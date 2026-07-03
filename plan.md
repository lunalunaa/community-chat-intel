# Chinese User Chat-History Analysis Plan

**Purpose:** Extract the same research signals a user poll would have produced — message counts, topics, official-vs-shadow-platform usage, messaging-adapter demand — from existing chat history rather than by actively polling users. Zero endorsement signal to any platform, zero sample-selection bias from who chooses to respond.

**Companion documents (repo-internal):**
- `README.md` — quick-start and file overview
- `analyze.py` (`chatintel-analyze` once installed) — the Python pipeline implementing this plan
- `report-template.md` — skeleton of the final findings report
- `docs/PIPELINE.md` — the deeper 4-stream analysis architecture

---

## 1. Research questions & their chat-history analogues

| Poll question | Chat-history analogue | Extraction method |
|---|---|---|
| Q1 Location | Cannot recover directly. Timezone-of-posting proxy. | Hour-of-day histogram per Chinese-primary user → mainland (UTC+8) vs overseas clusters |
| Q2 Acquisition channel | Messages containing "I saw" / "我看到" / "从..了解到" + URL references in first-N messages per user | Keyword + URL extraction, first-week-of-activity filter |
| Q3 Brand audit (impersonator sites) | Direct mentions of your product's known impersonator/clone domains (configure in `keywords.py`) | Regex URL extraction + domain classification |
| Q4 Install path | Messages about WSL2 / Linux / Docker / macOS / Windows install | Keyword cluster |
| Q5 Install friction | Error messages, help requests, "怎么装" / "安装失败" / "how do I install" | Error-keyword filter + help-request topic cluster |
| Q6 Model provider | Organic mentions of DeepSeek / Kimi / Qwen / GLM / Volcengine / Anthropic etc. | Provider-keyword frequency per user, weighted by "I use X" vs "X is bad" context |
| Q7 Messaging adapters | Mentions of Feishu / WeChat / WeCom / DingTalk / Telegram in feature-request or usage context | Platform-keyword filter + sentiment analysis |
| Q7b Competitor products | Organic mentions of named competitors (configure in `keywords.py`'s `COMPETITORS`) | Competitor-keyword filter |
| Q8 Help channels | Questions asked vs answered in the chat itself | Unanswered-question detection (no reply within N messages / N hours) |
| Q9 Feature usage | Mentions of your product's differentiator features | Feature-keyword frequency |
| Q10 Usage intensity | Messages per user over time; "stopped using" = last-seen timestamp | Per-user time-series |
| Q11 Preferred official Chinese channels | Cannot recover. Indirect: mentions of WeChat OA / Zhihu / Bilibili / ModelScope | Keyword frequency + context |
| Q12 Ongoing friction | Complaints, error reports, "问题/问不到/解决不了/没办法" | Complaint-keyword filter |

### Signals chat-history gives us that polls don't

1. **Question-to-answer ratio** — are Chinese users' questions getting answered?
2. **Retention cohort analysis** — when did each Chinese user first post, and when did they last post?
3. **Organic cross-platform references** — mentions of "I'm also on [X]" without us asking
4. **Actual provider configs** — users often paste config snippets
5. **Actual error messages** — tells us which failure modes are common
6. **Community mutual-help graph** — who answers whose questions?

### Signals polls would have given us that chat history won't

1. **Attitudes / preferences** the user didn't spontaneously express
2. **Reasons users stopped using** (they just go silent)
3. **Ranked preferences between alternatives** never mentioned together
4. **Acquisition channels** for users who never talked about how they found the product

**This is an acceptable tradeoff** given that the poll carries an endorsement signal we don't want to send.

---

## 2. Data sources & access

Confirm with the requester which of these are in scope. Pipeline supports all three input formats; at least one is required.

### Discord (expected primary)

- **Tool:** [`DiscordChatExporter`](https://github.com/Tyrrrz/DiscordChatExporter) by Tyrrrz (GUI + CLI available)
- **Format:** JSON (preferred — preserves metadata) or CSV
- **Scope options:**
  - Whole server (requires admin bot token)
  - Specific channels (e.g., `#help`, `#general`, any `#chinese`-tagged channel)
  - Date range (recommend last 6 months for first pass)
- **Permissions:** read-only bot token is sufficient; no admin needed unless private channels are in scope
- **Rate:** DiscordChatExporter respects Discord's rate limits automatically

### Telegram

- **Tool:** native Telegram Desktop → Settings → Advanced → Export chat history
- **Format:** JSON (select "JSON" in export UI, not HTML)
- **Scope:** one group/channel per export
- **Permissions:** you must be a member; admin not required for public groups

### WeChat

- **No native export.** Options:
  - You run a `wechaty`/`gewechat`-based bot that logs messages → JSON. Requires setup lead time + account pairing.
  - You use third-party decryption tools on your own device's WeChat database (Android root / iOS backup / macOS `CE0` database). Jurisdictional legality varies.
  - Manual copy-paste at small scale (impractical for meaningful analytics).
- **Recommendation:** skip WeChat for the first pass unless a bot has been logging messages historically. WeChat analytics are valuable but expensive to set up retroactively.

### Matrix / Slack / other

- Pipeline has a pluggable adapter layer; add a loader function that normalizes to the canonical schema (see §3.1). Adding a new platform is ~30 lines of code.

---

## 3. Pipeline design

### 3.1 Canonical message schema

All platform adapters normalize to this shape so downstream extractors are platform-agnostic:

```python
{
    "platform": "discord" | "telegram" | "matrix" | "wechat" | ...,
    "channel": "channel-name or group-id",
    "message_id": "stable unique id within platform",
    "author_id": "hash of platform-native user id",   # hashed for privacy
    "author_name": "display name (optional, kept in non-redacted version only)",
    "timestamp": "ISO 8601 UTC",
    "content": "raw message text (markdown + URLs preserved)",
    "reply_to_message_id": "id of parent message or None",
    "reactions": [{"emoji": "...", "count": int}],
    "attachment_count": int,
}
```

### 3.2 Stage sequence

```
INPUT (platform-native export)
    │
    ▼
[1] ADAPTER: platform-native → canonical schema
    │
    ▼
[2] LANG FILTER: classify each message → {zh, en, mixed, unknown}
    │     - Uses CJK-char ratio heuristic (fast, offline)
    │     - Optional upgrade: fasttext-lid or langdetect
    │
    ▼
[3] USER SEGMENTATION: per-user language profile
    │     - zh-primary / bilingual / en-primary / one-post
    │
    ▼
[4] KEYWORD EXTRACTION: apply dictionaries (see §3.3)
    │     - URLs, providers, claws, platforms, features, frictions
    │
    ▼
[5] TOPIC CATEGORIZATION: LLM-tag each zh/mixed message
    │     - Small set of stable topic categories (see §3.4)
    │     - Skippable for first pass; run later for richer report
    │
    ▼
[6] QUESTION DETECTION: identify question messages
    │     - Ends with ?/？/吗 etc. OR contains help-request phrases
    │
    ▼
[7] REPLY GRAPH: build question → reply chains
    │     - A question is "answered" if it has a reply within N hours
    │     - Unanswered questions = product-pain signal
    │
    ▼
[8] RETENTION COHORT: per-user first-post & last-post
    │     - Active / lapsed / one-time classification
    │
    ▼
[9] AGGREGATION: produce the stat tables the report template expects
    │     - Mirrors the poll's question structure
    │
    ▼
OUTPUT: JSON stat bundle + report.md with placeholders filled
```

### 3.3 Keyword dictionaries

Stored in `keywords.py`; loaded by `analyze.py`. Categories:

1. **Providers** — DeepSeek, Kimi / 月之暗面, Qwen / 通义, GLM / 智谱, MiniMax, Volcengine / 火山 / 方舟, Doubao / 豆包, Anthropic / Claude, OpenAI / ChatGPT, Gemini / Google, OpenRouter, HuggingFace, ModelScope / 魔搭, Ollama, vLLM, etc.
2. **Competitors** — your market's named competitor products and their slang/nicknames (EXAMPLE placeholders in `keywords.py`; replace with real ones)
3. **Messaging platforms** — Feishu / 飞书 / Lark, WeChat / 微信, WeCom / 企业微信, DingTalk / 钉钉, QQ, Discord, Telegram, Slack, Signal, Matrix, Email / 邮件, SMS
4. **Product features** — your product's differentiator feature names (EXAMPLE placeholders in `keywords.py`: skills / 技能, memory / 记忆, cron / 定时任务, delegate / 子任务 / 委派, browser / 浏览器, vision / 视觉, TTS / 语音, MCP, execute_code)
5. **Install paths** — WSL / WSL2, Docker, Linux, macOS, Windows, pip, uv, apt, brew, 安装
6. **Friction signals** — error, traceback, 报错, 超时, 翻墙, VPN, 失败, 卡住, 问题, 不能, 怎么办, help, fix, broken, slow
7. **Impersonator domains** — your product's known impersonator/clone domains (EXAMPLE placeholders in `keywords.py`; replace with real ones)
8. **Shadow-community markers** — 微信群, QQ群, 飞书群, 公众号, 知乎, B站 / 哔哩哔哩, 小红书, 掘金, 博客园 / CSDN / 思否
9. **Chinese-providers-by-region split markers** — 中国版, 国内版, 国际版, `.cn` domain TLD

Each keyword has:
- Canonical label (for deduplication)
- Pattern variants (中英混合 / case-insensitive / punctuation-tolerant)
- Context weighting (is the mention positive "I use X" vs negative "X is broken" vs neutral reference?) — LLM pass optional

### 3.4 Topic categories (LLM-tagged)

Small, stable set to keep tagging consistent:

- `install_help` — asking how to install / deploy
- `install_report` — reporting an install issue or fix
- `provider_config` — model provider setup or API key questions
- `messaging_adapter` — IM platform integration questions
- `feature_usage` — using your product's differentiator features
- `model_discussion` — which model is best / benchmarks / comparisons
- `community_meta` — announcements, meetups, links to external content
- `brand_identity` — "is [X site] official?" / authenticity questions
- `bug_report` — reproducible technical issue
- `feature_request` — "I wish this product could..."
- `success_story` — showing off something they built
- `general_discussion` — catch-all

Each message tagged with 1 primary + optional 1 secondary category.

### 3.5 LLM selection for topic tagging

- **First pass:** free/cheap model (a low-cost provider, or your own product dogfooding itself if it's an AI-agent tool) — batch prompts of 50 messages each, request JSON output
- **Validation:** sample 100 tagged messages, hand-check, compute precision/recall
- **Fallback:** unsupervised BERTopic clustering if LLM tagging is too noisy or expensive

Cost estimate: at ~20K Chinese messages, a few dollars on a cheap Chinese-market provider for a full pass. Trivial.

---

## 4. Output artifacts

### 4.1 Machine-readable

`stats.json` — single file containing all aggregated stats, one object per report section:

```json
{
  "metadata": {
    "analyzed_at": "2026-04-22T22:55:00Z",
    "source": "discord",
    "channels": ["#general", "#help"],
    "date_range": ["2025-10-01", "2026-04-22"],
    "total_messages": 123456,
    "chinese_messages": 7890,
    "chinese_users": 234,
    "pipeline_version": "0.1.0"
  },
  "location_proxy": {...},
  "acquisition": {...},
  "brand_audit": {...},
  "install": {...},
  "providers": {...},
  "claws": {...},
  "messaging_platforms": {...},
  "features": {...},
  "help_answered_rate": {...},
  "retention": {...},
  "friction": {...}
}
```

### 4.2 Human-readable

`report.md` — populated from `report-template.md` with all stat placeholders filled. Structure mirrors the poll structure so comparison is easy.

`excerpts.md` — redacted quote excerpts (paraphrased where needed) illustrating each key finding. Usernames hashed. Raw content only for unambiguously-public messages.

### 4.3 Privacy artifacts

- `user_hash_salt.key` — random salt used to hash user IDs; stored outside repo, not committed
- `id_mapping.json` — reversible mapping (hash → user_id) for internal re-identification, only stored on the analyst's machine

---

## 5. Privacy & ethics guardrails

**Hard rules:**

1. No raw user IDs, usernames, or avatars in outputs shared beyond the immediate analysis team
2. No direct message quotes in the shared report — paraphrase to the point where the original message is not reverse-searchable
3. Minimum quote length: any direct quote must be short enough and generic enough that it cannot be used to identify the author
4. Hashed IDs in intermediate files; salt stored separately
5. If anyone in the chat asks "are we being analyzed," the answer is truthful: yes, with these guardrails

**Soft norms:**

1. Announce retroactively in the chat once analysis is complete: "we did an aggregate analysis of Chinese-language activity to inform community planning. Here's what we found. No individual data was shared."
2. Offer an opt-out mechanism for future analyses (users can DM to request exclusion from future aggregate reports)
3. Retain raw data only as long as needed for the analysis; delete after the report is finalized

**Platform-specific considerations:**

- **Discord:** most servers don't have explicit analytics norms; aggregate analysis is generally accepted. Check server rules / community guidelines.
- **Telegram:** ToS permits aggregate member-content analysis; check group-specific rules.
- **WeChat:** socially sensitive. Announcing the analysis in advance (not retroactively) is recommended.
- **Matrix:** varies by room; some E2EE rooms' messages shouldn't be exported even if you can.

---

## 6. Timeline & effort

| Phase | Effort | Who |
|---|---|---|
| 1. Export chat history from Discord / Telegram / etc. | 1–4 hours depending on scope | Requester |
| 2. Run `chatintel-analyze` on the export | 15 min (CPU) + 1–2 hours (LLM pass) | Analyst |
| 3. Review stats, sanity-check, iterate keyword dictionaries | 2–3 hours | Analyst |
| 4. Fill in report template, write narrative sections | 3–4 hours | Analyst |
| 5. Internal review | 1–2 days elapsed | Leadership |
| 6. Publish aggregate findings to chat (opt-in) | 15 min | Community team |

**Total active work:** ~1–2 days after receiving the chat export.

---

## 7. Known limitations

1. **Self-selection bias doesn't disappear.** Chat-history analysis reflects only users who joined the chat and posted — lurkers and non-joiners are invisible. This is strictly worse than the poll for any "why didn't you join" question.
2. **Lapsed users are observationally equivalent to retained-but-quiet users.** "Last post 90 days ago" might mean "stopped using the product" or "using it daily but no longer chats about it."
3. **Chinese-primary classification is imperfect.** Users who code-switch heavily get misclassified; bilingual Western-diaspora Chinese users may look the same as mainland users in the data.
4. **Topic tagging quality depends on LLM choice.** First-pass cheap models will be noisy. Budget time for a human-validated sample.
5. **Reply-chain reconstruction is platform-dependent.** Discord reply threads are clean; Telegram replies are clean; Slack threaded replies are clean; unthreaded Telegram groups are ambiguous.
6. **Sarcasm, joke, in-group references** are not detected by keyword matching. LLM topic pass partially compensates but not fully.
7. **Impersonator-site mentions** may be benign references ("oh, is that site official?") rather than endorsements. Context matters; tagging is LLM-dependent.

---

## 8. Next steps checklist

- [ ] Requester selects platform(s) and scope (which channels, which date range)
- [ ] Requester runs the export tool and produces a JSON file
- [ ] Analyst updates `keywords.py` for any platform-specific terminology
- [ ] Analyst runs `chatintel-analyze --input <export.json> --platform discord --out ./out/`
- [ ] Analyst reviews `stats.json` and decides if LLM topic pass is needed (default: yes)
- [ ] Analyst runs `chatintel-topics --input-chat <export.json> --platform discord --out ./out/topics.json` if skipped initially
- [ ] Analyst fills `report.md` from the template + stats
- [ ] Analyst produces `excerpts.md` with paraphrased illustrative quotes
- [ ] Review with leadership
- [ ] Publish aggregate summary to the chat (optional but recommended)
