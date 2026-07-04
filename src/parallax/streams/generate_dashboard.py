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
        --chat ./out/export.json --out ./out/dashboard.html

The dashboard is a single HTML file with all CSS/JS/data embedded — no
server needed, no build step. Open it directly in any browser.

Design inspired by magicui.design: bento grid, number ticker animation,
gradient bar fills, SVG trend chart, shine borders, blur fade-in,
auto-generated insights summary.
"""

import argparse
import json
from pathlib import Path

# --- CSS ---
_CSS = """
:root {
  --bg: #0a0b0f;
  --surface: rgba(18, 20, 26, 0.85);
  --surface-hi: #1a1d26;
  --border: #252834;
  --text: #e8eaed;
  --muted: #8b8f9e;
  --dim: #5c6172;
  --accent: #6c8aff;
  --accent-glow: rgba(108, 138, 255, 0.25);
  --green: #3fb950;
  --green-glow: rgba(63, 185, 80, 0.2);
  --red: #f85149;
  --red-glow: rgba(248, 81, 73, 0.2);
  --yellow: #d2991d;
  --orange: #db6d28;
  --cyan: #39c5cf;
  --pink: #f778ba;
  --radius: 12px;
  --radius-sm: 6px;
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  --mono: 'SF Mono', 'Fira Code', 'JetBrains Mono', Consolas, monospace;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}
/* --- Header --- */
.header {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 16px; flex-wrap: wrap; gap: 12px;
}
.header h1 { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; }
.header h1 .accent { background: linear-gradient(135deg, var(--accent), var(--cyan)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.header .meta { font-size: 12px; color: var(--muted); font-family: var(--mono); }
/* --- Insights bar --- */
.insights {
  display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap;
}
.insight-pill {
  padding: 6px 14px; border-radius: 100px; font-size: 12px; font-weight: 500;
  background: var(--surface); border: 1px solid var(--border);
  backdrop-filter: blur(8px); display: flex; align-items: center; gap: 6px;
  animation: fadeIn 0.5s ease forwards; opacity: 0;
}
.insight-pill .dot { width: 6px; height: 6px; border-radius: 50%; }
.insight-pill .dot.red { background: var(--red); box-shadow: 0 0 6px var(--red); }
.insight-pill .dot.green { background: var(--green); box-shadow: 0 0 6px var(--green); }
.insight-pill .dot.yellow { background: var(--yellow); box-shadow: 0 0 6px var(--yellow); }
.insight-pill .dot.accent { background: var(--accent); box-shadow: 0 0 6px var(--accent); }
/* --- Controls --- */
.controls {
  display: flex; align-items: center; gap: 12px; margin-bottom: 20px; flex-wrap: wrap;
  padding: 12px 16px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); backdrop-filter: blur(8px);
}
.controls label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--dim); }
.controls select, .controls button {
  background: var(--surface-hi); color: var(--text); border: 1px solid var(--border);
  border-radius: var(--radius-sm); padding: 6px 12px; font-size: 12px; cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.controls select:hover, .controls button:hover { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
.controls button.active { background: var(--accent-glow); border-color: var(--accent); color: var(--accent); }
.controls .spacer { flex: 1; }
/* --- KPI Row --- */
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 20px; }
.kpi {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 16px 18px; position: relative; overflow: hidden; backdrop-filter: blur(8px);
  transition: border-color 0.2s, box-shadow 0.2s; animation: fadeInBlur 0.5s ease forwards; opacity: 0;
}
.kpi:hover { border-color: var(--dim); }
.kpi.glow-accent { box-shadow: 0 0 20px var(--accent-glow); }
.kpi.glow-red { box-shadow: 0 0 20px var(--red-glow); }
.kpi.glow-green { box-shadow: 0 0 20px var(--green-glow); }
.kpi .label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--dim); margin-bottom: 4px; }
.kpi .value { font-size: 28px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
.kpi .value.accent { background: linear-gradient(135deg, var(--accent), var(--cyan)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.kpi .value.green { color: var(--green); }
.kpi .value.red { color: var(--red); }
.kpi .value.yellow { color: var(--yellow); }
.kpi .sub { font-size: 11px; color: var(--muted); margin-top: 2px; }
.kpi .delta { font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; margin-top: 2px; }
.kpi .delta.up { color: var(--green); }
.kpi .delta.down { color: var(--red); }
/* --- Bento Grid --- */
.bento {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 14px;
}
.bento .span-2 { grid-column: span 2; }
.bento .span-4 { grid-column: span 4; }
@media (max-width: 1024px) { .bento { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 640px) { .bento { grid-template-columns: 1fr; } .bento .span-2, .bento .span-4 { grid-column: span 1; } }
/* --- Card --- */
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 18px; overflow: hidden; backdrop-filter: blur(8px); position: relative;
  animation: fadeInBlur 0.5s ease forwards; opacity: 0;
}
.card.glow-red { box-shadow: 0 0 16px var(--red-glow); }
.card.glow-accent { box-shadow: 0 0 16px var(--accent-glow); }
.card.glow-green { box-shadow: 0 0 16px var(--green-glow); }
/* Shine border */
.card.shine::before {
  content: ''; position: absolute; inset: 0; border-radius: var(--radius); padding: 1px;
  background: conic-gradient(from var(--shine-angle, 0deg), transparent 0%, var(--accent) 10%, transparent 20%);
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor; mask-composite: exclude;
  animation: shine 4s linear infinite; pointer-events: none;
}
@property --shine-angle { syntax: '<angle>'; initial-value: 0deg; inherits: false; }
@keyframes shine { to { --shine-angle: 360deg; } }
.card h2 {
  font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--muted); margin-bottom: 12px;
}
.card-body { position: relative; }
/* --- Bar list --- */
.bar-list { display: flex; flex-direction: column; gap: 6px; }
.bar-item {
  display: flex; align-items: center; gap: 10px; font-size: 13px; cursor: pointer;
  border-radius: var(--radius-sm); padding: 2px 4px; margin: -2px -4px; transition: background 0.15s;
}
.bar-item:hover { background: var(--surface-hi); }
.bar-item .name {
  width: 120px; text-align: right; color: var(--muted); font-family: var(--mono);
  font-size: 12px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.bar-item .bar-track {
  flex: 1; height: 24px; background: var(--surface-hi); border-radius: 6px; overflow: hidden; position: relative;
}
.bar-item .bar-fill {
  height: 100%; border-radius: 6px; display: flex; align-items: center; padding: 0 8px;
  font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--bg);
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}
.bar-fill.accent { background: linear-gradient(90deg, var(--accent), #8a9aff); }
.bar-fill.green { background: linear-gradient(90deg, var(--green), #5fcc6e); }
.bar-fill.red { background: linear-gradient(90deg, var(--red), #ff6b5e); }
.bar-fill.yellow { background: linear-gradient(90deg, var(--yellow), #e0a82a); }
.bar-fill.cyan { background: linear-gradient(90deg, var(--cyan), #4ed4dd); }
.bar-fill.pink { background: linear-gradient(90deg, var(--pink), #ff8ac4); }
.bar-fill.orange { background: linear-gradient(90deg, var(--orange), #ed7d3a); }
.bar-item .trend { font-size: 10px; font-family: var(--mono); color: var(--dim); width: 40px; text-align: right; flex-shrink: 0; }
/* --- Drill-down --- */
.drilldown {
  display: none; margin-top: 8px; padding: 12px; background: var(--surface-hi);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  max-height: 280px; overflow-y: auto; font-size: 12px;
}
.drilldown.open { display: block; animation: fadeIn 0.2s ease; }
.drilldown .msg { padding: 6px 0; border-bottom: 1px solid var(--border); }
.drilldown .msg:last-child { border-bottom: none; }
.drilldown .msg .ts { color: var(--dim); font-family: var(--mono); font-size: 10px; }
.drilldown .msg .sender { color: var(--accent); font-weight: 600; margin-right: 6px; }
.drilldown .msg .content { color: var(--text); margin-top: 2px; }
.drilldown .no-data { color: var(--dim); text-align: center; padding: 20px 0; }
/* --- Table --- */
table { width: 100%; border-collapse: collapse; font-size: 13px; }
table th { text-align: left; font-weight: 600; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; padding: 8px 0; border-bottom: 1px solid var(--border); }
table td { padding: 8px 0; border-bottom: 1px solid var(--border); font-variant-numeric: tabular-nums; }
table td.num { text-align: right; font-family: var(--mono); }
table tr:last-child td { border-bottom: none; }
/* --- Badge --- */
.badge { display: inline-block; padding: 2px 8px; border-radius: 100px; font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; }
.badge.green { background: rgba(63,185,80,0.15); color: var(--green); }
.badge.red { background: rgba(248,81,73,0.15); color: var(--red); }
.badge.yellow { background: rgba(210,153,29,0.15); color: var(--yellow); }
.badge.dim { background: rgba(140,143,158,0.15); color: var(--muted); }
/* --- Trend chart (SVG) --- */
.trend-svg { width: 100%; height: 200px; }
.trend-svg .grid line { stroke: var(--border); stroke-width: 0.5; }
.trend-svg .bar { transition: opacity 0.2s; cursor: pointer; }
.trend-svg .bar:hover { opacity: 0.8; }
.trend-svg .bar-label { fill: var(--muted); font-size: 10px; font-family: var(--mono); }
.trend-svg .bar-value { fill: var(--text); font-size: 12px; font-weight: 600; font-family: var(--mono); text-anchor: middle; }
/* --- Footer --- */
.footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--border); font-size: 11px; color: var(--dim); font-family: var(--mono); display: flex; justify-content: space-between; }
/* --- Animations --- */
@keyframes fadeIn { to { opacity: 1; } }
@keyframes fadeInBlur { from { opacity: 0; filter: blur(8px); } to { opacity: 1; filter: blur(0); } }
.kpi:nth-child(1) { animation-delay: 0.05s; }
.kpi:nth-child(2) { animation-delay: 0.1s; }
.kpi:nth-child(3) { animation-delay: 0.15s; }
.kpi:nth-child(4) { animation-delay: 0.2s; }
.kpi:nth-child(5) { animation-delay: 0.25s; }
.kpi:nth-child(6) { animation-delay: 0.3s; }
"""


# --- JS ---
_JS = """
const RUNS = __RUNS_JSON__;
const USERS = __USERS_JSON__;
const MESSAGES = __MESSAGES_JSON__;
const HAS_TREND = __HAS_TREND__;
const HAS_DRILLDOWN = __HAS_DRILLDOWN__;

let currentRunIdx = RUNS.length - 1;
let currentCohort = 'all';
let currentView = 'current';

function get(key) { const run = RUNS[currentRunIdx]; return run ? (run[key] || {}) : {}; }
function getMeta() { return RUNS[currentRunIdx]?.metadata || {}; }
function sum(obj) { return Object.values(obj || {}).reduce((a, b) => a + b, 0); }
function fmtPct(n, total) { return total > 0 ? (n / total * 100).toFixed(0) + '%' : '0%'; }
function delta(current, previous) {
  if (previous === undefined || previous === 0) return '';
  const d = current - previous;
  if (d === 0) return '';
  const pct = (d / previous * 100).toFixed(0);
  const cls = d > 0 ? 'up' : 'down';
  const arrow = d > 0 ? '\u2191' : '\u2193';
  return '<div class="delta ' + cls + '">' + arrow + ' ' + Math.abs(pct) + '% vs prev</div>';
}
function prevValue(key, subkey) {
  if (currentRunIdx === 0) return undefined;
  const prev = RUNS[currentRunIdx - 1];
  if (!prev) return undefined;
  if (subkey) return prev[key]?.[subkey];
  return prev[key];
}

// --- Number ticker ---
function animateValue(el, target, duration) {
  const start = 0;
  const startTime = performance.now();
  function update(now) {
    const elapsed = (now - startTime) / duration;
    if (elapsed >= 1) { el.textContent = target.toLocaleString(); return; }
    const eased = 1 - Math.pow(1 - elapsed, 3);
    const current = Math.floor(start + (target - start) * eased);
    el.textContent = current.toLocaleString();
    requestAnimationFrame(update);
  }
  requestAnimationFrame(update);
}

// --- Auto-insights ---
function generateInsights() {
  const meta = getMeta();
  const friction = get('friction_signals') || {};
  const helpAns = get('help_answered') || {};
  const providers = get('providers') || {};
  const insights = [];
  const totalMsgs = meta.total_messages || 0;
  const frictionCount = sum(friction);
  const rate = helpAns.target_answered_rate || 0;
  // Top provider
  const sortedProviders = Object.entries(providers).sort((a,b) => b[1] - a[1]);
  if (sortedProviders.length > 0) {
    insights.push({dot: 'accent', text: sortedProviders[0][0] + ' is the most mentioned provider (' + sortedProviders[0][1] + ' mentions)'});
  }
  // Friction
  if (frictionCount > 0 && totalMsgs > 0) {
    const pct = (frictionCount / totalMsgs * 100).toFixed(0);
    const cls = pct > 15 ? 'red' : 'yellow';
    insights.push({dot: cls, text: pct + '% of messages mention friction (' + frictionCount + ' signals)'});
  }
  // Answer rate
  if (rate > 0) {
    const cls = rate >= 0.7 ? 'green' : rate < 0.5 ? 'red' : 'yellow';
    insights.push({dot: cls, text: 'Answer rate: ' + (rate * 100).toFixed(0) + '% (48h window)'});
  } else {
    insights.push({dot: 'red', text: 'No questions answered within 48h'});
  }
  // Delta vs previous run
  if (currentRunIdx > 0) {
    const prevMeta = prevValue('metadata');
    const prevMsgs = prevMeta?.total_messages || 0;
    if (prevMsgs > 0) {
      const d = totalMsgs - prevMsgs;
      if (d > 0) insights.push({dot: 'green', text: '+' + d + ' messages vs previous run'});
      else if (d < 0) insights.push({dot: 'red', text: d + ' messages vs previous run'});
    }
  }
  return insights;
}

function renderInsights() {
  const insights = generateInsights();
  const el = document.getElementById('insights');
  if (!el) return;
  el.innerHTML = insights.map((ins, i) =>
    '<div class="insight-pill" style="animation-delay:' + (i * 0.1) + 's">' +
    '<span class="dot ' + ins.dot + '"></span>' + ins.text + '</div>'
  ).join('');
}

// --- Bar list ---
function barList(containerId, data, colorClass, dataKey) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) { el.innerHTML = '<div class="no-data">No data</div>'; return; }
  const max = Math.max(...entries.map(e => e[1]));
  el.innerHTML = entries.map(function(item) {
    var name = item[0], count = item[1];
    var pct = (count / max * 100).toFixed(1);
    var trendHtml = '';
    if (HAS_TREND && currentRunIdx > 0) {
      var prev = (prevValue(dataKey) || {})[name] || 0;
      if (prev > 0) {
        var d = count - prev;
        if (d === 0) trendHtml = '<span class="trend">\u2014</span>';
        else {
          var color = d > 0 ? 'var(--green)' : 'var(--red)';
          trendHtml = '<span class="trend" style="color:' + color + '">' + (d > 0 ? '+' : '') + d + '</span>';
        }
      }
    }
    return '<div class="bar-item" onclick="toggleDrilldown(this, \\'' + dataKey + '\\', \\'' + name + '\\')">' +
      '<div class="name">' + name + '</div>' +
      '<div class="bar-track"><div class="bar-fill ' + colorClass + '" style="width:' + pct + '%">' + count + '</div></div>' +
      trendHtml + '</div><div class="drilldown"></div>';
  }).join('');
  // Animate bars on render
  setTimeout(function() {
    el.querySelectorAll('.bar-fill').forEach(function(b) {
      var w = b.style.width; b.style.width = '0';
      requestAnimationFrame(function() { b.style.width = w; });
    });
  }, 50);
}

function toggleDrilldown(barItem, dataKey, label) {
  var dd = barItem.nextElementSibling;
  if (!dd || !dd.classList.contains('drilldown')) return;
  if (dd.classList.contains('open')) { dd.classList.remove('open'); return; }
  document.querySelectorAll('.drilldown.open').forEach(function(d) { d.classList.remove('open'); });
  dd.classList.add('open');
  if (!HAS_DRILLDOWN || MESSAGES.length === 0) {
    dd.innerHTML = '<div class="no-data">No message data available. Pass --chat to enable drill-down.</div>';
    return;
  }
  var labelLower = label.toLowerCase();
  var labelParts = labelLower.split(/[\\s_-]+/);
  var matches = MESSAGES.filter(function(m) {
    var c = (m.content || '').toLowerCase();
    return labelParts.some(function(part) { return part.length >= 3 && c.includes(part); });
  }).slice(0, 20);
  if (matches.length === 0) {
    dd.innerHTML = '<div class="no-data">No messages found matching "' + label + '"</div>';
    return;
  }
  dd.innerHTML = matches.map(function(m) {
    return '<div class="msg"><span class="ts">' + (m.ts || '?') + '</span>' +
      '<span class="sender">' + (m.sender || '?') + '</span>' +
      '<div class="content">' + m.content + '</div></div>';
  }).join('');
}

// --- KPIs ---
function renderKPIs() {
  var meta = getMeta();
  var users = get('users') || {};
  var langDist = get('language_distribution') || {};
  var friction = get('friction_signals') || {};
  var helpAns = get('help_answered') || {};
  var totalMsgs = meta.total_messages || 0;
  var totalUsers = users.total || 0;
  var targetMsgs = (langDist.target || 0) + (langDist.mixed || 0);
  var questions = helpAns.total_questions || 0;
  var frictionCount = sum(friction);
  var answeredRate = helpAns.target_answered_rate || 0;
  var frictionColor = frictionCount > totalMsgs * 0.15 ? 'red' : 'yellow';
  var rateColor = answeredRate >= 0.7 ? 'green' : answeredRate < 0.5 ? 'red' : 'yellow';
  var prevMeta = prevValue('metadata');
  var prevUsers = prevValue('users');
  var glowClass = frictionCount > totalMsgs * 0.15 ? 'glow-red' : '';

  document.getElementById('kpi-row').innerHTML =
    '<div class="kpi"><div class="label">Messages</div><div class="value" data-target="' + totalMsgs + '">0</div><div class="sub">total analyzed</div>' + delta(totalMsgs, prevMeta?.total_messages) + '</div>' +
    '<div class="kpi"><div class="label">Users</div><div class="value" data-target="' + totalUsers + '">0</div><div class="sub">' + (users.target_plus_bilingual || 0) + ' target-lang</div>' + delta(totalUsers, prevUsers?.total) + '</div>' +
    '<div class="kpi"><div class="label">Target-lang</div><div class="value accent" data-target="' + targetMsgs + '">0</div><div class="sub">' + (langDist.mixed || 0) + ' mixed</div></div>' +
    '<div class="kpi"><div class="label">Questions</div><div class="value" data-target="' + questions + '">0</div><div class="sub">' + (helpAns.target_questions || 0) + ' target</div></div>' +
    '<div class="kpi ' + glowClass + '"><div class="label">Friction</div><div class="value ' + frictionColor + '" data-target="' + frictionCount + '">0</div><div class="sub">' + fmtPct(frictionCount, totalMsgs) + ' of msgs</div></div>' +
    '<div class="kpi"><div class="label">Answered</div><div class="value ' + rateColor + '" data-target="' + Math.round(answeredRate * 100) + '">0</div><div class="sub">48h window</div></div>';

  // Animate number tickers
  document.querySelectorAll('.kpi .value[data-target]').forEach(function(el) {
    var target = parseInt(el.dataset.target);
    animateValue(el, target, 800);
  });
}

// --- Sections ---
function renderSections() {
  var meta = getMeta();
  var retention = get('retention') || {};
  var competitors = get('competitors') || {};
  var competitorsHtml = Object.keys(competitors).length > 0 ?
    '<div class="card span-4"><h2>Competitor mentions</h2><div class="card-body"><div class="bar-list" id="bar-competitors"></div></div></div>' : '';

  document.getElementById('sections').innerHTML =
    '<div class="bento">' +
    '<div class="card span-2"><h2>Provider mentions</h2><div class="card-body"><div class="bar-list" id="bar-providers"></div></div></div>' +
    '<div class="card"><h2>Messaging platforms</h2><div class="card-body"><div class="bar-list" id="bar-messaging"></div></div></div>' +
    '<div class="card"><h2>Language distribution</h2><div class="card-body"><div class="bar-list" id="bar-language"></div></div></div>' +
    '</div>' +
    '<div class="bento">' +
    '<div class="card glow-red"><h2>Friction signals</h2><div class="card-body"><div class="bar-list" id="bar-friction"></div></div></div>' +
    '<div class="card glow-green"><h2>Feature usage</h2><div class="card-body"><div class="bar-list" id="bar-features"></div></div></div>' +
    '<div class="card span-2"><h2>Retention \u2014 target-language cohort</h2><div class="card-body"><table>' +
    '<tr><td>Active (30d)</td><td class="num"><span class="badge green">' + (retention.target_active_30d || 0) + '</span></td></tr>' +
    '<tr><td>Lapsed (30\u201390d)</td><td class="num"><span class="badge yellow">' + (retention.target_lapsed_30_90d || 0) + '</span></td></tr>' +
    '<tr><td>Lapsed (90d+)</td><td class="num"><span class="badge red">' + (retention.target_lapsed_90d_plus || 0) + '</span></td></tr>' +
    '<tr><td>One-time posters</td><td class="num"><span class="badge dim">' + (retention.target_one_time_posters || 0) + '</span></td></tr>' +
    '</table></div></div>' +
    '</div>' +
    '<div class="bento">' +
    '<div class="card"><h2>Install paths</h2><div class="card-body"><div class="bar-list" id="bar-install"></div></div></div>' +
    '<div class="card"><h2>Shadow communities</h2><div class="card-body"><div class="bar-list" id="bar-shadow"></div></div></div>' +
    '<div class="card"><h2>URL categories</h2><div class="card-body"><div class="bar-list" id="bar-urls"></div></div></div>' +
    '<div class="card"><h2>Location proxy</h2><div class="card-body"><div class="bar-list" id="bar-location"></div></div></div>' +
    '</div>' +
    '<div class="bento">' + competitorsHtml + '</div>';

  barList('bar-providers', get('providers'), 'accent', 'providers');
  barList('bar-messaging', get('messaging_platforms'), 'cyan', 'messaging_platforms');
  barList('bar-language', get('language_distribution'), 'green', 'language_distribution');
  barList('bar-location', get('location_proxy'), 'orange', 'location_proxy');
  barList('bar-friction', get('friction_signals'), 'red', 'friction_signals');
  barList('bar-features', get('features'), 'accent', 'features');
  barList('bar-install', get('install_paths'), 'cyan', 'install_paths');
  barList('bar-shadow', get('shadow_community_mentions'), 'pink', 'shadow_community_mentions');
  barList('bar-urls', (get('urls') || {}).category_counts || {}, 'orange', 'urls');
  if (document.getElementById('bar-competitors')) barList('bar-competitors', competitors, 'yellow', 'competitors');
}

// --- SVG Trend chart ---
function renderTrendChart() {
  if (!HAS_TREND) return;
  var el = document.getElementById('trend-chart');
  if (!el) return;
  var max = Math.max.apply(null, RUNS.map(function(r) { return r.metadata?.total_messages || 0; }));
  var chartH = 160, barW = 48, gap = 60, padX = 20, padY = 30;
  var totalW = padX * 2 + RUNS.length * (barW + gap) - gap;
  var gridLines = 4;
  var svg = '<svg class="trend-svg" viewBox="0 0 ' + totalW + ' ' + (chartH + padY * 2) + '" preserveAspectRatio="xMidYMid meet">';
  // Gridlines
  svg += '<g class="grid">';
  for (var i = 0; i <= gridLines; i++) {
    var y = padY + (chartH / gridLines) * i;
    var val = Math.round(max - (max / gridLines) * i);
    svg += '<line x1="' + padX + '" y1="' + y + '" x2="' + (totalW - padX) + '" y2="' + y + '"/>';
    svg += '<text x="' + (padX - 4) + '" y="' + (y + 3) + '" text-anchor="end" class="bar-label">' + val + '</text>';
  }
  svg += '</g>';
  // Bars
  RUNS.forEach(function(r, i) {
    var msgs = r.metadata?.total_messages || 0;
    var h = max > 0 ? (msgs / max * chartH) : 0;
    var x = padX + i * (barW + gap);
    var y = padY + chartH - h;
    var isCurrent = i === currentRunIdx;
    var fill = isCurrent ? 'var(--accent)' : 'var(--dim)';
    var opacity = isCurrent ? 1 : 0.5;
    svg += '<rect class="bar" x="' + x + '" y="' + y + '" width="' + barW + '" height="' + h + '" rx="4" fill="' + fill + '" opacity="' + opacity + '"><title>' + msgs + ' messages</title></rect>';
    svg += '<text class="bar-value" x="' + (x + barW/2) + '" y="' + (y - 6) + '">' + msgs + '</text>';
    var date = (r.metadata?.date_range?.[0] || '?').slice(0, 10);
    svg += '<text class="bar-label" x="' + (x + barW/2) + '" y="' + (padY + chartH + 16) + '" text-anchor="middle">' + date + '</text>';
  });
  svg += '</svg>';
  el.innerHTML = svg;
}

// --- Header ---
function renderHeader() {
  var meta = getMeta();
  var channels = meta.channels;
  var channelStr = Array.isArray(channels) ? channels.join(', ') : (channels || 'unknown');
  document.getElementById('header-meta').textContent = channelStr + ' \u00b7 ' + (meta.total_messages || 0).toLocaleString() + ' msgs \u00b7 ' + (meta.target_language_name || 'n/a') + ' / ' + (meta.region_name || 'n/a') + ' \u00b7 ' + (meta.date_range?.[0] || '?').slice(0,10) + ' \u2192 ' + (meta.date_range?.[1] || '?').slice(0,10);
  document.getElementById('footer-time').textContent = (meta.analyzed_at || '?').slice(0, 19);
}

// --- Run selector ---
function populateRunSelector() {
  var sel = document.getElementById('run-selector');
  if (!sel) return;
  sel.innerHTML = RUNS.map(function(r, i) {
    var date = (r.metadata?.date_range?.[0] || 'run ' + (i+1)).slice(0, 10);
    var msgs = r.metadata?.total_messages || 0;
    return '<option value="' + i + '"' + (i === currentRunIdx ? ' selected' : '') + '>' + date + ' (' + msgs.toLocaleString() + ' msgs)</option>';
  }).join('');
  if (RUNS.length <= 1) sel.style.display = 'none';
}

// --- Controls ---
function switchRun() {
  currentRunIdx = parseInt(document.getElementById('run-selector').value);
  renderAll();
}
function setView(view) {
  currentView = view;
  var btnCurrent = document.getElementById('btn-current');
  var btnTrend = document.getElementById('btn-trend');
  if (btnCurrent) btnCurrent.classList.toggle('active', view === 'current');
  if (btnTrend) btnTrend.classList.toggle('active', view === 'trend');
  document.getElementById('trend-section').style.display = view === 'trend' ? 'block' : 'none';
  document.getElementById('sections').style.display = view === 'trend' ? 'none' : 'block';
  document.getElementById('kpi-row').style.display = view === 'trend' ? 'none' : 'grid';
  document.getElementById('insights').style.display = view === 'trend' ? 'none' : 'flex';
  if (view === 'trend') renderTrendChart();
}
function setCohort(cohort) {
  currentCohort = cohort;
  document.getElementById('btn-all').classList.toggle('active', cohort === 'all');
  document.getElementById('btn-target').classList.toggle('active', cohort === 'target');
}

function renderAll() {
  populateRunSelector();
  renderHeader();
  renderInsights();
  renderKPIs();
  renderSections();
  if (HAS_TREND) renderTrendChart();
}

renderAll();
"""


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

    runs_json = json.dumps(stats_runs, ensure_ascii=False)
    users_json = json.dumps(users or [], ensure_ascii=False)

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

    latest = stats_runs[-1] if stats_runs else {}
    meta = latest.get("metadata", {})

    has_trend = len(stats_runs) > 1
    has_drilldown = users is not None or chat_jsonl is not None

    trend_buttons = ""
    if has_trend:
        trend_buttons = (
            "<label>View</label>"
            '<button id="btn-current" class="active" onclick="setView(\'current\')">Current</button>'
            '<button id="btn-trend" onclick="setView(\'trend\')">Trend</button>'
        )

    # Replace placeholders in JS
    js = _JS.replace("__RUNS_JSON__", runs_json)
    js = js.replace("__USERS_JSON__", users_json)
    js = js.replace("__MESSAGES_JSON__", messages_json)
    js = js.replace("__HAS_TREND__", "true" if has_trend else "false")
    js = js.replace("__HAS_DRILLDOWN__", "true" if has_drilldown else "false")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Parallax \u2014 Community Dashboard</title>
<style>
{_CSS}
</style>
</head>
<body>

<div class="header">
  <h1><span class="accent">\u25c6</span> Parallax Community Dashboard</h1>
  <div class="meta" id="header-meta"></div>
</div>

<div class="insights" id="insights"></div>

<div class="controls">
  <label>Run</label>
  <select id="run-selector" onchange="switchRun()"></select>
  {trend_buttons}
  <label>Cohort</label>
  <button id="btn-all" class="active" onclick="setCohort('all')">All</button>
  <button id="btn-target" onclick="setCohort('target')">Target-lang</button>
  <div class="spacer"></div>
</div>

<div class="kpi-row" id="kpi-row"></div>

<div id="trend-section" style="display:none;">
  <div class="card" style="margin-bottom:14px;">
    <h2>Trend \u2014 total messages over runs</h2>
    <div class="card-body">
      <div id="trend-chart"></div>
    </div>
  </div>
</div>

<div id="sections"></div>

<div class="footer">
  <span>Generated by parallax v{meta.get("pipeline_version", "?")}</span>
  <span id="footer-time"></span>
</div>

<script>
{js}
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
        help="Path to raw chat export JSON (enables message-level drill-down)",
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
