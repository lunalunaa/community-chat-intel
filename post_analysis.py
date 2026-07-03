#!/usr/bin/env python3
"""Post-analysis: brand audit, cost-complaint drill, messaging CSV exports.

BRAND_PATTERNS below is a worked EXAMPLE showing the pattern end-to-end
(official name + shadow-docs domains + colloquial slang + a list of
competitor products, each with their own aliases/slang). Replace every entry
with your own product's actual brand variants, impersonator domains, and
competitor slang — nothing here is meant to ship as-is.

PRODUCT_NAME (env var) is substituted into report headers/prompts so the
generated markdown doesn't hardcode a specific product.
"""
import json
import os
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(os.environ.get("OUT_DIR", "./out"))
CHAT = Path(os.environ.get("CHAT_JSONL", "./data/pages.jsonl"))
PRODUCT_NAME = os.environ.get("PRODUCT_NAME", "the product")

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
#    EXAMPLE patterns only — replace with your own product's brand/competitor map.
BRAND_PATTERNS = {
    "product_official":      r"example[-\s]?product|example-org",
    "shadow_docs_cluster":    r"shadow-docs\.example|unofficial-docs\.example",
    "clone_variant_a":       r"exampleclone|example[\s-]?clone",
    "clone_variant_b":       r"nanoexample|nano[\s-]?example",
    "cn_shadow_domain":       r"example-product\.(cn|org\.cn)|exampleproduct(ai)?",
    "colloquial_slang":       r"example昵称",
    "competitor_a_slang":     r"竞品甲|competitor[\s-]?a",
    "competitor_a_official":  r"competitor a product",
    "competitor_b":           r"competitor[\s-]?b",
    "competitor_c":           r"competitor[\s-]?c",
    "proxy_reseller_domains": r"example-proxy\.icu|example-reseller\.com",
}

counts = Counter()
samples = defaultdict(list)
cnt = 0
for line in CHAT.open():
    try:
        m = json.loads(line)
    except Exception:
        continue
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
md = [f"# Brand Audit — {PRODUCT_NAME} (Example Run)", "",
    "Scope: all non-system messages in the export, regex-matched against known brand patterns + newly-discovered impersonators",
    "", f"Corpus scanned: {cnt:,} non-system messages", "",
    "## Summary Counts", "",
    "| Brand / Variant | Message Count |", "|---|---:|"]
for b, c in counts.most_common():
    md.append(f"| `{b}` | {c:,} |")

md += ["", "## Key Observations (example commentary — replace with your own findings)", "",
    "- **Colloquial slang variants** often outnumber the official product name in casual chat — any sentiment analysis on the official name alone will undercount discussion volume.",
    "- **Shadow-docs domain clusters** (unofficial mirrors/re-hosts of documentation) are a common brand-confusion vector — treat any hit here as high-priority for verification.",
    "- **Newly-discovered clone/competitor names** surfaced via Stream C fact extraction that weren't in your original impersonator list are exactly the kind of finding this audit should catch — expand BRAND_PATTERNS whenever one turns up.",
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
# (b) TOKEN / COST CONSUMPTION DRILL
# =========================================================================
print("[b] cost consumption drill...", flush=True)
tok_out = BASE / "post/token_consumption.md"
TOK_PAT = re.compile(r'(token|消耗|costs?|费用|tokens?消耗|几十|几百|几千万|烧钱|太贵|expensive|太费|耗费|爆表|超出|超标|burn)', re.IGNORECASE)
AMT_PAT = re.compile(r'(\d+(?:\.\d+)?)\s*(?:万|千万|亿|k|m|千|百万|万亿)?\s*(?:token|美元|元|块|刀|rmb|\$|￥|¥)', re.IGNORECASE)

tok_hits = []
for line in CHAT.open():
    try: m = json.loads(line)
    except Exception: continue
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

md = [f"# Token Consumption / Cost Complaints — {PRODUCT_NAME}", "",
    f"Total hits (keyword-filtered): {len(tok_hits):,}", "", "## Sample: 40 random hits", ""]
random.seed(1)
for h in random.sample(tok_hits, min(40, len(tok_hits))):
    md.append(f"- **{h['sender']}** ({h['ts']}): {h['content']}")

# Also pull Stream C pricing_complaints specifically about this product
product_cost = [i for i in facts['pricing_complaints']
    if isinstance(i.get('service'), str) and PRODUCT_NAME.lower() in i['service'].lower()]
md += ["", "---", "",
    f"## Stream C: pricing_complaints specifically about {PRODUCT_NAME} ({len(product_cost)} incidents)", ""]
for i in product_cost:
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
