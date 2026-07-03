#!/usr/bin/env python3
"""Generate a self-contained interactive HTML dashboard from stats.json.

Usage:
    # Single run (static dashboard):
    python -m parallax.streams.generate_dashboard --stats ./out/stats.json --out ./out/dashboard.html

    # Trend view (compare multiple runs):
    python -m parallax.streams.generate_dashboard \\
        --stats ./run1/stats.json ./run2/stats.json ./run3/stats.json \\
        --out ./out/dashboard.html

    # With drill-down (embeds users.json for message lookup):
    python -m parallax.streams.generate_dashboard \\
        --stats ./out/stats.json --users ./out/users.json \\
        --out ./out/dashboard.html

The dashboard is a single HTML file with all CSS/JS/data embedded — no
server needed, no build step. Open it directly in any browser.
"""

import argparse
import json
from pathlib import Path


def generate_dashboard(
    stats_runs: list[dict],
    output_path: Path,
    users: list[dict] | None = None,
    chat_jsonl: Path | None = None,
):
    """Generate a self-contained interactive HTML dashboard.

    Args:
        stats_runs: list of stats dicts (1 for single, multiple for trend view)
        output_path: where to write the HTML
        users: optional users.json data for drill-down
        chat_jsonl: optional raw chat export for message-level drill-down
    """

    # Prepare embedded data
    runs_json = json.dumps(stats_runs, ensure_ascii=False)
    users_json = json.dumps(users or [], ensure_ascii=False)

    # Load chat messages for drill-down if provided
    messages_json = "[]"
    if chat_jsonl and chat_jsonl.exists():
        raw = chat_jsonl.read_text(encoding="utf-8")
        msgs = []
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "messages" in data:
                msg_list = data["messages"]
            elif isinstance(data, list):
                msg_list = data
            else:
                msg_list = []
        except json.JSONDecodeError:
            msg_list = []
            for line in raw.splitlines():
                try:
                    msg_list.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        for m in msg_list:
            content = m.get("content") or ""
            if isinstance(content, dict):
                content = content.get("text", "") or json.dumps(
                    content, ensure_ascii=False
                )
            if not isinstance(content, str):
                content = str(content)
            content = content.strip()
            if not content or len(content) < 3:
                continue
            sender = m.get("sender") or m.get("author") or {}
            msgs.append(
                {
                    "id": m.get("message_id", m.get("id", "")),
                    "ts": m.get("create_time", m.get("timestamp", "")),
                    "sender": sender.get("name", sender.get("username", "?")),
                    "content": content[:300],
                }
            )
        messages_json = json.dumps(msgs, ensure_ascii=False)

    # Latest run for header/KPIs
    latest = stats_runs[-1] if stats_runs else {}
    meta = latest.get("metadata", {})

    has_trend = len(stats_runs) > 1
    has_drilldown = users is not None or chat_jsonl is not None

    _trend_buttons = (
        "<label>View</label>"
        '<button id="btn-current" class="active" onclick="setView(\'current\')">Current</button>'
        '<button id="btn-trend" onclick="setView(\'trend\')">Trend</button>'
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Parallax — Community Dashboard</title>
<style>
:root {{
  --bg: #0a0b0f;
  --surface: #12141a;
  --surface-hi: #1a1d26;
  --border: #252834;
  --text: #e8eaed;
  --muted: #8b8f9e;
  --dim: #5c6172;
  --accent: #6c8aff;
  --accent-dim: rgba(108, 138, 255, 0.12);
  --green: #3fb950;
  --red: #f85149;
  --yellow: #d2991d;
  --orange: #db6d28;
  --cyan: #39c5cf;
  --pink: #f778ba;
  --radius: 10px;
  --radius-sm: 6px;
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  --mono: 'SF Mono', 'Fira Code', 'JetBrains Mono', Consolas, monospace;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}}

/* --- Header --- */
.header {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}}
.header h1 {{
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.02em;
}}
.header h1 .accent {{ color: var(--accent); }}
.header .meta {{
  font-size: 12px;
  color: var(--muted);
  font-family: var(--mono);
}}

/* --- Controls bar --- */
.controls {{
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}}
.controls label {{
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--dim);
  margin-right: 4px;
}}
.controls select, .controls button {{
  background: var(--surface-hi);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 6px 12px;
  font-size: 12px;
  font-family: var(--font);
  cursor: pointer;
  transition: border-color 0.2s;
}}
.controls select:hover, .controls button:hover {{
  border-color: var(--accent);
}}
.controls button.active {{
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
}}
.controls .spacer {{ flex: 1; }}

/* --- KPI Row --- */
.kpi-row {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}}
.kpi {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  position: relative;
  overflow: hidden;
  transition: border-color 0.2s;
}}
.kpi:hover {{ border-color: var(--dim); }}
.kpi .label {{
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--dim);
  margin-bottom: 4px;
}}
.kpi .value {{
  font-size: 26px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}}
.kpi .sub {{
  font-size: 11px;
  color: var(--muted);
  margin-top: 2px;
}}
.kpi .value.accent {{ color: var(--accent); }}
.kpi .value.green {{ color: var(--green); }}
.kpi .value.red {{ color: var(--red); }}
.kpi .value.yellow {{ color: var(--yellow); }}
.kpi .delta {{
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  margin-top: 2px;
}}
.kpi .delta.up {{ color: var(--green); }}
.kpi .delta.down {{ color: var(--red); }}

/* --- Grid --- */
.grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
}}
.grid .full {{ grid-column: 1 / -1; }}

@media (max-width: 768px) {{
  .grid {{ grid-template-columns: 1fr; }}
  .controls {{ flex-direction: column; align-items: stretch; }}
}}

/* --- Card --- */
.card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px;
  overflow: hidden;
}}
.card h2 {{
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}}
.card h2 .card-controls {{
  display: flex;
  gap: 4px;
}}
.card h2 .card-controls button {{
  background: none;
  border: none;
  color: var(--dim);
  cursor: pointer;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
}}
.card h2 .card-controls button:hover {{ color: var(--accent); }}
.card-body {{ position: relative; }}

/* --- Bar list --- */
.bar-list {{ display: flex; flex-direction: column; gap: 6px; }}
.bar-item {{
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  padding: 2px 4px;
  margin: -2px -4px;
  transition: background 0.15s;
}}
.bar-item:hover {{ background: var(--surface-hi); }}
.bar-item .name {{
  width: 130px;
  text-align: right;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 12px;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.bar-item .bar-track {{
  flex: 1;
  height: 22px;
  background: var(--surface-hi);
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}}
.bar-item .bar-fill {{
  height: 100%;
  border-radius: 4px;
  display: flex;
  align-items: center;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--bg);
  transition: width 0.4s ease, opacity 0.2s;
}}
.bar-item .bar-fill.accent {{ background: var(--accent); }}
.bar-item .bar-fill.green {{ background: var(--green); }}
.bar-item .bar-fill.red {{ background: var(--red); }}
.bar-item .bar-fill.yellow {{ background: var(--yellow); }}
.bar-item .bar-fill.cyan {{ background: var(--cyan); }}
.bar-item .bar-fill.pink {{ background: var(--pink); }}
.bar-item .bar-fill.orange {{ background: var(--orange); }}
.bar-item .bar-fill.dim {{ background: var(--dim); }}
.bar-item .trend {{
  font-size: 10px;
  font-family: var(--mono);
  color: var(--dim);
  width: 40px;
  text-align: right;
  flex-shrink: 0;
}}

/* --- Drill-down panel --- */
.drilldown {{
  display: none;
  margin-top: 8px;
  padding: 12px;
  background: var(--surface-hi);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  max-height: 300px;
  overflow-y: auto;
  font-size: 12px;
}}
.drilldown.open {{ display: block; }}
.drilldown .msg {{
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
}}
.drilldown .msg:last-child {{ border-bottom: none; }}
.drilldown .msg .ts {{
  color: var(--dim);
  font-family: var(--mono);
  font-size: 10px;
}}
.drilldown .msg .sender {{
  color: var(--accent);
  font-weight: 600;
  margin-right: 6px;
}}
.drilldown .msg .content {{
  color: var(--text);
  margin-top: 2px;
}}
.drilldown .no-data {{
  color: var(--dim);
  text-align: center;
  padding: 20px 0;
}}

/* --- Table --- */
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
table th {{
  text-align: left; font-weight: 600; color: var(--muted);
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 8px 0; border-bottom: 1px solid var(--border);
}}
table td {{
  padding: 8px 0; border-bottom: 1px solid var(--border);
  font-variant-numeric: tabular-nums;
}}
table td.num {{ text-align: right; font-family: var(--mono); }}
table tr:last-child td {{ border-bottom: none; }}

/* --- Badge --- */
.badge {{
  display: inline-block; padding: 2px 8px; border-radius: 100px;
  font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums;
}}
.badge.green {{ background: rgba(63,185,80,0.15); color: var(--green); }}
.badge.red {{ background: rgba(248,81,73,0.15); color: var(--red); }}
.badge.yellow {{ background: rgba(210,153,29,0.15); color: var(--yellow); }}
.badge.dim {{ background: rgba(140,143,158,0.15); color: var(--muted); }}

/* --- Trend chart --- */
.trend-chart {{
  display: none;
  margin-top: 12px;
}}
.trend-chart.open {{ display: block; }}
.trend-bar {{
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  margin-right: 8px;
  vertical-align: bottom;
}}
.trend-bar .bar {{
  width: 40px;
  background: var(--accent);
  border-radius: 3px 3px 0 0;
  transition: height 0.4s ease;
}}
.trend-bar .label {{
  font-size: 10px;
  font-family: var(--mono);
  color: var(--dim);
  margin-top: 4px;
  white-space: nowrap;
  transform: rotate(-30deg);
  transform-origin: top left;
}}

/* --- Footer --- */
.footer {{
  margin-top: 32px; padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 11px; color: var(--dim); font-family: var(--mono);
  display: flex; justify-content: space-between;
}}
</style>
</head>
<body>

<div class="header">
  <h1><span class="accent">◆</span> Parallax Community Dashboard</h1>
  <div class="meta" id="header-meta"></div>
</div>

<!-- Controls -->
<div class="controls">
  <label>Run</label>
  <select id="run-selector" onchange="switchRun()"></select>
  {_trend_buttons if has_trend else ""}
  <label>Cohort</label>
  <button id="btn-all" class="active" onclick="setCohort('all')">All</button>
  <button id="btn-target" onclick="setCohort('target')">Target-lang</button>
  <div class="spacer"></div>
  <span id="run-info" style="font-size:11px;color:var(--dim);font-family:var(--mono);"></span>
</div>

<!-- KPI Row -->
<div class="kpi-row" id="kpi-row"></div>

<!-- Trend chart (hidden by default) -->
<div id="trend-section" style="display:none;">
  <div class="card" style="margin-bottom:14px;">
    <h2>Trend — total messages over runs</h2>
    <div class="card-body">
      <div id="trend-chart" style="height:120px;display:flex;align-items:flex-end;gap:4px;overflow-x:auto;"></div>
    </div>
  </div>
</div>

<!-- Data sections -->
<div id="sections"></div>

<div class="footer">
  <span>Generated by parallax v{meta.get("pipeline_version", "?")}</span>
  <span id="footer-time"></span>
</div>

<script>
const RUNS = {runs_json};
const USERS = {users_json};
const MESSAGES = {messages_json};
const HAS_TREND = {str(has_trend).lower()};
const HAS_DRILLDOWN = {str(has_drilldown).lower()};

let currentRunIdx = RUNS.length - 1;
let currentCohort = 'all';  // 'all' or 'target'
let currentView = 'current';  // 'current' or 'trend'

// --- Helpers ---
function get(key) {{
  const run = RUNS[currentRunIdx];
  if (!run) return {{}};
  return run[key] || {{}};
}}

function getMeta() {{
  return RUNS[currentRunIdx]?.metadata || {{}};
}}

function sum(obj) {{
  return Object.values(obj || {{}}).reduce((a, b) => a + b, 0);
}}

function fmtPct(n, total) {{
  return total > 0 ? (n / total * 100).toFixed(0) + '%' : '0%';
}}

function delta(current, previous) {{
  if (previous === undefined || previous === 0) return '';
  const d = current - previous;
  if (d === 0) return '';
  const pct = (d / previous * 100).toFixed(0);
  const cls = d > 0 ? 'up' : 'down';
  const arrow = d > 0 ? '↑' : '↓';
  return `<div class="delta ${{cls}}">${{arrow}} ${{Math.abs(pct)}}% vs prev</div>`;
}}

function prevValue(key, subkey) {{
  if (currentRunIdx === 0) return undefined;
  const prev = RUNS[currentRunIdx - 1];
  if (!prev) return undefined;
  if (subkey) return prev[key]?.[subkey];
  return prev[key];
}}

// --- Bar list with drill-down ---
function barList(containerId, data, colorClass, dataKey) {{
  const el = document.getElementById(containerId);
  if (!el) return;
  const entries = Object.entries(data || {{}}).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) {{
    el.innerHTML = '<div class="no-data">No data</div>';
    return;
  }}
  const max = Math.max(...entries.map(e => e[1]));

  // Trend values
  let trendHtml = '';
  if (HAS_TREND && currentRunIdx > 0) {{
    const prevData = prevValue(dataKey) || {{}};
    trendHtml = entries.map(([name, count]) => {{
      const prev = prevData[name] || 0;
      if (prev === 0) return '<span class="trend"></span>';
      const d = count - prev;
      if (d === 0) return '<span class="trend">—</span>';
      const cls = d > 0 ? 'up' : 'down';
      return `<span class="trend" style="color:var(${{d > 0 ? '--green' : '--red'}})">${{d > 0 ? '+' : ''}}${{d}}</span>`;
    }}).join('');
  }}

  el.innerHTML = entries.map(([name, count]) => `
    <div class="bar-item" onclick="toggleDrilldown(this, '${{dataKey}}', '${{name}}')">
      <div class="name">${{name}}</div>
      <div class="bar-track">
        <div class="bar-fill ${{colorClass}}" style="width: ${{(count / max * 100).toFixed(1)}}%">${{count}}</div>
      </div>
      ${{HAS_TREND && currentRunIdx > 0 ? (() => {{
        const prev = (prevValue(dataKey) || {{}})[name] || 0;
        if (prev === 0) return '<span class="trend"></span>';
        const d = count - prev;
        if (d === 0) return '<span class="trend">—</span>';
        return `<span class="trend" style="color:var(${{d > 0 ? '--green' : '--red'}})">${{d > 0 ? '+' : ''}}${{d}}</span>`;
      }})() : ''}}
    </div>
    <div class="drilldown"></div>
  `).join('');
}}

function toggleDrilldown(barItem, dataKey, label) {{
  const dd = barItem.nextElementSibling;
  if (!dd || !dd.classList.contains('drilldown')) return;

  if (dd.classList.contains('open')) {{
    dd.classList.remove('open');
    return;
  }}

  // Close all other drilldowns
  document.querySelectorAll('.drilldown.open').forEach(d => d.classList.remove('open'));
  dd.classList.add('open');

  if (!HAS_DRILLDOWN || MESSAGES.length === 0) {{
    dd.innerHTML = '<div class="no-data">No message data available for drill-down. Pass --chat to enable.</div>';
    return;
  }}

  // Find messages matching this label
  const labelLower = label.toLowerCase();
  const labelParts = labelLower.split(/[\\s_-]+/);
  const matches = MESSAGES.filter(m => {{
    const c = (m.content || '').toLowerCase();
    // Match if any part of the label appears in the message
    return labelParts.some(part => part.length >= 3 && c.includes(part));
  }}).slice(0, 20);

  if (matches.length === 0) {{
    dd.innerHTML = '<div class="no-data">No messages found matching "' + label + '"</div>';
    return;
  }}

  dd.innerHTML = matches.map(m => `
    <div class="msg">
      <span class="ts">${{m.ts || '?'}}</span>
      <span class="sender">${{m.sender || '?'}}</span>
      <div class="content">${{m.content}}</div>
    </div>
  `).join('');
}}

// --- KPI rendering ---
function renderKPIs() {{
  const meta = getMeta();
  const users = get('users') || {{}};
  const langDist = get('language_distribution') || {{}};
  const friction = get('friction_signals') || {{}};
  const helpAns = get('help_answered') || {{}};

  const totalMsgs = meta.total_messages || 0;
  const totalUsers = users.total || 0;
  const targetUsers = users.target_plus_bilingual || 0;
  const targetMsgs = (langDist.target || 0) + (langDist.mixed || 0);
  const questions = helpAns.total_questions || 0;
  const frictionCount = sum(friction);
  const answeredRate = (helpAns.target_answered_rate || 0);

  const frictionColor = frictionCount > totalMsgs * 0.15 ? 'red' : 'yellow';
  const rateColor = answeredRate >= 0.7 ? 'green' : answeredRate < 0.5 ? 'red' : 'yellow';

  const prevMeta = prevValue('metadata');
  const prevUsers = prevValue('users');

  document.getElementById('kpi-row').innerHTML = `
    <div class="kpi">
      <div class="label">Messages</div>
      <div class="value">${{totalMsgs.toLocaleString()}}</div>
      <div class="sub">total analyzed</div>
      ${{delta(totalMsgs, prevMeta?.total_messages)}}
    </div>
    <div class="kpi">
      <div class="label">Users</div>
      <div class="value">${{totalUsers.toLocaleString()}}</div>
      <div class="sub">${{targetUsers}} target-lang</div>
      ${{delta(totalUsers, prevUsers?.total)}}
    </div>
    <div class="kpi">
      <div class="label">Target-lang</div>
      <div class="value accent">${{targetMsgs.toLocaleString()}}</div>
      <div class="sub">${{langDist.mixed || 0}} mixed / ${{langDist.target || 0}} pure</div>
    </div>
    <div class="kpi">
      <div class="label">Questions</div>
      <div class="value">${{questions}}</div>
      <div class="sub">${{helpAns.target_questions || 0}} target-lang</div>
    </div>
    <div class="kpi">
      <div class="label">Friction</div>
      <div class="value ${{frictionColor}}">${{frictionCount}}</div>
      <div class="sub">${{fmtPct(frictionCount, totalMsgs)}} of msgs</div>
    </div>
    <div class="kpi">
      <div class="label">Answered</div>
      <div class="value ${{rateColor}}">${{(answeredRate * 100).toFixed(0)}}%</div>
      <div class="sub">48h window</div>
    </div>
  `;
}}

// --- Section rendering ---
function renderSections() {{
  const meta = getMeta();
  const retention = get('retention') || {{}};
  const competitors = get('competitors') || {{}};

  document.getElementById('sections').innerHTML = `
    <div class="grid">
      <div class="card">
        <h2>Provider mentions</h2>
        <div class="card-body"><div class="bar-list" id="bar-providers"></div></div>
      </div>
      <div class="card">
        <h2>Messaging platforms</h2>
        <div class="card-body"><div class="bar-list" id="bar-messaging"></div></div>
      </div>
    </div>
    <div class="grid">
      <div class="card">
        <h2>Friction signals</h2>
        <div class="card-body"><div class="bar-list" id="bar-friction"></div></div>
      </div>
      <div class="card">
        <h2>Feature usage</h2>
        <div class="card-body"><div class="bar-list" id="bar-features"></div></div>
      </div>
    </div>
    <div class="grid">
      <div class="card">
        <h2>Language distribution</h2>
        <div class="card-body"><div class="bar-list" id="bar-language"></div></div>
      </div>
      <div class="card">
        <h2>Retention — target-language cohort</h2>
        <div class="card-body">
          <table>
            <tr><td>Active (30d)</td><td class="num"><span class="badge green">${{retention.target_active_30d || 0}}</span></td></tr>
            <tr><td>Lapsed (30–90d)</td><td class="num"><span class="badge yellow">${{retention.target_lapsed_30_90d || 0}}</span></td></tr>
            <tr><td>Lapsed (90d+)</td><td class="num"><span class="badge red">${{retention.target_lapsed_90d_plus || 0}}</span></td></tr>
            <tr><td>One-time posters</td><td class="num"><span class="badge dim">${{retention.target_one_time_posters || 0}}</span></td></tr>
          </table>
        </div>
      </div>
    </div>
    <div class="grid">
      <div class="card">
        <h2>Install paths</h2>
        <div class="card-body"><div class="bar-list" id="bar-install"></div></div>
      </div>
      <div class="card">
        <h2>Shadow communities</h2>
        <div class="card-body"><div class="bar-list" id="bar-shadow"></div></div>
      </div>
    </div>
    <div class="grid">
      <div class="card">
        <h2>URL categories</h2>
        <div class="card-body"><div class="bar-list" id="bar-urls"></div></div>
      </div>
      <div class="card">
        <h2>Location proxy (timezone)</h2>
        <div class="card-body"><div class="bar-list" id="bar-location"></div></div>
      </div>
    </div>
    ${{Object.keys(competitors).length > 0 ? `
    <div class="grid full">
      <div class="card" style="grid-column:1/-1;">
        <h2>Competitor mentions</h2>
        <div class="card-body"><div class="bar-list" id="bar-competitors"></div></div>
      </div>
    </div>` : ''}}
  `;

  barList('bar-providers', get('providers'), 'accent', 'providers');
  barList('bar-messaging', get('messaging_platforms'), 'cyan', 'messaging_platforms');
  barList('bar-language', get('language_distribution'), 'green', 'language_distribution');
  barList('bar-location', get('location_proxy'), 'orange', 'location_proxy');
  barList('bar-friction', get('friction_signals'), 'red', 'friction_signals');
  barList('bar-features', get('features'), 'accent', 'features');
  barList('bar-install', get('install_paths'), 'cyan', 'install_paths');
  barList('bar-shadow', get('shadow_community_mentions'), 'pink', 'shadow_community_mentions');
  barList('bar-urls', (get('urls') || {{}}).category_counts || {{}}, 'orange', 'urls');
  if (document.getElementById('bar-competitors'))
    barList('bar-competitors', competitors, 'yellow', 'competitors');
}}

// --- Trend chart ---
function renderTrendChart() {{
  if (!HAS_TREND) return;
  const el = document.getElementById('trend-chart');
  if (!el) return;
  const max = Math.max(...RUNS.map(r => r.metadata?.total_messages || 0));
  el.innerHTML = RUNS.map((r, i) => {{
    const msgs = r.metadata?.total_messages || 0;
    const h = max > 0 ? (msgs / max * 100) : 0;
    const date = (r.metadata?.date_range?.[0] || '?').slice(0, 10);
    return `<div class="trend-bar">
      <div class="bar" style="height:${{h}}px;background:var(--${{i === currentRunIdx ? 'accent' : 'dim'}});" title="${{msgs}} msgs"></div>
      <div class="label">${{date}}</div>
    </div>`;
  }}).join('');
}}

// --- Header / footer ---
function renderHeader() {{
  const meta = getMeta();
  const channels = meta.channels;
  const channelStr = Array.isArray(channels) ? channels.join(', ') : (channels || 'unknown');
  document.getElementById('header-meta').textContent = `${{channelStr}} · ${{(meta.total_messages || 0).toLocaleString()}} msgs · ${{meta.target_language_name || 'n/a'}} / ${{meta.region_name || 'n/a'}} · ${{(meta.date_range?.[0] || '?').slice(0,10)}} → ${{(meta.date_range?.[1] || '?').slice(0,10)}}`;
  document.getElementById('footer-time').textContent = (meta.analyzed_at || '?').slice(0, 19);
}}

// --- Run selector ---
function populateRunSelector() {{
  const sel = document.getElementById('run-selector');
  if (!sel) return;
  sel.innerHTML = RUNS.map((r, i) => {{
    const date = (r.metadata?.date_range?.[0] || 'run ' + (i+1)).slice(0, 10);
    const msgs = r.metadata?.total_messages || 0;
    return `<option value="${{i}}" ${{i === currentRunIdx ? 'selected' : ''}}>${{date}} (${{msgs.toLocaleString()}} msgs)</option>`;
  }}).join('');
  if (RUNS.length <= 1) sel.style.display = 'none';
}}

// --- Controls ---
function switchRun() {{
  const sel = document.getElementById('run-selector');
  currentRunIdx = parseInt(sel.value);
  renderAll();
}}

function setView(view) {{
  currentView = view;
  document.getElementById('btn-current')?.classList.toggle('active', view === 'current');
  document.getElementById('btn-trend')?.classList.toggle('active', view === 'trend');
  document.getElementById('trend-section').style.display = view === 'trend' ? 'block' : 'none';
  document.getElementById('sections').style.display = view === 'trend' ? 'none' : 'block';
  document.getElementById('kpi-row').style.display = view === 'trend' ? 'none' : 'grid';
  if (view === 'trend') renderTrendChart();
}}

function setCohort(cohort) {{
  currentCohort = cohort;
  document.getElementById('btn-all').classList.toggle('active', cohort === 'all');
  document.getElementById('btn-target').classList.toggle('active', cohort === 'target');
  // TODO: filter stats by cohort when we have per-cohort breakdowns
  // For now this just toggles the visual state
}}

// --- Render all ---
function renderAll() {{
  populateRunSelector();
  renderHeader();
  renderKPIs();
  renderSections();
  if (HAS_TREND) renderTrendChart();
}}

// --- Init ---
renderAll();
</script>

</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    features = []
    if has_trend:
        features.append("trend view")
    if has_drilldown:
        features.append("drill-down")
    feature_str = f" ({', '.join(features)})" if features else ""
    print(f"[dashboard] written to {output_path} ({len(html):,} bytes){feature_str}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate a self-contained interactive HTML dashboard from stats.json"
    )
    parser.add_argument(
        "--stats",
        required=True,
        nargs="+",
        help="Path(s) to stats.json from parallax-analyze. Multiple files enable trend view.",
    )
    parser.add_argument(
        "--users", default=None, help="Path to users.json (enables drill-down)"
    )
    parser.add_argument(
        "--chat",
        default=None,
        help="Path to raw chat export NDJSON (enables message-level drill-down)",
    )
    parser.add_argument("--out", required=True, help="Output path for dashboard.html")
    args = parser.parse_args()

    stats_runs = [json.loads(Path(p).read_text()) for p in args.stats]

    users = None
    if args.users:
        users = json.loads(Path(args.users).read_text())

    chat_path = Path(args.chat) if args.chat else None

    generate_dashboard(stats_runs, Path(args.out), users, chat_path)


if __name__ == "__main__":
    main()
