# Community Chat-History Analysis Findings

> **Template instructions:** `analyze.py` populates the `\{{stats.foo.bar}}` placeholders automatically. After the pipeline runs, fill the `NARRATIVE:` prose sections manually based on what the numbers show. Keep the structure intact so successive report versions are directly comparable. Never paste raw user IDs, usernames, or direct message quotes — use `excerpts.md` for (paraphrased, redacted) illustrative examples.

**Period analyzed:** {{stats.metadata.date_range.0}} → {{stats.metadata.date_range.1}}
**Platform:** {{stats.metadata.channels}}
**Analyzed at:** {{stats.metadata.analyzed_at}}
**Pipeline version:** {{stats.metadata.pipeline_version}}

---

## TL;DR

NARRATIVE: Write 4-6 bullets capturing the most decision-relevant findings. Answer:
- How big is the Chinese-speaking cohort relative to the overall community?
- Is it growing, stable, or shrinking?
- What's the single loudest product pain point?
- Which Chinese providers dominate, and is your product's UX aligned with that?
- Are impersonator sites a real issue in this data?
- What, if anything, does this tell us about Feishu / WeChat / other IM platform demand?

---

## 1. Sample overview

| Metric | Value |
|---|---|
| Total messages analyzed | {{stats.metadata.total_messages}} |
| Channels in scope | {{stats.metadata.channels}} |
| Language distribution | {{stats.language_distribution}} |
| Total unique users | {{stats.users.total}} |
| Chinese-primary users | {{stats.users.zh_primary}} |
| Bilingual users (Chinese + other) | {{stats.users.bilingual}} |
| English-primary users | {{stats.users.en_primary}} |
| **Chinese-speaking cohort (zh + bilingual)** | **{{stats.users.zh_plus_bilingual}}** |

Per-channel message counts: `{{stats.metadata.channel_message_counts}}`
Per-channel Chinese/mixed message counts: `{{stats.metadata.channel_zh_message_counts}}`

NARRATIVE: Interpret the scale. What fraction of the community is Chinese-speaking? Is the Chinese share concentrated in specific channels (e.g., #help, #general, or a dedicated #chinese channel)? Note any skew — e.g., "Chinese users are disproportionately in #help," which has UX implications.

---

## 2. Location proxy (via posting-hour analysis)

Most Chinese-speaking users post in these UTC clusters (used as a timezone proxy):

```
{{stats.location_proxy}}
```

- `mainland_evening` — modal post hour 12–16 UTC = evening 20–24 Beijing (UTC+8) → likely Mainland China
- `na_evening` — modal post hour 0–6 UTC = evening 16–22 PT / 20–02 ET → likely North America
- `eu_evening` — modal post hour 18–22 UTC = evening 20–24 CET → likely Europe
- `other` — unclear / daytime / mixed

NARRATIVE: Does the Chinese cohort skew mainland or diaspora? This determines whether mainland-specific moves (a domestic model mirror, a China-market provider UX, WeChat Official Account presence, ICP-filed docs site) are load-bearing or whether international-hosted services are sufficient.

---

## 3. Retention — Chinese cohort activity

| Cohort | Count |
|---|---|
| Active in last 30 days | {{stats.retention.zh_active_30d}} |
| Lapsed 30–90 days | {{stats.retention.zh_lapsed_30_90d}} |
| Lapsed 90+ days | {{stats.retention.zh_lapsed_90d_plus}} |
| One-time posters (single message ever) | {{stats.retention.zh_one_time_posters}} |

NARRATIVE: Lapsed rate is the most important single number for Chinese-cohort product health. If >40% are lapsed/one-time, the onboarding-to-retention funnel is broken for this audience. Cross-reference with §7 friction signals to hypothesize cause. Call out any notable cohort transitions (e.g., "peak Chinese onboarding was [month], then drop-off").

---

## 4. Model provider mentions (organic, not polled)

Raw mention counts across all Chinese/mixed messages:

```
{{stats.providers}}
```

NARRATIVE: Rank by mention share. Which Chinese-made providers (DeepSeek, Kimi, GLM, Qwen, Volcengine, MiniMax, Doubao) dominate vs Western (Anthropic, OpenAI, Gemini, OpenRouter)? Is there a clear mainland/diaspora split — do mainland-evening users mention Chinese providers more? Compare to your product's supported-providers list:
- Are users naming providers you already support? → good, provider UX is the lever
- Are they naming providers you do NOT support? → gap in provider coverage
- Is a specific Chinese provider mentioned at all? → signal on awareness of that provider's integration (if you have one)

---

## 5. Competitor mentions

Organic mentions of competitor products in Chinese-speaker conversations:

```
{{stats.competitors}}
```

NARRATIVE: Which competitors surface organically? Interpretation guide:
- Heavy mentions of specific named competitors → Chinese users think of your product next to these as alternatives or comparison points. Not inherently a loss signal — depends on sentiment (see excerpts.md).
- Mentions of competitors philosophically closest to your own product → organic mentions here indicate users are actively evaluating you against them.
- No competitor mentions → the competitive landscape isn't on this audience's mental map despite industry-wide hype. Useful to know; means you aren't being framed as "yet another alternative" in this community.

---

## 6. Messaging-platform mentions

Organic mentions of IM platforms in Chinese-speaker conversations:

```
{{stats.messaging_platforms}}
```

NARRATIVE: This is the most important single input to any "which IM platform should we integrate first" decision — what do Chinese users actually talk about when messaging platforms come up? Rank order matters more than absolute count. Interpretation guide:
- Feishu/飞书 dominates → a Feishu adapter has organic demand.
- WeChat/微信 or WeCom/企业微信 dominates → pivot: the priority adapter is WeChat, not Feishu.
- DingTalk/钉钉 competitive → consider a DingTalk adapter alongside or instead of Feishu.
- None of them mentioned significantly → Chinese users aren't blocked on IM integration; re-prioritize elsewhere.

Cross-check with the "want to use vs using now" sentiment in excerpts.md.

---

## 7. Friction signals

Raw counts of friction-related keywords in Chinese-speaker messages:

```
{{stats.friction_signals}}
```

NARRATIVE: Rank the friction types. Typical patterns:
- `vpn_blocked` heavy → network-access friction is P1; a domestic mirror + Chinese-provider default routing become urgent.
- `error_generic` / `key_issue` / `oauth_issue` heavy → config UX problem; a Chinese-provider setup wizard + Chinese-language error messages are high-ROI.
- `confused` / `help_request` heavy → docs are failing; Chinese-language docs or LLM-translated docs become P1.
- `broken` / `failed` with specific product context → bug triage priority.

Identify the top 3 friction types and reference illustrative excerpts in `excerpts.md`.

---

## 8. Install paths

Mentions of deploy/install paths in Chinese-speaker messages:

```
{{stats.install_paths}}
```

NARRATIVE: What install surfaces are Chinese users on? If WSL heavy → Windows-native documentation investment is warranted. If Docker heavy → containerized-deploy story matters. If a hosted-service option is heavily used → hosted experience is winning; self-install friction is a smaller issue than it seems.

---

## 9. Feature usage (depth signal)

```
{{stats.features}}
```

NARRATIVE: Are Chinese users engaging with your product's differentiator features, or using it as a thin chat UI? High mentions of differentiator features → community content should showcase advanced workflows. Low mentions → marketing and docs should lead with differentiators; users aren't discovering the value. Cross-tab with friction: if a differentiator feature is mentioned but so is `confused` → that feature has UX friction even for users who know about it.

---

## 9b. LLM-tagged topic distribution (optional; requires `topics.py` pass)

If `topics.py` has been run, the aggregate topic distribution is:

```
{{stats.topics.counts}}
```

Total tagged: {{stats.topics.total_tagged}}

NARRATIVE: Topic distribution tells you what the Chinese cohort is *actually talking about* once you sum across keyword hits. Typical interpretation:
- Heavy `provider_config` + `install_help` → onboarding UX is the primary support burden; docs and provider-config UX fixes are high-ROI
- Heavy `messaging_adapter` → users are actively trying to wire your product into their IM platforms; adapter completeness matters
- Heavy `bug_report` → a stable-release quality problem
- Heavy `feature_request` → indicates product pull but unmet demand
- Heavy `general_discussion` → healthy community but no strong signal
- Significant `brand_identity` → users are confused about what's official; brand-protection priority

Cross-reference with §10 (brand audit), §7 (friction), §6 (messaging platforms). `topics_by_category.json` gives per-category message-ID lists if you want to pull representative examples (paraphrase for `excerpts.md`).

---

## 10. Brand audit — impersonator domain mentions

Impersonator domain mentions (both as URLs and bare-text references):

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

NARRATIVE: Compare `impersonator_domains` vs `official_domains` mention counts. If impersonator mentions are non-trivial (>5% of Chinese-domain mentions), brand-protection priority escalates. If impersonator mentions are *in* question contexts ("is X official?"), users are uncertain — publishing a canonical "official Chinese-language presence" statement is cheap and high-value. If impersonator mentions are in *recommendation* contexts ("I followed this guide from X"), impersonator sites are actively serving as your documentation — risk is much higher. Excerpts in `excerpts.md` should disambiguate this.

---

## 11. Shadow community mentions

Where Chinese users say they hang out outside this chat:

```
{{stats.shadow_community_mentions}}
```

NARRATIVE: Which external communities surface? Typical pattern for Chinese AI communities:
- WeChat groups / Official Accounts → often the actual center of gravity. If mentioned frequently, these are where Chinese community engagement strategy should focus.
- Zhihu → where technical long-form discussion happens. High mentions → a Zhihu organizational account is high-ROI content investment.
- Bilibili → where tutorial / walkthrough content lives. High mentions → a Bilibili channel is the video-content play.
- Xiaohongshu → younger/creator audience. Lower priority for developer-tool content usually.

---

## 12. Help-answered rate

| Metric | Value |
|---|---|
| Total questions asked (all languages) | {{stats.help_answered.total_questions}} |
| Chinese/mixed questions asked | {{stats.help_answered.zh_questions}} |
| Chinese/mixed questions answered within 48h | {{stats.help_answered.zh_questions_answered_within_48h}} |
| **Chinese-question answered rate** | **{{stats.help_answered.zh_answered_rate}}** |

NARRATIVE: The answered-rate is a direct community-health signal. If <70%, Chinese users are being under-served by the existing help system. If <50%, Chinese questions are effectively getting ignored and users will leave for communities that help them. Interpretation guide:
- Low rate + heavy `help_request` / `confused` friction → need a Chinese-speaking mod or LLM-based auto-responder; at minimum, a pinned Chinese FAQ.
- Low rate + specific topic clusters unanswered (e.g., a specific adapter setup, a specific provider config) → targeted docs fix those specific cases.
- High rate → the existing volunteer ecosystem is working; focus resources elsewhere.

---

## 13. Acquisition-channel markers

Organic mentions of how users found your product:

```
{{stats.acquisition_markers}}
```

NARRATIVE: These are noisy signals from messages like "I saw it on [X]" or "found this via [Y]." Treat counts as directional, not authoritative. If GitHub / HuggingFace dominate → developer-native channels are working. If WeChat / Zhihu / personal blogs dominate → Chinese-language content marketing is the driver. If Twitter/X dominates → overseas diaspora pipeline is working. Use this to allocate where new Chinese-language content should be published.

---

## 14. Cross-tabulations (see `crosstabs.py`)

NARRATIVE: Fill these in from `crosstabs.json` / `crosstabs.md`, or extend the pipeline. The highest-value cross-tabs:

1. **Provider × Location proxy** — are mainland users more likely to mention Chinese providers than overseas users?
2. **Messaging platform × Retention** — do users who mention Feishu/WeChat stick around longer? (Selection bias hazard; interpret carefully.)
3. **Impersonator mention × Friction** — do users who referenced impersonator sites report more confusion?
4. **Feature usage × Retention** — do users who mention your differentiator features retain better? (The "are differentiators sticky" question.)
5. **Install path × Friction** — do WSL users hit more friction than Linux-native?

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

See `plan.md` §7 for full list. Most important for this specific run:

- Self-selection: only users who joined this chat and posted are counted. Lurkers and non-joiners are invisible.
- Language classification is heuristic; heavy code-switching may be misclassified. Reviewed samples indicate ~{{NARRATIVE: describe spot-check accuracy, e.g., "~90% accurate on a 50-message sample"}}.
- Impersonator-domain mention context is not auto-classified. See excerpts.md for disambiguation.
- Lapsed users are observationally equivalent to retained-but-quiet users — "stopped using the product" is not directly recoverable.
- No LLM topic-tagging pass was run. Rerun with topic tagging for a richer §9.

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
