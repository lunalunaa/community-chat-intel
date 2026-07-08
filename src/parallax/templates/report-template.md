# Community Chat-History Analysis Findings

> **Template instructions:** `analyze.py` populates the `{{stats.foo.bar}}` placeholders automatically. After the pipeline runs, fill the `NARRATIVE:` prose sections manually based on what the numbers show. Keep the structure intact so successive report versions are directly comparable. Never paste raw user IDs, usernames, or direct message quotes — use `excerpts.md` for (paraphrased, redacted) illustrative examples.

**Period analyzed:** {{stats.metadata.date_range.0}} → {{stats.metadata.date_range.1}}
**Platform:** {{stats.metadata.channels}}
**Analyzed at:** {{stats.metadata.analyzed_at}}
**Pipeline version:** {{stats.metadata.pipeline_version}}

---

## TL;DR

NARRATIVE: Write 4-6 bullets capturing the most decision-relevant findings. Answer:
- How big is the target-language cohort relative to the overall community?
- Is it growing, stable, or shrinking?
- What's the single loudest pain point?
- Which tools/products dominate in this community, and is your product's UX aligned with that?
- Is brand confusion a real issue in this data?
- What, if anything, does this tell us about platform-integration demand?

---

## 1. Sample overview

| Metric | Value |
|---|---|
| Total messages analyzed | {{stats.metadata.total_messages}} |
| Channels in scope | {{stats.metadata.channels}} |
| Language distribution | {{stats.language_distribution}} |
| Total unique users | {{stats.users.total}} |
| Target-language-primary users | {{stats.users.target_primary}} |
| Bilingual users (target + other) | {{stats.users.bilingual}} |
| Other-language-primary users | {{stats.users.other_primary}} |
| **Target-language cohort (target + bilingual)** | **{{stats.users.target_plus_bilingual}}** |

Per-channel message counts: `{{stats.metadata.channel_message_counts}}`
Per-channel target-language message counts: `{{stats.metadata.channel_target_message_counts}}`

NARRATIVE: Interpret the scale. What fraction of the community is target-language? Is the target-language share concentrated in specific channels? Note any skew — e.g., "target-language users are disproportionately in #help," which has UX implications.

---

## 2. Timezone distribution (via posting-hour analysis)

Most target-language users post in these UTC clusters (used as a timezone proxy):

```
{{stats.location_proxy}}
```

- `region_evening` — modal post hour in the region's typical evening → likely in-region
- `na_evening` — modal post hour 0–6 UTC → likely North America
- `eu_evening` — modal post hour 18–22 UTC → likely Europe
- `other` — unclear / daytime / mixed

NARRATIVE: Does the cohort skew in-region or diaspora? This determines whether region-specific infrastructure (localized docs, regional service endpoints, local support channels) is load-bearing or whether internationally-hosted services are sufficient.

---

## 3. Retention — target-language cohort activity

| Cohort | Count |
|---|---|
| Active in last 30 days | {{stats.retention.target_active_30d}} |
| Lapsed 30–90 days | {{stats.retention.target_lapsed_30_90d}} |
| Lapsed 90+ days | {{stats.retention.target_lapsed_90d_plus}} |
| One-time posters (single message ever) | {{stats.retention.target_one_time_posters}} |

NARRATIVE: Lapsed rate is the most important single number for cohort product health. If >40% are lapsed/one-time, the onboarding-to-retention funnel is broken for this audience. Cross-reference with §7 pain points to hypothesize cause. Call out any notable cohort transitions (e.g., "peak onboarding was [month], then drop-off").

---

## 4. Top mentions (organic, not polled)

Raw mention counts across all target-language messages:

```
{{stats.providers}}
```

NARRATIVE: Rank by mention share. Which tools/products dominate in this community? Is there a clear in-region vs diaspora split — do in-region users mention different tools more? Compare to your product's supported set:
- Are users naming tools/products you already support? → good, UX is the lever
- Are they naming tools/products you do NOT support? → gap in coverage
- Is a specific tool/product mentioned at all? → signal on awareness of that integration (if you have one)

---

## 5. Alternatives

Organic mentions of alternative products in target-language conversations:

```
{{stats.competitors}}
```

NARRATIVE: Which alternatives surface organically? Interpretation guide:
- Heavy mentions of specific named alternatives → users think of your product next to these as alternatives or comparison points. Not inherently a loss signal — depends on sentiment (see excerpts.md).
- Mentions of alternatives philosophically closest to your own product → organic mentions here indicate users are actively evaluating you against them.
- No alternative mentions → the competitive landscape isn't on this audience's mental map despite industry-wide hype. Useful to know; means you aren't being framed as "yet another alternative" in this community.

---

## 6. Platforms

Organic mentions of platforms in target-language conversations:

```
{{stats.messaging_platforms}}
```

NARRATIVE: This is the most important single input to any "which platform should we integrate first" decision — what do users actually talk about when platforms come up? Rank order matters more than absolute count. Interpretation guide:
- One platform dominates → organic demand for that platform's integration
- Multiple platforms competitive → consider which aligns with your product strategy
- None mentioned significantly → users aren't blocked on platform integration; re-prioritize elsewhere

Cross-check with the "want to use vs using now" sentiment in excerpts.md.

---

## 7. Pain points

Raw counts of pain-point-related keywords in target-language messages:

```
{{stats.friction_signals}}
```

NARRATIVE: Rank the pain point types. Typical patterns:
- Access/blocked issues heavy → access friction is P1; alternative access methods or localized solutions become urgent.
- Generic errors / configuration issues heavy → config UX problem; a setup wizard + localized error messages are high-ROI.
- Confusion / help requests heavy → docs are failing; localized docs or LLM-translated docs become P1.
- Broken / failed with specific product context → bug triage priority.

Identify the top 3 pain point types and reference illustrative excerpts in `excerpts.md`.

---

## 8. Setup methods

Mentions of setup/deploy methods in target-language messages:

```
{{stats.install_paths}}
```

NARRATIVE: What setup surfaces are users on? If a specific method dominates (e.g., container-based, OS-native, or hosted), prioritize documentation and support for that path. A hosted option that's heavily used → hosted experience is winning; self-install friction is a smaller issue than it seems.

---

## 9. Topic mentions (depth signal)

```
{{stats.features}}
```

NARRATIVE: Are users engaging with your product's notable features, or using it as a thin UI? High mentions of key topics → community content should showcase advanced workflows. Low mentions → marketing and docs should lead with key capabilities; users aren't discovering the value. Cross-tab with pain points: if a topic is mentioned but so is confusion → that area has UX friction even for users who know about it.

---

## 9b. LLM-tagged topic distribution (optional; requires `topics.py` pass)

If `topics.py` has been run, the aggregate topic distribution is:

```
{{stats.topics.counts}}
```

Total tagged: {{stats.topics.total_tagged}}

NARRATIVE: Topic distribution tells you what the cohort is *actually talking about* once you sum across keyword hits. Typical interpretation:
- Heavy setup/config + install topics → onboarding UX is the primary support burden; docs and config UX fixes are high-ROI
- Heavy platform-integration topics → users are actively trying to wire your product into their platforms; integration completeness matters
- Heavy bug reports → a stable-release quality problem
- Heavy feature requests → indicates product pull but unmet demand
- Heavy general discussion → healthy community but no strong signal
- Significant brand-identity topics → users are confused about what's official; brand-protection priority

Cross-reference with §10 (brand confusion), §7 (pain points), §6 (platforms). `topics_by_category.json` gives per-category message-ID lists if you want to pull representative examples (paraphrase for `excerpts.md`).

---

## 10. Brand confusion — external domain mentions

External domain mentions (both as URLs and bare-text references):

```
{{stats.urls.impersonator_domains}}
```

Official domain mentions:

```
{{stats.urls.official_domains}}
```

Full URL category breakdown:

```
{{stats.urls.category_counts}}
```

Top 50 domains mentioned overall:

```
{{stats.urls.top_domains}}
```

NARRATIVE: Compare external/unofficial domain mentions vs official domain mentions. If unofficial mentions are non-trivial (>5% of domain mentions), brand-protection priority escalates. If unofficial mentions are *in* question contexts ("is X official?"), users are uncertain — publishing a canonical "official presence" statement is cheap and high-value. If unofficial mentions are in *recommendation* contexts ("I followed this guide from X"), third-party sites are actively serving as your documentation — risk is much higher. Excerpts in `excerpts.md` should disambiguate this.

---

## 11. External communities

Where users say they hang out outside this chat:

```
{{stats.shadow_community_mentions}}
```

NARRATIVE: Which external communities surface? These are the platforms where your community's attention lives outside the chat you're analyzing. High mentions of a specific platform → that's where content and engagement investment should go. The specific platforms will vary by region — see your `RegionProfile` in `languages.py` for the configured set.

---

## 12. Help-answered rate

| Metric | Value |
|---|---|
| Total questions asked (all languages) | {{stats.help_answered.total_questions}} |
| Target-language questions asked | {{stats.help_answered.target_questions}} |
| Target-language questions answered within 48h | {{stats.help_answered.target_questions_answered_within_48h}} |
| **Target-language answered rate** | **{{stats.help_answered.target_answered_rate}}** |

NARRATIVE: The answered-rate is a direct community-health signal. If <70%, target-language users are being under-served by the existing help system. If <50%, questions are effectively getting ignored and users will leave for communities that help them. Interpretation guide:
- Low rate + heavy confusion / help-request pain points → need a moderator or LLM-based auto-responder; at minimum, a pinned FAQ.
- Low rate + specific topic clusters unanswered (e.g., a specific integration setup, a specific config issue) → targeted docs fix those specific cases.
- High rate → the existing volunteer ecosystem is working; focus resources elsewhere.

---

## 13. Discovery channels

Organic mentions of how users found your product:

```
{{stats.acquisition_channels}}
```

NARRATIVE: These are noisy signals from messages like "I saw it on [X]" or "found this via [Y]." Treat counts as directional, not authoritative. If developer-native platforms dominate → developer channels are working. If local platforms dominate → localized content marketing is the driver. If international social platforms dominate → international pipeline is working. Use this to allocate where new content should be published.

---

## 14. Cross-tabulations (see `crosstabs.py`)

NARRATIVE: Fill these in from `crosstabs.json` / `crosstabs.md`, or extend the pipeline. The highest-value cross-tabs:

1. **Top mentions × Timezone distribution** — are in-region users more likely to mention different tools/products than overseas users?
2. **Platforms × Retention** — do users who mention specific platforms stick around longer? (Selection bias hazard; interpret carefully.)
3. **Brand confusion × Pain points** — do users who referenced unofficial sites report more confusion?
4. **Topic mentions × Retention** — do users who mention key topics retain better? (The "are notable features sticky" question.)
5. **Setup methods × Pain points** — do users on a specific setup method hit more friction than others?

---

## 15. Recommendations (analyst synthesis)

NARRATIVE: After reading §1–§14, write 3–6 concrete recommendations in this section. Map each to a priority tier:

- **P0 (this week):** ____________
- **P1 (this quarter):** ____________
- **P2 (next quarter):** ____________
- **Explicitly NOT recommended:** ____________

Tie each recommendation back to at least one numerical finding above, so reviewers can audit the reasoning.

---

## 16. Known limitations

Most important for this specific run:

- Self-selection: only users who joined this chat and posted are counted. Lurkers and non-joiners are invisible.
- Language classification is heuristic; heavy code-switching may be misclassified. Reviewed samples indicate ~{{NARRATIVE: describe spot-check accuracy, e.g., "~90% accurate on a 50-message sample"}}.
- Unofficial-domain mention context is not auto-classified. See excerpts.md for disambiguation.
- Lapsed users are observationally equivalent to retained-but-quiet users — "stopped using the product" is not directly recoverable.
- Regional clustering and external-community platform lists are illustrative starting points, not exhaustive — extend them for your market.

---

## Appendices

- `users.json` — per-user profiles (hashed IDs, redacted display names unless `--keep-names`)
- `stats.json` — machine-readable version of all numbers in this report
- `excerpts.md` — paraphrased illustrative quotes (produce manually, redact identifying features)
- `user_hash_salt.key` — salt file (DO NOT share outside analysis team; stored outside repo)

---

## Version history

| Version | Date | Notes |
|---|---|---|
| 0.1 | {{stats.metadata.analyzed_at}} | Initial automated analysis pass |
