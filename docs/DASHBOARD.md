# Dashboard — Usage & Interpretation Guide

> **Scope note:** this document describes a companion daily-monitoring service that generates the dashboard below. That service is **not included in this repo** — it depends on org-specific scheduling/delivery infrastructure and isn't part of the core `chatintel` package. This doc is kept as a design reference for anyone building their own daily-digest service on top of `chatintel-analyze`'s output (see `docs/PIPELINE.md` File Reference section for the minimal shape to replicate).

The daily service renders a self-contained HTML dashboard at `dailies/dashboard.html`. No server, no build step — open it in any browser. Everything is embedded.

---

## Quick Start

```bash
# Open the dashboard in your default browser
open ~/your-analysis-dir/dailies/dashboard.html        # macOS
xdg-open ~/your-analysis-dir/dailies/dashboard.html    # Linux
start ~/your-analysis-dir/dailies/dashboard.html       # Windows/WSL
```

Or just double-click `dashboard.html` in your file manager.

The dashboard works offline after first load (Chart.js CDN cache). Refresh the page to pick up new data — the service rewrites the file on each run.

---

## Layout

The dashboard is a responsive grid of cards, each showing one metric or chart. It reflows from two columns on desktop to a single column on mobile.

```
┌─────────────────────────────────────────────────┐
│  Product · Community Dashboard                   │
│  Chat name · member count · last updated        │
├──────────────────┬──────────────────────────────┤
│  📊 Today        │  📈 Activity (7 days)        │
│  KPIs: msgs,     │  Bar chart: daily message    │
│  users, target-  │  volume with today           │
│  language,       │  highlighted                 │
│  questions,      │                              │
│  friction        │                              │
├──────────────────┼──────────────────────────────┤
│  👥 Users (7d)   │  🔥 Top Keywords (today)     │
│  Line chart:     │  Per-category keyword        │
│  active posters  │  breakdown with counts       │
│  per day         │                              │
├──────────────────┴──────────────────────────────┤
│  📋 Recent Topics          │  ⚠️ Friction (7d)  │
│  Table: keyword-topic      │  Dual line chart:  │
│  distribution today, with  │  friction signals   │
│  proportional bars         │  + questions asked  │
├─────────────────────────────────────────────────┤
│  📰 Latest Digest                               │
│  Full daily summary rendered as formatted       │
│  markdown — what happened, key themes,          │
│  friction, notable threads                       │
├─────────────────────────────────────────────────┤
│  📋 Recent Digests                              │
│  Last 7 days: date, message count, users, TL;DR │
└─────────────────────────────────────────────────┘
```

---

## Section Reference

### 📊 Today — KPIs

Key performance indicators for the most recent day of data:

| Metric | What it tells you |
|--------|-------------------|
| **Messages** | Total messages today. Compare day-over-day in the activity chart. |
| **Active users** | Unique posters today. |
| **Target-language** | Messages flagged as target-language or mixed-language by the configured `LanguageProfile` (see `src/chatintel/core/languages.py`) — script-ratio for CJK/Cyrillic/Arabic/etc., stopword-ratio for Latin-script languages. |
| **Questions** | Messages ending in question markers or containing question keywords (per the active language profile). |
| **Friction signals** | Errors, network complaints, timeout, confusion, API key issues, and other problem keywords. |

> **Healthy:** messages stable or growing, users diverse, friction <15% of messages.  
> **Watch:** message count dropping 3+ days, friction spiking, active users concentrating in top 3.

---

### 📈 Activity — 7-Day Bar Chart

A Chart.js bar chart showing daily message volume for the last 7 days (up to 14 when data exists). Today's bar is highlighted; previous days are faded.

**What to look for:**
- **Weekday/weekend pattern** — many tech communities drop 30-50% on weekends
- **Sudden spikes** — viral content shares, new release announcements, or a hot topic blowing up
- **Declining trend** — 5+ days of declining volume may signal community fatigue or a competing platform draining attention

---

### 👥 Users — 7-Day Line Chart

A Chart.js line chart of unique active posters per day. Green fill under the curve.

**What to look for:**
- **Flat or rising line** — community is maintaining or growing its active core
- **Declining line with stable message count** — fewer people are talking more (concentration risk)
- **Spike + return to baseline** — one-day influx with low retention

The ratio between this chart and the activity chart matters. If messages stay high but users drop, the top 3-5 posters are carrying the conversation — fragile if any of them leave.

---

### 🔥 Top Keywords — Today

Keyword hits grouped by category, with raw counts:

| Category | What it covers |
|----------|---------------|
| **PROVIDERS** | LLM/API providers mentioned in your ecosystem (configure in `keywords.py`) |
| **MESSAGING** | Chat platforms referenced (configure in `keywords.py`) |
| **FEATURES** | Your product's feature names (configure in `keywords.py`) |
| **FRICTION** | error, timeout, network issues, confusion, broken, key issues, etc. |
| **COMPETITORS** | Named competitor products in your market (configure in `keywords.py`) |

Only the top 5 per category are shown. If a category is absent, no keywords of that type were detected today.

> **Interpretation tip:** High `FEATURES` + low `FRICTION` = users are exploring advanced functionality without pain. High `FRICTION` + high `PROVIDERS` = provider-config issues (check the digest for specifics).

---

### 📋 Recent Topics — Today's Distribution

A table showing which keyword labels were mentioned most today, with a proportional bar visualization. Each row shows the label, raw count, and share of total keyword hits.

> **Not a true topic model** — these are keyword-hit aggregates, not LLM-classified topics. Use the digest (below) for semantic topic understanding; use this for quick distribution scanning.

---

### ⚠️ Friction Signals — 7-Day Dual Line Chart

Two overlaid line charts:
- **Red (Friction):** Daily count of friction keyword hits (errors, network issues, timeout, confusion, etc.)
- **Amber (Questions):** Daily count of detected question messages

**What to look for:**
- **Friction spiking while questions are flat** — an acute technical problem (outage, breaking change, provider deprecation)
- **Questions spiking while friction is flat** — onboarding wave (new users asking setup questions)
- **Both spiking together** — major incident or release with breaking changes
- **Both declining** — community is self-sufficient or the friction sources have been addressed

---

### 📰 Latest Digest

The full daily digest rendered as formatted HTML. This is the richest section — it contains the LLM-generated narrative summary of today's conversation.

Sections within the digest:
- **What Happened** — 3-5 bullet points capturing the main discussions
- **Key Themes** — table with topic, share, and signal interpretation
- **Friction & Issues** — specific problems, complaints, errors surfaced today
- **Notable** — long threads, resolved questions, success stories, competitor mentions, brand confusion incidents
- **TL;DR** — one-sentence summary

> The digest is generated by a single LLM call per day (~$0.02). It synthesizes the keyword data plus a sample of actual messages to produce a coherent narrative. If the LLM is unavailable, a lightweight fallback digest is generated from keyword stats alone.

---

### 📋 Recent Digests

Last 7 days of digests as a compact list: date, message count, active user count, TL;DR. Click through to the full digest above for the most recent day; for earlier days, open `dailies/YYYY-MM-DD.md` directly.

---

## Interpreting the Dashboard Day-to-Day

### What a healthy community looks like

| Indicator | Healthy pattern |
|-----------|----------------|
| Messages | 150-400/day, slight weekday/weekend oscillation |
| Users | 25-60/day, no single user above 15% of messages |
| Target-language share | 70-90% (normal for a well-scoped target-language chat) |
| Friction | Under 20% of messages, flat or declining trend |
| Questions | 15-40/day, most answered (see digest) |
| Keywords | Diverse across providers/messaging/features; no single topic dominating >40% |

### Red flags

| Pattern | What it suggests |
|---------|-----------------|
| Messages halved for 5+ days | Community migrating to another platform |
| Friction spiking 2×+ | Outage, breaking change, or provider deprecation |
| Users declining while messages stable | Concentration in top posters — fragile |
| Single keyword dominating (>50%) | Crisis or monoculture — check digest immediately |
| Zero messages | Fetch failed — check your daily service's status |

---

## Files

| File | Purpose |
|------|---------|
| `dailies/dashboard.html` | Self-contained dashboard (open in browser) |
| `dailies/dashboard_data.json` | Machine-readable data backing the dashboard |
| `dailies/YYYY-MM-DD.md` | Daily digest markdown for each day |
| `dailies/feed.md` | Rolling 7-day feed of all recent digests |
| `daily_state.db` | SQLite database backing all dashboard data |

---

## Customization

### Changing the time window

The dashboard shows up to 14 days of charts. To change this, edit the `LIMIT 14` in `generate_dashboard()` in your daily service implementation.

### Adding a new chart

1. Add your metric to the `daily_stats` table (add a column in `init_db()`)
2. Populate it in your analysis-and-digest function
3. Add a `<canvas>` element and Chart.js block to the `DASHBOARD_HTML` template
4. The data flows through `dashboard_data.json` → `DATA` JS object automatically

### Changing the theme

The CSS variables at the top of `DASHBOARD_HTML` control all colors:

```css
:root {
    --bg: #0d1117;        /* page background */
    --surface: #161b22;   /* card background */
    --border: #30363d;    /* card borders */
    --text: #e6edf3;      /* body text */
    --muted: #8b949e;     /* secondary text */
    --accent: #58a6ff;    /* highlights, links */
    --green: #3fb950;     /* positive indicators */
    --red: #f85149;       /* negative indicators */
    --yellow: #d2991d;    /* warnings */
}
```

The default is GitHub's dark theme. For a light theme, swap the values.

### Hosting on a server

If you want to serve the dashboard over HTTP instead of opening files locally:

```bash
cd ~/your-analysis-dir/dailies
python3 -m http.server 8080
# → http://localhost:8080/dashboard.html
```

The dashboard is entirely static — no backend needed. The data is embedded in the HTML at generation time.
