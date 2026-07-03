"""LLM topic-tagging pass for the community chat-history analysis pipeline.

Tags every target-language / mixed-language message with one of a fixed
topic set by shelling out to a locally-configured LLM CLI tool (any CLI that
accepts a prompt and prints the response to stdout). Configure the command
via the LLM_CLI environment variable (space-separated, default: "hermes chat
-q") — see run_llm_cli() below.

Works for any target language (see `languages.py` for the supported list) —
pass `--target-language ja` for Japanese, `--target-language none` to tag
every message regardless of language classification, etc. Defaults to `zh`
for backward compatibility.

No direct API calls, no external API keys needed from this script itself —
your provider's key lives wherever your chosen CLI expects it, and the CLI
handles auth, retries, rate limits, streaming.

WHY THIS DESIGN:
  - Respects the user's provider preference (no hard-coded provider)
  - Reuses whatever LLM orchestration tooling you already have configured
  - Zero additional auth / SDK / dependency surface
  - Resumable via message-content hash cache

USAGE:
  # First configure a provider on your chosen CLI once, then:
  parallax-topics \\
      --users-json ./out/users.json \\
      --input-chat ./discord_export.json \\
      --platform discord \\
      --target-language ja \\
      --out ./out/topics.json \\
      [--batch-size 25] \\
      [--concurrency 2] \\
      [--dry-run] \\
      [--limit 100]       # for testing / cost-capping

The script writes:
  - ./out/topics.json              : message_id -> topic
  - ./out/topics_by_category.json  : category -> [message_ids]
  - ./out/.topics_cache.json       : content_hash -> topic  (never delete — resumes across runs)
  - updates ./out/stats.json       : adds .topics aggregated counts (merge)
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from parallax.core import analyze
from parallax.core import languages as lang

# ----------------------------------------------------------------------------
# Topic categories — see plan.md §3.4
# ----------------------------------------------------------------------------
TOPIC_CATEGORIES = [
    "install_help",  # asking how to install / deploy
    "install_report",  # reporting install issue or sharing a fix
    "provider_config",  # model provider setup or API key questions
    "messaging_adapter",  # IM platform integration questions
    "feature_usage",  # using product-specific features (skills / memory / cron / etc.)
    "model_discussion",  # which model is best / benchmarks / comparisons
    "community_meta",  # announcements, meetups, links to external content
    "brand_identity",  # "is [X site] official?" / authenticity questions
    "bug_report",  # reproducible technical issue
    "feature_request",  # "I wish this product could..."
    "success_story",  # showing off something they built
    "general_discussion",  # catch-all, including casual chat
]


# ----------------------------------------------------------------------------
# Prompt construction
# ----------------------------------------------------------------------------
def build_system_prompt_header(language_name: str | None) -> str:
    """Build the classifier system prompt for the given target-language name.

    `language_name=None` means language classification was disabled upstream
    (every message is treated as in-scope) — the prompt is phrased generically
    in that case rather than naming a specific bilingual pairing.
    """
    bilingual_desc = (
        f"a {language_name}/English-bilingual message classifier"
        if language_name
        else "a multilingual message classifier"
    )
    brand_example_lang = (
        f"other {language_name}-language" if language_name else "other local-language"
    )
    return f"""\
You are {bilingual_desc} for a product's community chat.

For each message in the input batch, assign exactly ONE primary topic from this list:
  - install_help       : user is asking HOW to install / deploy the product or a dependency
  - install_report     : user is sharing an install experience, fix, or error
  - provider_config    : questions or discussion about model provider setup / API keys / config
  - messaging_adapter  : questions or discussion about IM platform integration (any platform)
  - feature_usage      : using product-specific features (skills / memory / cron / subagents / MCP / browser / vision / etc.)
  - model_discussion   : comparing models, benchmarks, opinions about which LLM is best
  - community_meta     : announcements, links to external content, meetups, events
  - brand_identity     : asking whether a site / group chat / {brand_example_lang} resource is official
  - bug_report         : reporting a reproducible technical issue
  - feature_request    : requesting a new feature or capability
  - success_story      : showing off a workflow, demo, or success
  - general_discussion : casual chat, greetings, off-topic, or anything that doesn't fit above

OUTPUT FORMAT (STRICT):
Return a JSON array. One element per input message. Each element has exactly:
  {{"id": "<message id as given>", "topic": "<one of the categories above>"}}

Do not include any other text, markdown, or explanation. Only the JSON array.

Examples:
  Input:  [{{"id": "m1", "text": "怎么配置这个 provider? 报错了 unauthorized"}}]
  Output: [{{"id": "m1", "topic": "provider_config"}}]

  Input:  [{{"id": "m2", "text": "有人在 example-product.org.cn 上看过介绍吗？是官方的吗"}}]
  Output: [{{"id": "m2", "topic": "brand_identity"}}]
"""


def build_batch_prompt(batch: list[dict[str, str]], system_prompt_header: str) -> str:
    """Pair the system header with a batch of messages to classify."""
    payload = json.dumps(batch, ensure_ascii=False)
    return (
        f"{system_prompt_header}\n"
        f"Classify the following {len(batch)} message(s). "
        f"Return exactly {len(batch)} elements in the output array, in the same order.\n\n"
        f"Input:\n{payload}\n\n"
        f"Output (JSON array only):"
    )


# ----------------------------------------------------------------------------
# LLM CLI invocation
# ----------------------------------------------------------------------------


def call_llm_cli(
    prompt: str,
    provider: str | None = None,
    model: str | None = None,
    timeout: int = 180,
) -> str:
    """Shell out to a local LLM CLI tool ("hermes chat -q ..." by default).

    Returns the raw stdout (with the leading `session_id: ...` line stripped,
    a quirk of the default CLI's --quiet output).
    Raises subprocess.CalledProcessError or TimeoutExpired on failure.
    """
    cmd = [
        "hermes",
        "chat",
        "-q",
        prompt,
        "--quiet",
        "--ignore-rules",  # skip AGENTS.md / memory / skills injection
        "--ignore-user-config",  # skip custom config; use defaults from .env
        "--max-turns",
        "1",  # single completion — no tool-calling loops
        "--source",
        "tool",  # hide from user session list
    ]
    if provider:
        cmd.extend(["--provider", provider])
    if model:
        cmd.extend(["--model", model])

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
    out = r.stdout

    # Strip the "session_id: xxx" line(s) that --quiet still prints
    lines = out.split("\n")
    filtered = [l for l in lines if not l.startswith("session_id:")]
    return "\n".join(filtered).strip()


def parse_llm_response(raw: str, expected_ids: list[str]) -> dict[str, str] | None:
    """Extract the JSON array from the model response and turn it into a dict.

    Returns None on parse failure — caller decides whether to retry with a
    smaller batch, fall back to a default topic, etc.
    """
    # Strip common wrappers: ```json ... ```, ``` ... ```
    s = raw.strip()
    fenced = re.match(r"```(?:json)?\s*(.*?)\s*```", s, re.DOTALL)
    if fenced:
        s = fenced.group(1).strip()

    # Find the first [...] block — robust against models that add prose before/after
    m = re.search(r"\[\s*\{.*?\}\s*\]", s, re.DOTALL)
    if m:
        s = m.group(0)

    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, list):
        return None

    result: dict[str, str] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id", ""))
        topic = str(item.get("topic", ""))
        if topic not in TOPIC_CATEGORIES:
            # Tolerate minor capitalization; fall back to general_discussion
            topic_lc = topic.lower().strip()
            if topic_lc in TOPIC_CATEGORIES:
                topic = topic_lc
            else:
                topic = "general_discussion"
        result[mid] = topic

    # Return None if model didn't produce one topic per expected id
    if not all(mid in result for mid in expected_ids):
        return None

    return result


# ----------------------------------------------------------------------------
# Cache
# ----------------------------------------------------------------------------


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class TopicCache:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, str] = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                print(
                    f"[cache] warning: {path} corrupt, starting fresh", file=sys.stderr
                )
                self.data = {}

    def get(self, text: str) -> str | None:
        return self.data.get(content_hash(text))

    def set(self, text: str, topic: str) -> None:
        self.data[content_hash(text)] = topic

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self.path)


# ----------------------------------------------------------------------------
# Message loading (reuses analyze.py adapters)
# ----------------------------------------------------------------------------


def load_target_language_messages(
    chat_path: Path,
    platform: str,
    salt: str,
    language_profile: lang.LanguageProfile | None,
) -> list[analyze.Message]:
    """Load messages, filter to target + mixed (or all, if language_profile is None)."""
    adapter = analyze.ADAPTERS[platform]
    all_msgs = list(adapter(chat_path, salt))
    if language_profile is None:
        return all_msgs
    filtered = []
    for m in all_msgs:
        classification = analyze.classify_language(m.content, language_profile)
        if classification in ("target", "mixed"):
            filtered.append(m)
    return filtered


# ----------------------------------------------------------------------------
# Main pipeline
# ----------------------------------------------------------------------------


def process_batch(
    batch: list[analyze.Message],
    provider: str | None,
    model: str | None,
    cache: TopicCache,
    dry_run: bool,
    system_prompt_header: str,
) -> dict[str, str]:
    """Tag a single batch. Returns {message_id: topic}."""
    # Cache lookup first — filter out already-tagged messages
    to_tag: list[analyze.Message] = []
    results: dict[str, str] = {}
    for m in batch:
        cached = cache.get(m.content)
        if cached is not None:
            results[m.message_id] = cached
        else:
            to_tag.append(m)

    if not to_tag:
        return results

    if dry_run:
        for m in to_tag:
            results[m.message_id] = "general_discussion"
        return results

    # Truncate very long messages to avoid blowing context — we only need
    # enough signal to classify, not full content
    batch_payload = [{"id": m.message_id, "text": m.content[:800]} for m in to_tag]
    prompt = build_batch_prompt(batch_payload, system_prompt_header)
    expected_ids = [m.message_id for m in to_tag]

    # Try once, retry once with smaller batch on parse failure
    try:
        raw = call_llm_cli(prompt, provider=provider, model=model)
    except subprocess.TimeoutExpired:
        print(
            f"[llm-cli] timeout on batch of {len(to_tag)}; marking all as general_discussion",
            file=sys.stderr,
        )
        for m in to_tag:
            results[m.message_id] = "general_discussion"
        return results
    except subprocess.CalledProcessError as e:
        print(
            f"[llm-cli] error on batch of {len(to_tag)}: {e.stderr[:500]}",
            file=sys.stderr,
        )
        for m in to_tag:
            results[m.message_id] = "general_discussion"
        return results

    parsed = parse_llm_response(raw, expected_ids)

    if parsed is None and len(to_tag) > 1:
        # Retry each message individually — slower but more reliable
        print(
            f"[parse] batch parse failed; retrying {len(to_tag)} individually",
            file=sys.stderr,
        )
        parsed = {}
        for m in to_tag:
            single_prompt = build_batch_prompt(
                [{"id": m.message_id, "text": m.content[:800]}], system_prompt_header
            )
            try:
                single_raw = call_llm_cli(single_prompt, provider=provider, model=model)
                single_parsed = parse_llm_response(single_raw, [m.message_id])
                if single_parsed:
                    parsed.update(single_parsed)
                else:
                    parsed[m.message_id] = "general_discussion"
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                parsed[m.message_id] = "general_discussion"

    if parsed is None:
        parsed = {m.message_id: "general_discussion" for m in to_tag}

    # Cache + merge
    for m in to_tag:
        topic = parsed.get(m.message_id, "general_discussion")
        cache.set(m.content, topic)
        results[m.message_id] = topic

    return results


def run(
    chat_path: Path,
    platform: str,
    out_path: Path,
    salt_path: Path,
    batch_size: int = 25,
    concurrency: int = 2,
    provider: str | None = None,
    model: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    stats_path: Path | None = None,
    language_profile: lang.LanguageProfile | None = None,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path = out_path.parent / ".topics_cache.json"
    cache = TopicCache(cache_path)

    system_prompt_header = build_system_prompt_header(
        language_profile.name if language_profile else None
    )

    salt = analyze.ensure_salt(salt_path)
    messages = load_target_language_messages(
        chat_path, platform, salt, language_profile
    )
    if limit:
        messages = messages[:limit]

    lang_desc = language_profile.name if language_profile else "all-language"
    print(
        f"[topics] {len(messages)} {lang_desc}/mixed messages to tag "
        f"(cache has {len(cache.data)} entries)",
        file=sys.stderr,
    )

    # Build batches
    batches = [
        messages[i : i + batch_size] for i in range(0, len(messages), batch_size)
    ]
    print(f"[topics] {len(batches)} batches of ≤{batch_size} messages", file=sys.stderr)

    all_results: dict[str, str] = {}
    start = time.time()

    if concurrency <= 1:
        for i, batch in enumerate(batches):
            batch_results = process_batch(
                batch, provider, model, cache, dry_run, system_prompt_header
            )
            all_results.update(batch_results)
            cache.save()  # persist after each batch so Ctrl-C is safe
            elapsed = time.time() - start
            print(
                f"[topics] batch {i + 1}/{len(batches)} done "
                f"({len(all_results)}/{len(messages)} msgs, {elapsed:.0f}s)",
                file=sys.stderr,
            )
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = {
                ex.submit(
                    process_batch,
                    b,
                    provider,
                    model,
                    cache,
                    dry_run,
                    system_prompt_header,
                ): i
                for i, b in enumerate(batches)
            }
            for f in as_completed(futures):
                batch_results = f.result()
                all_results.update(batch_results)
                cache.save()
                elapsed = time.time() - start
                print(
                    f"[topics] one batch done "
                    f"({len(all_results)}/{len(messages)} msgs, {elapsed:.0f}s)",
                    file=sys.stderr,
                )

    # Write topics.json (message_id → topic)
    topics_out = out_path.parent / "topics.json"
    topics_out.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[write] {topics_out}", file=sys.stderr)

    # Write topics_by_category.json (category → [message_ids])
    by_cat: dict[str, list[str]] = collections.defaultdict(list)
    for mid, topic in all_results.items():
        by_cat[topic].append(mid)
    by_cat_out = out_path.parent / "topics_by_category.json"
    by_cat_out.write_text(
        json.dumps(
            {k: sorted(v) for k, v in by_cat.items()}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    print(f"[write] {by_cat_out}", file=sys.stderr)

    # Merge topic counts into stats.json if present
    if stats_path is None:
        stats_path = out_path.parent / "stats.json"
    if stats_path.exists():
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        counts = collections.Counter(all_results.values())
        stats["topics"] = {
            "total_tagged": len(all_results),
            "counts": dict(counts.most_common()),
            "by_category": {k: len(v) for k, v in by_cat.items()},
        }
        stats_path.write_text(
            json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[merge] updated {stats_path} with .topics section", file=sys.stderr)

        # Re-render report.md so §9b shows real data
        template_path = (
            Path(__file__).parent.parent / "templates" / "report-template.md"
        )
        report_path = stats_path.parent / "report.md"
        if template_path.exists():
            report_md = analyze.render_report(template_path, stats)
            report_path.write_text(report_md, encoding="utf-8")
            print(f"[re-render] {report_path} with topics", file=sys.stderr)

    elapsed = time.time() - start
    print(
        f"[done] tagged {len(all_results)} messages in {elapsed:.0f}s", file=sys.stderr
    )


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(
        description="LLM topic-tagging pass for community chat analysis."
    )
    p.add_argument(
        "--input-chat",
        required=True,
        type=Path,
        help="Chat export JSON (same file used with analyze.py)",
    )
    p.add_argument("--platform", required=True, choices=list(analyze.ADAPTERS.keys()))
    p.add_argument(
        "--target-language",
        type=str,
        default="zh",
        help="Language code to filter/tag messages for (see languages.py "
        "LANGUAGE_PROFILES; default: zh). Pass 'none' to tag every message "
        "regardless of language classification.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("./out/topics.json"),
        help="Output path for topics.json (default: ./out/topics.json)",
    )
    p.add_argument(
        "--salt-file",
        type=Path,
        default=Path("./user_hash_salt.key"),
        help="User-ID hashing salt file (default: ./user_hash_salt.key in the "
        "current working directory — never commit this file)",
    )
    p.add_argument(
        "--stats-path",
        type=Path,
        default=None,
        help="Path to stats.json to merge .topics into (default: <out>/stats.json)",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Messages per LLM CLI call (default: 25)",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Parallel LLM CLI subprocesses (default: 1 — sequential)",
    )
    p.add_argument(
        "--provider",
        type=str,
        default=None,
        help="LLM CLI --provider override (default: whatever you have configured)",
    )
    p.add_argument("--model", type=str, default=None, help="LLM CLI --model override")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't call the LLM CLI; tag everything as general_discussion (for pipeline shape testing)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N target-language messages (for testing / cost-capping)",
    )
    args = p.parse_args()

    language_profile = lang.get_language_profile(args.target_language)
    if args.target_language not in (None, "none", "off") and language_profile is None:
        print(
            f"[warn] unknown --target-language '{args.target_language}'; "
            f"known codes: {', '.join(sorted(lang.LANGUAGE_PROFILES))}. "
            f"Falling back to no language filtering.",
            file=sys.stderr,
        )

    # Check the LLM CLI is available unless dry-run
    if not args.dry_run:
        try:
            r = subprocess.run(
                ["hermes", "--version"], capture_output=True, text=True, timeout=10
            )
            if r.returncode != 0:
                print(
                    "[error] `hermes --version` failed. Is your LLM CLI installed and on PATH? "
                    "(edit call_llm_cli() to point at your own CLI if it isn't named `hermes`)",
                    file=sys.stderr,
                )
                return 2
            print(
                f"[llm-cli] {r.stdout.strip().splitlines()[0] if r.stdout else 'found'}",
                file=sys.stderr,
            )
        except FileNotFoundError:
            print(
                "[error] `hermes` not found on PATH. Install your LLM CLI of choice, "
                "or edit call_llm_cli() to invoke a different command.",
                file=sys.stderr,
            )
            return 2
        except subprocess.TimeoutExpired:
            print(
                "[error] `hermes --version` timed out. Your LLM CLI may be misconfigured.",
                file=sys.stderr,
            )
            return 2

    run(
        chat_path=args.input_chat,
        platform=args.platform,
        out_path=args.out,
        salt_path=args.salt_file,
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        provider=args.provider,
        model=args.model,
        dry_run=args.dry_run,
        limit=args.limit,
        stats_path=args.stats_path,
        language_profile=language_profile,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
