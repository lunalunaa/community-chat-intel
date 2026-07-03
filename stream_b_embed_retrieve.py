#!/usr/bin/env python3
"""Stream B: Local embeddings + retrieval queries.

Embeds all non-system messages with a multilingual model, builds a FAISS index,
runs structured retrieval queries, feeds top-K results to an LLM for synthesis.

Uses local sentence-transformers (no API) for embeddings; the LLM synthesis
step shells out to `hermes chat -q` so any configured provider/model works —
override via LLM_PROVIDER / LLM_MODEL env vars (defaults shown are just an
example; edit the `cmd` list below if your LLM CLI isn't named `hermes`).
"""
import json
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

CHAT_JSONL = Path(os.environ.get("CHAT_JSONL", "./data/pages.jsonl"))
OUT_DIR = Path(os.environ.get("OUT_DIR", "./out/stream_b"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

print("[stream_b] loading sentence-transformers...", flush=True)
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss

MODEL_NAME = "BAAI/bge-m3"  # best multilingual, supports zh/en dense retrieval
print(f"[stream_b] loading model: {MODEL_NAME}", flush=True)
model = SentenceTransformer(MODEL_NAME)

# ===== Load and prep messages =====
CHINA_TZ = timezone(timedelta(hours=8))
def parse_ts(s):
    if isinstance(s, str) and re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}', s):
        return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=CHINA_TZ).astimezone(timezone.utc)
    return None

print("[stream_b] loading messages...", flush=True)
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
    content = content.strip()
    if len(content) < 5:  # skip empty/trivial
        continue
    sender = m.get('sender') or {}
    messages.append({
        'id': m.get('message_id', ''),
        'content': content[:1500],  # embed first 1500 chars to stay in model ctx
        'ts': m.get('create_time', ''),
        'sender_name': sender.get('name', ''),
    })
print(f"[stream_b] {len(messages):,} messages to embed", flush=True)

# ===== Embed (or load cached) =====
emb_cache = OUT_DIR / "embeddings.npy"
ids_cache = OUT_DIR / "ids.json"

if emb_cache.exists() and ids_cache.exists():
    print(f"[stream_b] loading cached embeddings from {emb_cache}", flush=True)
    embs = np.load(str(emb_cache))
    cached_ids = json.loads(ids_cache.read_text())
    if cached_ids == [m['id'] for m in messages]:
        print("[stream_b] cache matches; skipping embed pass", flush=True)
    else:
        print("[stream_b] cache mismatch; re-embedding", flush=True)
        emb_cache = None
else:
    emb_cache = None

if emb_cache is None or not Path(emb_cache).exists():
    print("[stream_b] embedding... (this is the slow part, ~2-5 min on CPU)", flush=True)
    import time
    t0 = time.time()
    texts = [m['content'] for m in messages]
    embs = model.encode(texts, batch_size=32, show_progress_bar=True, convert_to_numpy=True,
                         normalize_embeddings=True)
    elapsed = time.time() - t0
    print(f"[stream_b] embedded {len(texts):,} messages in {elapsed:.0f}s ({len(texts)/elapsed:.0f}/s)", flush=True)
    np.save(str(OUT_DIR / "embeddings.npy"), embs.astype('float32'))
    (OUT_DIR / "ids.json").write_text(json.dumps([m['id'] for m in messages]))

# ===== Build FAISS index =====
print(f"[stream_b] building FAISS index (dim={embs.shape[1]})", flush=True)
index = faiss.IndexFlatIP(embs.shape[1])  # inner product == cosine on normalized vectors
index.add(embs.astype('float32'))

# ===== Retrieval queries =====
# Structured queries — EXAMPLE set for a generic AI-agent product. Replace the
# product name / feature names / competitor names with your own; the query
# *shape* (feature-adapter demand, gateway-vs-direct-API usage, brand
# confusion, pricing complaints, VPN friction, competitor comparison) is the
# reusable part.
QUERIES = {
    # Messaging-adapter demand
    "feishu_adapter_demand": "想要把这个产品接入飞书机器人，飞书 webhook，飞书对接",
    "feishu_actively_building": "我正在开发飞书集成，我写了一个飞书 adapter",
    "wechat_adapter_demand": "能不能接入微信，微信机器人，企业微信",
    "dingtalk_adapter_demand": "钉钉机器人，钉钉对接",
    # Gateway / hosted vs direct API
    "hosted_service_usage": "我在用官方托管服务，额度，门户",
    "direct_vendor_api_usage": "我直接用 kimi API，minimax API key，直接调 deepseek",
    "openrouter_usage": "openrouter 更便宜，通过 openrouter 用",
    "agent_key_sharing": "大家分享一下 sk-key，谁有 API key 能借用，合租",
    # Topic texture
    "install_friction": "安装不上，报错，无法运行，docker 启动失败",
    "brand_identity_confusion": "这是官方吗，是真的假的，哪个是官方网站",
    "pricing_complaints": "太贵了，免费额度用完，信用卡支付不了，限额",
    "vpn_friction": "被墙了，没法访问，需要翻墙，国内用不了",
    "success_stories": "我用这个做了，搭建了个智能体，跑起来了",
    "feature_requests": "希望能加上，我想要一个功能，建议增加",
    "core_feature_usage": "skill memory cron 怎么用，如何创建 skill",
    # Competitor sentiment
    "comparison_with_competitors": "对比竞品A, 比竞品B好，和竞品C区别",
    "comparison_with_alt_tools": "比claude code好，比codex强，比cursor",
    # Community hubs
    "mentions_of_external_communities": "我的微信公众号，关注我的知乎，B站视频教程",
}

print(f"[stream_b] running {len(QUERIES)} retrieval queries", flush=True)
TOP_K = 30
retrieval_out = {}
for query_name, query_text in QUERIES.items():
    q_emb = model.encode([query_text], normalize_embeddings=True, convert_to_numpy=True).astype('float32')
    D, I = index.search(q_emb, TOP_K)
    hits = []
    for rank, (idx, score) in enumerate(zip(I[0], D[0])):
        if idx == -1:
            continue
        m = messages[idx]
        hits.append({
            'rank': rank + 1,
            'score': float(score),
            'message_id': m['id'],
            'ts': m['ts'],
            'sender': m['sender_name'],
            'content': m['content'][:500],
        })
    retrieval_out[query_name] = {
        'query': query_text,
        'hits': hits,
    }
    print(f"  [{query_name}] top score={hits[0]['score']:.3f}  \"{hits[0]['content'][:60]}...\"", flush=True)

(OUT_DIR / "retrieval_results.json").write_text(json.dumps(retrieval_out, indent=2, ensure_ascii=False))
print(f"[stream_b] retrieval done → {OUT_DIR / 'retrieval_results.json'}", flush=True)

# ===== Kimi K2.6 synthesis for each query =====
print()
print("[stream_b] synthesizing findings with MiMo v2.5...", flush=True)

findings = {}
for query_name, data in retrieval_out.items():
    prompt_lines = [
        "You are analyzing a Chinese AI community chat. Below are the 30 most-relevant messages for this research query:",
        f"QUERY: {query_name}",
        f"QUERY_TEXT: {data['query']}",
        "",
        "MESSAGES (ranked by semantic similarity, highest first):",
    ]
    for h in data['hits']:
        prompt_lines.append(f"[{h['rank']}] (score={h['score']:.2f}) {h['content']}")
    prompt_lines += [
        "",
        "TASK: Write a concise 150-200 word English analysis answering what these messages collectively reveal about this topic. Quote message numbers in brackets as evidence (e.g., '[3]'). Be specific and factual. If signal is weak/ambiguous, say so explicitly. Do not pad.",
    ]
    prompt = "\n".join(prompt_lines)

    cmd = ["hermes", "chat", "-q", prompt, "--quiet", "--ignore-rules", "--ignore-user-config",
           "--max-turns", "1", "--source", "tool",
           "--provider", os.environ.get("LLM_PROVIDER", "nous"),
           "--model", os.environ.get("LLM_MODEL", "xiaomi/mimo-v2.5")]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=True)
        out = r.stdout
        # strip session_id line
        lines = out.split('\n')
        clean = '\n'.join(l for l in lines if not l.startswith('session_id:')).strip()
        findings[query_name] = {
            'query': data['query'],
            'analysis': clean,
            'source_count': len(data['hits']),
        }
        print(f"  ✓ {query_name} ({len(clean)} chars)", flush=True)
    except subprocess.TimeoutExpired:
        findings[query_name] = {'query': data['query'], 'analysis': '[TIMEOUT]', 'source_count': len(data['hits'])}
        print(f"  ✗ {query_name} timeout", flush=True)
    except subprocess.CalledProcessError as e:
        findings[query_name] = {'query': data['query'], 'analysis': f'[ERROR: {e.stderr[:200]}]', 'source_count': len(data['hits'])}
        print(f"  ✗ {query_name} error", flush=True)

(OUT_DIR / "synthesized_findings.json").write_text(json.dumps(findings, indent=2, ensure_ascii=False))

# Also write a readable markdown version
md_lines = ["# Stream B — Semantic Retrieval Findings", "",
    f"Corpus: {len(messages):,} messages embedded with {MODEL_NAME}, synthesized via LLM",
    f"Queries: {len(QUERIES)}", "",
    "---", ""]
for q, f in findings.items():
    md_lines += [f"## {q}", f"_Query: {f['query']}_", "",
        f"{f['analysis']}", "", "---", ""]
(OUT_DIR / "findings.md").write_text("\n".join(md_lines), encoding='utf-8')

print(f"[stream_b] DONE. {len(findings)} findings written to {OUT_DIR / 'findings.md'}", flush=True)
