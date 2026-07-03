#!/usr/bin/env python3
"""Post-analysis: brand audit, token-complaint drill, messaging CSV exports.

The BRAND_PATTERNS dict below is a worked EXAMPLE (brand-impersonator /
competitor-slang detection for the open-source "Hermes Agent" project and its
"Claw" ecosystem of competitors) to show the pattern end-to-end. Swap in your
own product's brand variants, impersonator domains, and competitor slang.
"""
import json
import os
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(os.environ.get("OUT_DIR", "./out"))
CHAT = Path(os.environ.get("CHAT_JSONL", "./data/pages.jsonl"))

facts = json.load((BASE / "stream_c/aggregated_facts.json").open())
findings = json.load((BASE / "stream_b/synthesized_findings.json").open())
retrieval = json.load((BASE / "stream_b/retrieval_results.json").open())
topics = json.load((BASE / "topics.json").open())
stream_d_stats = {}
for f in (BASE / "stream_d").glob("*.json"):
    stream_d_stats[f.stem] = json.load(f.open())

# =========================================================================
# (a) BRAND AUDIT
# =========================================================================
print("[a] brand audit...", flush=True)
brand_out = BASE / "post/brand_audit.md"
brand_out.parent.mkdir(exist_ok=True)

# 1. All brand_confusion incidents
# 2. Scan ALL messages for impersonator/clone names + slang variants
BRAND_PATTERNS = {
    "hermes_official":       r"hermes[-\s]?agent|nousresearch",
    "aigc_green_shadow":     r"aigc\.green|hermes-doc\.aigc|word\.aigc|hermes\.aigc",
    "maxhermes":             r"maxhermes|max[\s-]?hermes",
    "nanobot":               r"nanobot|nano[\s-]?bot",
    "hermes_cn_shadow":      r"hermes-agent\.(cn|org\.cn)|hermesagent|hermesagentai",
    "luxury_brand_slang":    r"爱马仕",
    "openclaw_slang_lobster": r"龙虾|小龙虾|lobster",
    "openclaw_official":     r"openclaw",
    "clawhub":               r"clawhub",
    "arkclaw":               r"arkclaw|ark[\s-]?claw",
    "kimi_claw":             r"kimiclaw|kimi[\s-]?claw",
    "workbuddy":             r"workbuddy|work[\s-]?buddy",
    "autoclaw":              r"autoclaw|auto[\s-]?claw",
    "coze":                  r"coze|扣子",
    "qclaw":                 r"qclaw|q[\s-]?claw",
    "duclaw":                r"duclaw|du[\s-]?claw",
    "maxclaw":               r"maxclaw|max[\s-]?claw",
    "stepclaw":              r"stepclaw",
    "lobsterai":             r"lobsterai|lobster[\s-]?ai",
    "countbot":              r"countbot|count[\s-]?bot",
    "hiclaw":                r"hiclaw",
    "pokeclaw":              r"pokeclaw",
    "opencraw":              r"opencraw|open[\s-]?craw",
    "openharness":           r"openharness",
    "proxy_domains":         r"szygumin\.icu|opennana\.com|aitokenwave|toolin\.ai",
}

counts = Counter()
samples = defaultdict(list)
cnt = 0
for line in CHAT.open():
    try:
        m = json.loads(line)
    except: continue
    if m.get('msg_type') == 'system': continue
    content = m.get('content') or ''
    if isinstance(content, dict):
        content = content.get('text','') or ''
    if not isinstance(content, str): continue
    cnt += 1
    lc = content.lower()
    for brand, pat in BRAND_PATTERNS.items():
        if re.search(pat, lc, re.IGNORECASE):
            counts[brand] += 1
            if len(samples[brand]) < 8:
                sender = (m.get('sender') or {}).get('name', '?')
                samples[brand].append({'ts': m.get('create_time',''), 'sender': sender,
                    'content': content[:250].replace('\n',' ')})

# Build report
md = ["# Brand Audit — Example Run", "",
    "Scope: all non-system messages in the export, regex-matched against known brand patterns + newly-discovered impersonators",
    "", f"Corpus scanned: {cnt:,} non-system messages", "",
    "## Summary Counts", "",
    "| Brand / Variant | Message Count |", "|---|---:|"]
for b, c in counts.most_common():
    md.append(f"| `{b}` | {c:,} |")

md += ["", "## Key Observations", "",
    "- **Luxury-brand slang `爱马仕` (Hermès-the-fashion-house)** is used informally for Hermes Agent. Non-malicious but creates Baidu/WeChat SEO confusion.",
    "- **`龙虾 / 小龙虾` (lobster)** is the primary slang for OpenClaw — shows up 5-10× more than 'openclaw' text. Any sentiment analysis on 'openclaw' alone misses most discussion.",
    "- **`aigc.green` cluster** (hermes-doc.aigc.green, word.aigc.green, hermes.aigc.green) — unofficial docs site network not in original impersonator list.",
    "- **`MaxHermes` and `nanobot`** — example of newly-discovered competitor/clone names surfaced via Stream C fact extraction that weren't in the original impersonator list.",
    "", "---", "", "## Sample Messages (up to 8 per brand, for context)", ""]
for brand in counts:
    if not samples[brand]: continue
    md += [f"### {brand} ({counts[brand]} mentions)", ""]
    for s in samples[brand]:
        md.append(f"- **{s['sender']}** ({s['ts']}): {s['content']}")
    md.append("")

# Merge Stream C brand_confusion incidents
md += ["---", "", "## Stream C Structured Brand_Confusion Incidents", "",
    f"Total incidents: {len(facts['brand_confusion'])}", "",
    "### Resolution breakdown"]
res_counts = Counter(i.get('resolution','unknown') for i in facts['brand_confusion'])
md += [f"- {r}: {c}" for r, c in res_counts.most_common()]
md += ["", "### 40 random incidents"]
import random
random.seed(0)
for i in random.sample(facts['brand_confusion'], min(40, len(facts['brand_confusion']))):
    q = i.get('question','').replace('\n',' ')[:200]
    r = i.get('resolution','?')
    u = i.get('user_ref','?')
    md.append(f"- [{r}] **{u}**: {q}")

brand_out.write_text("\n".join(md), encoding='utf-8')
print(f"[a] wrote {brand_out} ({brand_out.stat().st_size // 1024} KB)", flush=True)

# =========================================================================
# (b) TOKEN CONSUMPTION DRILL
# =========================================================================
print("[b] token consumption drill...", flush=True)
tok_out = BASE / "post/token_consumption.md"
TOK_PAT = re.compile(r'(token|消耗|costs?|费用|tokens?消耗|几十|几百|几千万|烧钱|太贵|expensive|太费|耗费|爆表|超出|超标|burn)', re.IGNORECASE)
AMT_PAT = re.compile(r'(\d+(?:\.\d+)?)\s*(?:万|千万|亿|k|m|千|百万|万亿)?\s*(?:token|美元|元|块|刀|rmb|\$|￥|¥)', re.IGNORECASE)

tok_hits = []
for line in CHAT.open():
    try: m = json.loads(line)
    except: continue
    if m.get('msg_type') == 'system': continue
    content = m.get('content') or ''
    if isinstance(content, dict): content = content.get('text','') or ''
    if not isinstance(content, str): continue
    if TOK_PAT.search(content):
        # Only include ones that are actually about cost/consumption, not just the word "token"
        if any(k in content for k in ['贵','消耗','费','烧','花','付','billed','cost','expensive','万 token','万token','亿token','亿 token','burn','爆']):
            sender = (m.get('sender') or {}).get('name','?')
            tok_hits.append({'ts': m.get('create_time',''), 'sender': sender,
                'content': content[:400].replace('\n',' ')})

md = ["# Token Consumption / Cost Complaints — Chinese Hermes Community", "",
    f"Total hits (keyword-filtered): {len(tok_hits):,}", "", "## Sample: 40 random hits", ""]
random.seed(1)
for h in random.sample(tok_hits, min(40, len(tok_hits))):
    md.append(f"- **{h['sender']}** ({h['ts']}): {h['content']}")

# Also pull Stream C pricing_complaints specifically about Hermes
hermes_cost = [i for i in facts['pricing_complaints']
    if isinstance(i.get('service'), str) and any(k in i['service'].lower() for k in ['hermes','爱马仕'])]
md += ["", "---", "",
    f"## Stream C: pricing_complaints specifically about Hermes ({len(hermes_cost)} incidents)", ""]
for i in hermes_cost:
    u = i.get('user_ref','?')
    s = i.get('service','?')
    iss = i.get('issue','?')
    md.append(f"- **{u}** ({s}): {iss}")

tok_out.write_text("\n".join(md), encoding='utf-8')
print(f"[b] wrote {tok_out} ({tok_out.stat().st_size // 1024} KB)", flush=True)

# =========================================================================
# (c) MESSAGING CSV
# =========================================================================
print("[c] messaging intent CSV...", flush=True)
csv_out = BASE / "post/messaging_intent.csv"
with csv_out.open('w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['chunk_idx', 'user_ref', 'platform', 'intent', 'context'])
    for i in facts['messaging_intent']:
        w.writerow([i.get('_chunk_idx',''), i.get('user_ref',''), i.get('platform',''),
            i.get('intent',''), i.get('context','')])
print(f"[c] wrote {csv_out} ({csv_out.stat().st_size // 1024} KB, {len(facts['messaging_intent'])} rows)", flush=True)

# Also CSV for other useful categories
for cat in ['install_problems','provider_usage','brand_confusion','feature_requests',
    'success_stories','pricing_complaints','api_key_sharing_evidence','competitor_mentions']:
    fp = BASE / f"post/{cat}.csv"
    items = facts[cat]
    if not items: continue
    all_keys = set()
    for it in items: all_keys.update(it.keys())
    keys = [k for k in all_keys if not k.startswith('_')] + ['_chunk_idx']
    with fp.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
        w.writeheader()
        for it in items:
            row = {k: (','.join(str(x) for x in it[k]) if isinstance(it.get(k), list) else it.get(k,''))
                for k in keys}
            w.writerow(row)
    print(f"[c] wrote {fp.name} ({len(items)} rows)", flush=True)

print("\n[a-c] all done, now preparing synthesis prompt...", flush=True)
