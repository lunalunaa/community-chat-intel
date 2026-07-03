#!/usr/bin/env python3
"""Retry the 16 failed chunks from Stream C, with tolerant JSON parsing.

Uses the exact same prompt and chunk definitions as stream_c_fact_extract.py,
but:
  - Accepts trailing commas (MiMo's main failure mode)
  - Falls back to json5-style repair if needed
  - Writes recovered results into chunks_cache.jsonl so the main aggregation
    sees them
  - Regenerates summary.json and aggregated_facts.json
"""
import json
import os
import re
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

CHAT_JSONL = Path(os.environ.get("CHAT_JSONL", "./data/pages.jsonl"))
OUT_DIR = Path(os.environ.get("OUT_DIR", "./out/stream_c"))
SALT = Path(os.environ.get("SALT_FILE", "./user_hash_salt.key")).read_text().strip()

def hash_user(uid):
    if not uid: return "unknown"
    return "u_" + hashlib.sha256((SALT + uid).encode()).hexdigest()[:12]

CHINA_TZ = timezone(timedelta(hours=8))
def parse_ts(s):
    if isinstance(s, str) and re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}', s):
        return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=CHINA_TZ).astimezone(timezone.utc)
    return None

messages = []
for line in CHAT_JSONL.open():
    try:
        m = json.loads(line)
    except json.JSONDecodeError:
        continue
    if m.get('msg_type') == 'system':
        continue
    content = m.get('content') or ''
    if isinstance(content, dict):
        content = content.get('text', '') or json.dumps(content, ensure_ascii=False)
    if not isinstance(content, str):
        content = str(content)
    if len(content.strip()) < 3:
        continue
    sender = m.get('sender') or {}
    uid = sender.get('id') or sender.get('open_id') or ''
    messages.append({
        'id': m.get('message_id', ''),
        'uhash': hash_user(uid),
        'name': sender.get('name', '?'),
        'ts': m.get('create_time', ''),
        'content': content.strip()[:800],
    })
messages.sort(key=lambda x: x['ts'])

CHUNK_SIZE = 100
chunks = [messages[i:i+CHUNK_SIZE] for i in range(0, len(messages), CHUNK_SIZE)]

# Same prompt as original
EXTRACTION_PROMPT = """You are analyzing a chunk of chat messages from the Chinese Hermes Agent community on Feishu. Extract structured facts. Output a single valid JSON object matching this schema (omit arrays that have no instances):

{
  "install_problems": [{"user_ref": "a short tag like 'user_A' or actual @name", "problem": "what broke", "os_or_context": "optional", "resolved": true/false/null}],
  "provider_usage": [{"user_ref": "...", "provider_or_gateway": "nous_portal | openrouter | direct_kimi | direct_minimax | direct_glm | direct_volcengine | direct_deepseek | direct_qwen | proxy_reseller | self_hosted | anthropic | openai | other", "sentiment": "positive | negative | neutral", "quoted_context": "short"}],
  "messaging_intent": [{"user_ref": "...", "platform": "feishu | wechat | dingtalk | qq | slack | discord | telegram | lark_intl | other", "intent": "exploring | wants_adapter | actively_building | using_via_existing_adapter", "context": "short"}],
  "brand_confusion": [{"user_ref": "...", "question": "what they asked", "resolution": "answered | unanswered | conflicting"}],
  "api_key_sharing_evidence": [{"user_ref": "...", "type": "offering | seeking | reselling | group_purchase", "details": "short"}],
  "pricing_complaints": [{"user_ref": "...", "service": "what", "issue": "short"}],
  "feature_requests": [{"user_ref": "...", "feature": "what they want", "use_case": "short"}],
  "success_stories": [{"user_ref": "...", "what_built": "short", "tools_used": ["skills", "memory", "cron", "mcp", ...]}],
  "vpn_network_friction": [{"user_ref": "...", "issue": "short", "workaround": "optional"}],
  "competitor_mentions": [{"user_ref": "...", "competitor": "arkclaw | kimiclaw | workbuddy | coze | claude_code | codex | cursor | other", "stance": "favoring_hermes | favoring_competitor | neutral_comparison"}]
}

Rules:
- Only extract facts actually supported by the messages. No speculation.
- If a chunk is mostly off-topic chatter, return mostly empty arrays.
- Use actual user names from messages when present (anonymize only if clearly harmful).
- Keep all field values concise (<50 chars where possible).
- IMPORTANT: Output STRICTLY valid JSON. No trailing commas. No comments. Just the JSON object.
- Output ONLY the JSON object, no prose before or after.

MESSAGES:
"""

def format_chunk(chunk):
    out = []
    for m in chunk:
        c = m['content'].replace('\n', ' ')[:500]
        out.append(f"[{m['ts']}] {m['name']}: {c}")
    return "\n".join(out)

def call_mimo(prompt, timeout=180):
    cmd = ["hermes", "chat", "-q", prompt, "--quiet", "--ignore-rules", "--ignore-user-config",
           "--max-turns", "1", "--source", "tool",
           "--provider", os.environ.get("LLM_PROVIDER", "nous"),
           "--model", os.environ.get("LLM_MODEL", "xiaomi/mimo-v2.5")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
    out = r.stdout
    lines = [l for l in out.split('\n') if not l.startswith('session_id:')]
    return '\n'.join(lines).strip()

def tolerant_json_parse(raw: str):
    """Try strict json first, then strip trailing commas, then json5-ish repair."""
    # Strip markdown fences
    cleaned = re.sub(r'^```(?:json)?|```$', '', raw, flags=re.MULTILINE).strip()
    # Find object
    m = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if not m:
        return None, 'no_json_found'
    body = m.group()
    # 1. strict
    try:
        return json.loads(body), None
    except json.JSONDecodeError:
        pass
    # 2. strip trailing commas: ,] -> ], ,} -> }
    body2 = re.sub(r',(\s*[\]}])', r'\1', body)
    try:
        return json.loads(body2), None
    except json.JSONDecodeError:
        pass
    # 3. try json5 if available
    try:
        import json5
        return json5.loads(body), None
    except ImportError:
        pass
    except Exception:
        pass
    # 4. try the last `{ ... }` in case MiMo concatenated multiple outputs
    last = re.findall(r'\{[^\{\}]*(?:\{[^\{\}]*\}[^\{\}]*)*\}', body, re.DOTALL)
    for candidate in reversed(last):
        candidate2 = re.sub(r',(\s*[\]}])', r'\1', candidate)
        try:
            return json.loads(candidate2), None
        except Exception:
            continue
    return None, 'all_parsers_failed'

def extract_from_chunk(idx, chunk):
    prompt = EXTRACTION_PROMPT + format_chunk(chunk)
    try:
        raw = call_mimo(prompt)
    except subprocess.TimeoutExpired:
        return idx, {'_error': 'timeout'}
    except subprocess.CalledProcessError as e:
        return idx, {'_error': f'subprocess_error: {e.stderr[:200]}'}
    facts, err = tolerant_json_parse(raw)
    if facts is None:
        return idx, {'_error': err, '_raw': raw[:800]}
    return idx, facts

# Load errors list
errors = json.load((OUT_DIR / "extraction_errors.json").open())
error_idxs = [e['chunk_idx'] for e in errors]
print(f"Retrying {len(error_idxs)} failed chunks: {error_idxs}", flush=True)

results = {}
import time
t0 = time.time()
with ThreadPoolExecutor(max_workers=4) as ex:
    futures = {ex.submit(extract_from_chunk, i, chunks[i]): i for i in error_idxs}
    for fut in as_completed(futures):
        idx, facts = fut.result()
        results[idx] = facts
        status = '✓' if '_error' not in facts else f'✗ {facts["_error"][:60]}'
        print(f"  chunk {idx}: {status}", flush=True)

# Append successes to chunks_cache.jsonl
cache_file = OUT_DIR / "chunks_cache.jsonl"
with cache_file.open('a') as fh:
    for idx, facts in results.items():
        if '_error' not in facts:
            fh.write(json.dumps({'chunk_idx': idx, 'facts': facts}, ensure_ascii=False) + '\n')

# Rebuild aggregation
print("\nRebuilding aggregates...", flush=True)
all_facts = {}
for line in cache_file.open():
    try:
        d = json.loads(line)
        all_facts[d['chunk_idx']] = d['facts']
    except Exception:
        continue

CATEGORIES = ['install_problems', 'provider_usage', 'messaging_intent', 'brand_confusion',
    'api_key_sharing_evidence', 'pricing_complaints', 'feature_requests',
    'success_stories', 'vpn_network_friction', 'competitor_mentions']

aggregated = {c: [] for c in CATEGORIES}
remaining_errors = []
for idx, facts in sorted(all_facts.items()):
    if '_error' in facts:
        remaining_errors.append({'chunk_idx': idx, 'error': facts['_error']})
        continue
    for cat in CATEGORIES:
        items = facts.get(cat, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    item['_chunk_idx'] = idx
                    aggregated[cat].append(item)

(OUT_DIR / "aggregated_facts.json").write_text(json.dumps(aggregated, indent=2, ensure_ascii=False))
(OUT_DIR / "extraction_errors.json").write_text(json.dumps(remaining_errors, indent=2, ensure_ascii=False))

summary = {cat: len(items) for cat, items in aggregated.items()}
summary['_total_chunks'] = len(all_facts)
summary['_successful_chunks'] = len(all_facts) - len(remaining_errors)
summary['_error_chunks'] = len(remaining_errors)

provider_counts = {}
for item in aggregated['provider_usage']:
    p = item.get('provider_or_gateway', 'unknown')
    sentiment = item.get('sentiment', 'neutral')
    key = f"{p}_{sentiment}"
    provider_counts[key] = provider_counts.get(key, 0) + 1

messaging_intent_counts = {}
for item in aggregated['messaging_intent']:
    key = f"{item.get('platform', 'unknown')}_{item.get('intent', 'unknown')}"
    messaging_intent_counts[key] = messaging_intent_counts.get(key, 0) + 1

competitor_counts = {}
for item in aggregated['competitor_mentions']:
    key = f"{item.get('competitor', 'unknown')}_{item.get('stance', 'unknown')}"
    competitor_counts[key] = competitor_counts.get(key, 0) + 1

(OUT_DIR / "summary.json").write_text(json.dumps({
    'overview': summary,
    'provider_usage_breakdown': provider_counts,
    'messaging_intent_breakdown': messaging_intent_counts,
    'competitor_breakdown': competitor_counts,
}, indent=2, ensure_ascii=False))

print("\n=== RETRY RESULT ===")
print(f"  Retried: {len(error_idxs)}")
print(f"  Recovered: {sum(1 for r in results.values() if '_error' not in r)}")
print(f"  Still failing: {len(remaining_errors)}")
print("  Total facts now:")
for cat, count in summary.items():
    if not cat.startswith('_'):
        print(f"    {cat:30s}: {count}")
