#!/usr/bin/env python3
"""Generate a self-contained HTML dashboard from stats.json.

Usage:
    python -m parallax.streams.generate_dashboard --stats ./out/stats.json --out ./out/dashboard.html

The dashboard is a single HTML file with all CSS/JS/data embedded — no
server needed, no build step. Open it directly in any browser.
"""

import argparse
import json
from pathlib import Path


def generate_dashboard(stats: dict, output_path: Path):
    """Generate a self-contained HTML dashboard from a stats dict."""

    stats_json = json.dumps(stats, indent=2, ensure_ascii=False)

    meta = stats.get("metadata", {})
    users = stats.get("users", {})
    retention = stats.get("retention", {})
    friction = stats.get("friction_signals", {})
    help_ans = stats.get("help_answered", {})
    lang_dist = stats.get("language_distribution", {})

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
  --accent-dim: rgba(108, 138, 255, 0.15);
  --green: #3fb950;
  --red: #f85149;
  --yellow: #d2991d;
  --orange: #db6d28;
  --cyan: #39c5cf;
  --pink: #f778ba;
  --radius: 10px;
  --radius-sm: 6px;
  --shadow: 0 1px 3px rgba(0,0,0,0.3);
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
  margin-bottom: 28px;
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

/* --- KPI Row --- */
.kpi-row {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}}
.kpi {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 18px;
  position: relative;
  overflow: hidden;
}}
.kpi .label {{
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--dim);
  margin-bottom: 6px;
}}
.kpi .value {{
  font-size: 28px;
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

/* --- Grid --- */
.grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}}
.grid .full {{ grid-column: 1 / -1; }}

@media (max-width: 768px) {{
  .grid {{ grid-template-columns: 1fr; }}
}}

/* --- Card --- */
.card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  overflow: hidden;
}}
.card h2 {{
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  margin-bottom: 14px;
}}
.card-body {{ position: relative; }}

/* --- Bar list (keyword breakdown) --- */
.bar-list {{ display: flex; flex-direction: column; gap: 8px; }}
.bar-item {{
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}}
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
  transition: width 0.4s ease;
}}
.bar-item .bar-fill.accent {{ background: var(--accent); }}
.bar-item .bar-fill.green {{ background: var(--green); }}
.bar-item .bar-fill.red {{ background: var(--red); }}
.bar-item .bar-fill.yellow {{ background: var(--yellow); }}
.bar-item .bar-fill.cyan {{ background: var(--cyan); }}
.bar-item .bar-fill.pink {{ background: var(--pink); }}
.bar-item .bar-fill.orange {{ background: var(--orange); }}
.bar-item .bar-fill.dim {{ background: var(--dim); }}

/* --- Table --- */
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}}
table th {{
  text-align: left;
  font-weight: 600;
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}}
table td {{
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-variant-numeric: tabular-nums;
}}
table td.num {{ text-align: right; font-family: var(--mono); }}
table tr:last-child td {{ border-bottom: none; }}

/* --- Badge --- */
.badge {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 100px;
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}}
.badge.green {{ background: rgba(63,185,80,0.15); color: var(--green); }}
.badge.red {{ background: rgba(248,81,73,0.15); color: var(--red); }}
.badge.yellow {{ background: rgba(210,153,29,0.15); color: var(--yellow); }}
.badge.dim {{ background: rgba(140,143,158,0.15); color: var(--muted); }}

/* --- Footer --- */
.footer {{
  margin-top: 32px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--dim);
  font-family: var(--mono);
  display: flex;
  justify-content: space-between;
}}
</style>
</head>
<body>

<div class="header">
  <h1><span class="accent">◆</span> Parallax Community Dashboard</h1>
  <div class="meta">
    {meta.get("channels", ["unknown"])[0] if isinstance(meta.get("channels"), list) else meta.get("channels", "unknown")} ·
    {meta.get("total_messages", 0):,} messages ·
    {meta.get("target_language_name", "n/a")} / {meta.get("region_name", "n/a")} ·
    {meta.get("date_range", ["?", "?"])[0][:10]} → {meta.get("date_range", ["?", "?"])[1][:10]}
  </div>
</div>

<!-- KPI Row -->
<div class="kpi-row">
  <div class="kpi">
    <div class="label">Messages</div>
    <div class="value">{meta.get("total_messages", 0):,}</div>
    <div class="sub">total analyzed</div>
  </div>
  <div class="kpi">
    <div class="label">Users</div>
    <div class="value">{users.get("total", 0):,}</div>
    <div class="sub">{users.get("target_plus_bilingual", 0)} target-lang cohort</div>
  </div>
  <div class="kpi">
    <div class="label">Target-language</div>
    <div class="value accent">{(lang_dist.get("target", 0) + lang_dist.get("mixed", 0)):,}</div>
    <div class="sub">{lang_dist.get("mixed", 0)} mixed / {lang_dist.get("target", 0)} pure</div>
  </div>
  <div class="kpi">
    <div class="label">Questions</div>
    <div class="value">{help_ans.get("total_questions", 0):,}</div>
    <div class="sub">{help_ans.get("target_questions", 0)} in target language</div>
  </div>
  <div class="kpi">
    <div class="label">Friction</div>
    <div class="value {"red" if sum(friction.values()) > meta.get("total_messages", 1) * 0.15 else "yellow"}">{sum(friction.values()):,}</div>
    <div class="sub">{sum(friction.values()) / max(1, meta.get("total_messages", 1)) * 100:.0f}% of messages</div>
  </div>
  <div class="kpi">
    <div class="label">Answered rate</div>
    <div class="value {"green" if help_ans.get("target_answered_rate", 0) >= 0.7 else "red" if help_ans.get("target_answered_rate", 0) < 0.5 else "yellow"}">{help_ans.get("target_answered_rate", 0) * 100:.0f}%</div>
    <div class="sub">target-lang, 48h window</div>
  </div>
</div>

<!-- Row 1: Providers + Messaging -->
<div class="grid">
  <div class="card">
    <h2>Provider mentions</h2>
    <div class="card-body">
      <div class="bar-list" id="bar-providers"></div>
    </div>
  </div>
  <div class="card">
    <h2>Messaging platforms</h2>
    <div class="card-body">
      <div class="bar-list" id="bar-messaging"></div>
    </div>
  </div>
</div>

<!-- Row 2: Friction + Features -->
<div class="grid">
  <div class="card">
    <h2>Friction signals</h2>
    <div class="card-body">
      <div class="bar-list" id="bar-friction"></div>
    </div>
  </div>
  <div class="card">
    <h2>Feature usage</h2>
    <div class="card-body">
      <div class="bar-list" id="bar-features"></div>
    </div>
  </div>
</div>

<!-- Row 3: Language distribution + Retention -->
<div class="grid">
  <div class="card">
    <h2>Language distribution</h2>
    <div class="card-body">
      <div class="bar-list" id="bar-language"></div>
    </div>
  </div>
  <div class="card">
    <h2>Retention — target-language cohort</h2>
    <div class="card-body">
      <table>
        <tr><td>Active (30d)</td><td class="num"><span class="badge green">{retention.get("target_active_30d", 0)}</span></td></tr>
        <tr><td>Lapsed (30–90d)</td><td class="num"><span class="badge yellow">{retention.get("target_lapsed_30_90d", 0)}</span></td></tr>
        <tr><td>Lapsed (90d+)</td><td class="num"><span class="badge red">{retention.get("target_lapsed_90d_plus", 0)}</span></td></tr>
        <tr><td>One-time posters</td><td class="num"><span class="badge dim">{retention.get("target_one_time_posters", 0)}</span></td></tr>
      </table>
    </div>
  </div>
</div>

<!-- Row 4: Install paths + Shadow communities -->
<div class="grid">
  <div class="card">
    <h2>Install paths</h2>
    <div class="card-body">
      <div class="bar-list" id="bar-install"></div>
    </div>
  </div>
  <div class="card">
    <h2>Shadow communities</h2>
    <div class="card-body">
      <div class="bar-list" id="bar-shadow"></div>
    </div>
  </div>
</div>

<!-- Row 5: URL categories + Location proxy -->
<div class="grid">
  <div class="card">
    <h2>URL categories</h2>
    <div class="card-body">
      <div class="bar-list" id="bar-urls"></div>
    </div>
  </div>
  <div class="card">
    <h2>Location proxy (timezone)</h2>
    <div class="card-body">
      <div class="bar-list" id="bar-location"></div>
    </div>
  </div>
</div>

<!-- Row 6: Competitors (full width if data exists) -->
<div class="grid full" id="row-competitors" style="display: {"grid" if stats.get("competitors") else "none"};">
  <div class="card" style="grid-column: 1 / -1;">
    <h2>Competitor mentions</h2>
    <div class="card-body">
      <div class="bar-list" id="bar-competitors"></div>
    </div>
  </div>
</div>

<div class="footer">
  <span>Generated by parallax v{meta.get("pipeline_version", "?")}</span>
  <span>{meta.get("analyzed_at", "?")[:19]}</span>
</div>

<script>
const DATA = {stats_json};

// --- Helpers ---
function barList(containerId, data, colorClass) {{
  const el = document.getElementById(containerId);
  if (!el) return;
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) {{
    el.innerHTML = '<div style="color: var(--dim); font-size: 12px; padding: 20px 0; text-align: center;">No data</div>';
    return;
  }}
  const max = Math.max(...entries.map(e => e[1]));
  el.innerHTML = entries.map(([name, count]) => `
    <div class="bar-item">
      <div class="name">${{name}}</div>
      <div class="bar-track">
        <div class="bar-fill ${{colorClass}}" style="width: ${{(count / max * 100).toFixed(1)}}%">${{count}}</div>
      </div>
    </div>
  `).join('');
}}

// --- Render ---
barList('bar-providers', DATA.providers || {{}}, 'accent');
barList('bar-messaging', DATA.messaging_platforms || {{}}, 'cyan');
barList('bar-language', DATA.language_distribution || {{}}, 'green');
barList('bar-location', DATA.location_proxy || {{}}, 'orange');

barList('bar-friction', DATA.friction_signals || {{}}, 'red');
barList('bar-features', DATA.features || {{}}, 'accent');
barList('bar-install', DATA.install_paths || {{}}, 'cyan');
barList('bar-shadow', DATA.shadow_community_mentions || {{}}, 'pink');
barList('bar-urls', (DATA.urls && DATA.urls.category_counts) || {{}}, 'orange');
barList('bar-competitors', DATA.competitors || {{}}, 'yellow');
</script>

</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"[dashboard] written to {output_path} ({len(html):,} bytes)")


def main():
    parser = argparse.ArgumentParser(
        description="Generate a self-contained HTML dashboard from stats.json"
    )
    parser.add_argument(
        "--stats", required=True, help="Path to stats.json from parallax-analyze"
    )
    parser.add_argument("--out", required=True, help="Output path for dashboard.html")
    args = parser.parse_args()

    stats = json.loads(Path(args.stats).read_text())
    generate_dashboard(stats, Path(args.out))


if __name__ == "__main__":
    main()
