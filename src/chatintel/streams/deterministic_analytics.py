#!/usr/bin/env python3
"""Stream D (deterministic_analytics.py): pinned to ground truth from a manually-verified membership count.

This script is written for chat platforms (Feishu/Lark, Discord, Slack, etc.)
that don't reliably emit "member left" events, so join-event counts alone
overstate current membership. Point GROUND_TRUTH_HUMANS / GROUND_TRUTH_BOTS at
whatever your platform's admin UI reports as of your export date — that
becomes the authoritative denominator for retention and engagement rates.

Example (from a real 20-day, 28K-message run on a Feishu community):
  - Verified humans: 3,119 / bots: 5 / total live members: 3,124
  - Human posters: 878 (28.2%) vs. 2,241 silent lurkers (71.8%)
  - ~49 inferred departures (join-events observed minus live membership)
"""

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHAT_JSONL = Path(os.environ.get("CHAT_JSONL", "./data/pages.jsonl"))
OUT_DIR = Path(os.environ.get("OUT_DIR", "./out/stream_d"))

# Set these from your platform's admin/member-list UI, verified as of export date.
GROUND_TRUTH_HUMANS = int(os.environ.get("GROUND_TRUTH_HUMANS", "0"))
GROUND_TRUTH_BOTS = int(os.environ.get("GROUND_TRUTH_BOTS", "0"))
GROUND_TRUTH_MEMBERS = GROUND_TRUTH_HUMANS + GROUND_TRUTH_BOTS

SALT_FILE = Path(os.environ.get("SALT_FILE", "./user_hash_salt.key"))
SALT = SALT_FILE.read_text().strip() if SALT_FILE.exists() else "default-salt"


def hash_user(label):
    return (
        "u_" + hashlib.sha256((SALT + label).encode()).hexdigest()[:12]
        if label
        else "unknown"
    )


# Timestamp parsing assumes a fixed UTC offset for "YYYY-MM-DD HH:MM"
# display-format timestamps some export tools emit without a tz marker.
# Defaults to +8 (China Standard Time) for backward compatibility with the
# original Feishu-export worked example; set TS_UTC_OFFSET_HOURS to your
# own export's local timezone offset (e.g. 9 for Japan/Korea, 0 for UTC).
DISPLAY_TS_TZ = timezone(
    timedelta(hours=float(os.environ.get("TS_UTC_OFFSET_HOURS", "8")))
)


def parse_ts(s):
    if isinstance(s, str) and re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}", s):
        return (
            datetime.strptime(s, "%Y-%m-%d %H:%M")
            .replace(tzinfo=DISPLAY_TS_TZ)
            .astimezone(timezone.utc)
        )
    return None


# Load
system_msgs = []
content_msgs = []
for line in CHAT_JSONL.open():
    try:
        m = json.loads(line)
    except:
        continue
    ts = parse_ts(m.get("create_time", ""))
    if not ts:
        continue
    c = m.get("content", "")
    if isinstance(c, dict):
        c = c.get("text", "") or ""
    m["_ts"] = ts
    m["_content_str"] = c if isinstance(c, str) else str(c)
    (system_msgs if m.get("msg_type") == "system" else content_msgs).append(m)

# Join events
JOIN_RE_QR = re.compile(r"^(.+?) joined the group")
JOIN_RE_INV = re.compile(r"^(.+?) invited (.+?) to the group")
join_events = []
for m in system_msgs:
    c = m["_content_str"]
    ts = m["_ts"]
    mm_inv = JOIN_RE_INV.match(c)
    mm_qr = JOIN_RE_QR.match(c)
    if mm_inv:
        join_events.append(
            (
                ts,
                mm_inv.group(2).strip().rstrip("."),
                mm_inv.group(1).strip(),
                "invited",
            )
        )
    elif mm_qr:
        m_qr = re.search(r"QR Code shared by (.+?)\.", c)
        join_events.append(
            (ts, mm_qr.group(1).strip(), m_qr.group(1).strip() if m_qr else None, "qr")
        )

join_events_observed = len(join_events)
unique_joiners_observed = len({j[1] for j in join_events})

# Poster activity by ID
posters = {}
for m in content_msgs:
    s = m.get("sender") or {}
    uid = s.get("id", "")
    if not uid:
        continue
    if uid not in posters:
        posters[uid] = {
            "name": s.get("name", ""),
            "messages": 0,
            "days": set(),
            "first": None,
            "last": None,
            "sender_type": s.get("sender_type", ""),
        }
    p = posters[uid]
    p["messages"] += 1
    p["days"].add(m["_ts"].date().isoformat())
    if p["first"] is None or m["_ts"] < p["first"]:
        p["first"] = m["_ts"]
    if p["last"] is None or m["_ts"] > p["last"]:
        p["last"] = m["_ts"]
    if not p["name"] and s.get("name"):
        p["name"] = s.get("name")

human_posters = {uid: v for uid, v in posters.items() if v["sender_type"] != "app"}
bot_posters = {uid: v for uid, v in posters.items() if v["sender_type"] == "app"}

# Status breakdown over HUMANS
status = Counter()
for uid, info in human_posters.items():
    d = len(info["days"])
    if info["messages"] == 1:
        status["one_time_poster"] += 1
    elif d == 1:
        status["single_day_poster"] += 1
    elif d >= 7:
        status["multi_week_active"] += 1
    else:
        status["few_day_active"] += 1

silent_humans = GROUND_TRUTH_HUMANS - len(human_posters)

# Message concentration over HUMAN posters
human_poster_list = sorted(human_posters.items(), key=lambda x: -x[1]["messages"])
total_human_msgs = sum(v["messages"] for v in human_posters.values())


def pct_msgs(top_n):
    return round(
        100
        * sum(v["messages"] for _, v in human_poster_list[:top_n])
        / total_human_msgs,
        2,
    )


def pct_members(top_n):
    return round(100 * top_n / GROUND_TRUTH_HUMANS, 3)


pareto_out = {
    "ground_truth": {
        "total_humans_in_chat": GROUND_TRUTH_HUMANS,
        "total_bots_in_chat": GROUND_TRUTH_BOTS,
        "total_members_in_chat": GROUND_TRUTH_MEMBERS,
        "source": os.environ.get(
            "GROUND_TRUTH_SOURCE", "platform admin UI, manually verified"
        ),
    },
    "observed_in_export": {
        "join_events_system_msgs": join_events_observed,
        "unique_joiner_names_system_msgs": unique_joiners_observed,
        "inferred_net_departures_20d": unique_joiners_observed - GROUND_TRUTH_HUMANS,
        "note": "Feishu does not log leave/removal events. Difference vs ground truth = inferred departures.",
    },
    "posters_by_type": {
        "human_posters": len(human_posters),
        "bot_posters": len(bot_posters),
        "silent_humans_lurkers": silent_humans,
        "lurker_rate_of_humans": round(100 * silent_humans / GROUND_TRUTH_HUMANS, 2),
        "poster_rate_of_humans": round(
            100 * len(human_posters) / GROUND_TRUTH_HUMANS, 2
        ),
    },
    "bot_footprint": {
        "total_bot_messages": sum(v["messages"] for v in bot_posters.values()),
        "bot_msg_share": round(
            100
            * sum(v["messages"] for v in bot_posters.values())
            / sum(v["messages"] for v in posters.values()),
            2,
        ),
        "bots": [
            {"uid_tail": uid[-16:], "messages": v["messages"], "name": v["name"]}
            for uid, v in sorted(bot_posters.items(), key=lambda x: -x[1]["messages"])
        ],
    },
    "human_concentration": {
        f"top_{n}_pct_of_msgs_by_humans": pct_msgs(n)
        for n in [1, 5, 10, 25, 50, 100, 200]
    },
    "human_concentration_of_membership": {
        f"top_{n}_pct_of_ground_truth_humans": pct_members(n)
        for n in [1, 5, 10, 25, 50, 100, 200]
    },
    "top_50_human_posters": [
        {
            "rank": i + 1,
            "user_hash": hash_user(uid),
            "messages": v["messages"],
            "days_active": len(v["days"]),
            "pct_of_human_msgs": round(100 * v["messages"] / total_human_msgs, 2),
            "has_name": bool(v["name"]),
        }
        for i, (uid, v) in enumerate(human_poster_list[:50])
    ],
}

(OUT_DIR / "user_pareto_v4.json").write_text(
    json.dumps(pareto_out, ensure_ascii=False, indent=2)
)

stickiness_out = {
    "denominator_ground_truth": GROUND_TRUTH_HUMANS,
    "human_poster_status_breakdown": dict(status),
    "retention_rates_over_human_membership": {
        "silent_lurkers": round(100 * silent_humans / GROUND_TRUTH_HUMANS, 2),
        "one_time_posters": round(
            100 * status["one_time_poster"] / GROUND_TRUTH_HUMANS, 2
        ),
        "single_day_posters": round(
            100 * status["single_day_poster"] / GROUND_TRUTH_HUMANS, 2
        ),
        "few_day_active": round(
            100 * status["few_day_active"] / GROUND_TRUTH_HUMANS, 2
        ),
        "multi_week_active": round(
            100 * status["multi_week_active"] / GROUND_TRUTH_HUMANS, 2
        ),
    },
    "retention_rates_over_human_posters": {
        "one_time_posters": round(
            100 * status["one_time_poster"] / max(len(human_posters), 1), 2
        ),
        "single_day_posters": round(
            100 * status["single_day_poster"] / max(len(human_posters), 1), 2
        ),
        "few_day_active": round(
            100 * status["few_day_active"] / max(len(human_posters), 1), 2
        ),
        "multi_week_active": round(
            100 * status["multi_week_active"] / max(len(human_posters), 1), 2
        ),
    },
}
(OUT_DIR / "user_stickiness_v4.json").write_text(
    json.dumps(stickiness_out, ensure_ascii=False, indent=2)
)

# Temporal v4
by_day_joined = defaultdict(int)
by_day_posted = defaultdict(
    lambda: {"messages": 0, "active_humans": set(), "first_posters": 0}
)
seen = set()
for ts, _, _, _ in join_events:
    by_day_joined[ts.date().isoformat()] += 1
for m in sorted(content_msgs, key=lambda x: x["_ts"]):
    s = m.get("sender") or {}
    if s.get("sender_type") == "app":
        continue
    uid = s.get("id", "")
    if not uid:
        continue
    d = m["_ts"].date().isoformat()
    by_day_posted[d]["messages"] += 1
    by_day_posted[d]["active_humans"].add(uid)
    if uid not in seen:
        by_day_posted[d]["first_posters"] += 1
        seen.add(uid)

all_days = sorted(set(list(by_day_joined.keys()) + list(by_day_posted.keys())))
temporal = []
cm, cp = 0, 0
for d in all_days:
    j = by_day_joined.get(d, 0)
    p = by_day_posted[d]
    cm += j
    cp += p["first_posters"]
    temporal.append(
        {
            "date": d,
            "new_members_joined": j,
            "new_first_time_human_posters": p["first_posters"],
            "human_messages": p["messages"],
            "active_humans": len(p["active_humans"]),
            "cumulative_joined": cm,
            "cumulative_human_posters": cp,
        }
    )
(OUT_DIR / "temporal_growth_v4.json").write_text(
    json.dumps(temporal, indent=2, ensure_ascii=False)
)

print("=== GROUND-TRUTH-ANCHORED ANALYSIS ===")
print(
    f"Live membership (Feishu UI): {GROUND_TRUTH_MEMBERS:,}  ({GROUND_TRUTH_HUMANS:,} humans + {GROUND_TRUTH_BOTS} bots)"
)
print(
    f"Observed join events:         {join_events_observed:,} ({unique_joiners_observed:,} unique names)"
)
print(
    f"Implied departures:           ~{unique_joiners_observed - GROUND_TRUTH_HUMANS:,} over 20 days"
)
print()
print(
    f"Human posters:                {len(human_posters):,}  ({round(100 * len(human_posters) / GROUND_TRUTH_HUMANS, 1)}% of humans)"
)
print(
    f"Silent humans (lurkers):      {silent_humans:,}  ({round(100 * silent_humans / GROUND_TRUTH_HUMANS, 1)}% of humans)"
)
print(
    f"Bot posters:                  {len(bot_posters)}    ({sum(v['messages'] for v in bot_posters.values())} messages = {round(100 * sum(v['messages'] for v in bot_posters.values()) / sum(v['messages'] for v in posters.values()), 1)}% of message volume)"
)
print()
print("HUMAN POSTER ENGAGEMENT:")
print(
    f"  multi_week_active (7+ days):  {status['multi_week_active']:,}  ({round(100 * status['multi_week_active'] / len(human_posters), 1)}% of posters, {round(100 * status['multi_week_active'] / GROUND_TRUTH_HUMANS, 2)}% of all humans)"
)
print(
    f"  few_day_active (2-6 days):    {status['few_day_active']:,}  ({round(100 * status['few_day_active'] / len(human_posters), 1)}% of posters)"
)
print(
    f"  single_day_poster:            {status['single_day_poster']:,}  ({round(100 * status['single_day_poster'] / len(human_posters), 1)}% of posters)"
)
print(
    f"  one_time_poster:              {status['one_time_poster']:,}  ({round(100 * status['one_time_poster'] / len(human_posters), 1)}% of posters)"
)
print()
print("MESSAGE CONCENTRATION (human posters over human msgs):")
for n in [1, 5, 10, 25, 50, 100, 200]:
    print(
        f"  Top {n:>3}: {pct_msgs(n):>6}% of msgs, {pct_members(n):>6}% of 3,119 humans"
    )
print()
print("PEAKS:")
print(f"  Most new members:   {max(temporal, key=lambda x: x['new_members_joined'])}")
print(f"  Most messages:      {max(temporal, key=lambda x: x['human_messages'])}")
