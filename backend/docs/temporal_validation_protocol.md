# FrictionRadar Temporal Intelligence Validation Protocol

**Version:** 1.0  
**Date:** 2026-05-18  
**Author:** Validation Methodology Team  
**Status:** Draft — Pre-Production Validation

---

## 1. Purpose

This document defines the validation protocol for FrictionRadar's Temporal Intelligence layer before production deployment. The layer comprises four engines — Score Delta, Signal Velocity, Temporal Diagnostic, and Temporal Eligibility Override — whose outputs feed the Temporal API endpoints and the frontend dashboard.

The goal is to answer: **Do temporal insights accurately reflect real-world company changes, and are they safe to expose to NovaWork positioning analysts?**

---

## 2. Company Selection

### 2.1 Eligibility Criteria

Select companies that meet **all** of the following:

| Criterion | Minimum | Rationale |
|-----------|---------|-----------|
| FrictionScore snapshots | ≥ 2 | Required for any delta computation |
| Scored signals | ≥ 5 | Minimum for MODERATE confidence |
| Scored signals (target) | ≥ 10 | Required for HIGH confidence subset |
| Collection runs | ≥ 2 | Confirms repeat collection, not single snapshot |
| Time span between first and last score | ≥ 7 days | Avoids same-day artificial deltas |

### 2.2 Company Selection Table (20 companies)

Select companies distributed across these dimensions:

| # | Company | Domain | Sector (inferred) | Size | Snapshot Count | Rationale for Inclusion |
|---|---------|--------|-------------------|------|---------------|--------------------------|
| 1 | _[fill]_ | | Software & SaaS | Mid-market | 2-3 | Known recent layoffs (public evidence) |
| 2 | _[fill]_ | | Fintech & Financial Services | Enterprise | 4+ | Recent funding round (public evidence) |
| 3 | _[fill]_ | | Healthcare & Biotech | Mid-market | 2-3 | Acquisition activity (public evidence) |
| 4 | _[fill]_ | | AI & Machine Learning | Startup | 3+ | Rapid hiring expansion (public evidence) |
| 5 | _[fill]_ | | Ecommerce & Consumer | Enterprise | 4+ | Known restructuring (public evidence) |
| 6 | _[fill]_ | | Professional Services | Mid-market | 2 | Stable company, no news (control case) |
| 7 | _[fill]_ | | Manufacturing & Industrial | Enterprise | 3+ | Earnings language change (public evidence) |
| 8 | _[fill]_ | | Semiconductors & Hardware | Enterprise | 4+ | Cyclical hiring pattern (public evidence) |
| 9 | _[fill]_ | | Media & Entertainment | Mid-market | 2-3 | Leadership change (public evidence) |
| 10 | _[fill]_ | | Logistics & Transportation | Mid-market | 3+ | Supply chain disruption (public evidence) |
| 11 | _[fill]_ | | Software & SaaS | Startup | 2 | Minimal data — should return INSUFFICIENT |
| 12 | _[fill]_ | | Education | Mid-market | 2 | Slow mover — should return STABLE_LOW or STABLE_ELEVATED |
| 13 | _[fill]_ | | Retail & Hospitality | Mid-market | 3+ | Seasonal hiring (public evidence) |
| 14 | _[fill]_ | | Telco & Internet Infra | Enterprise | 4+ | Engineering blog activity change (public evidence) |
| 15 | _[fill]_ | | Gaming | Mid-market | 2-3 | Post-launch contraction (public evidence) |
| 16 | _[fill]_ | | Real Estate & Construction | Mid-market | 2 | Quiet period — test false positives |
| 17 | _[fill]_ | | Energy & Utilities | Enterprise | 3+ | Regulatory change (public evidence) |
| 18 | _[fill]_ | | AI & Machine Learning | Startup | 2 | Recently added — low signal count |
| 19 | _[fill]_ | | Software & SaaS | Enterprise | 5+ | Highest snapshot count — test volatile detection |
| 20 | _[fill]_ | | Other | Any | 2 | Job market intermediary — should be filtered |

**Selection rules:**
- At least 5 companies with **known negative events** (layoffs, restructuring, acquisition disruption)
- At least 3 companies with **known positive events** (funding, expansion, new product launch)
- At least 3 **stable/control companies** with no significant news
- At least 2 companies expected to return **INSUFFICIENT** state
- At least 2 companies with **4+ snapshots** (test volatile/intermediate delta detection)

---

## 3. Evidence Sources for Cross-Validation

For each selected company, analysts must collect evidence from **at least 2** of the following sources:

| Source | Data Type | URL Pattern | Use Case |
|--------|-----------|-------------|----------|
| LinkedIn Jobs | Job posting volume | linkedin.com/jobs/view/ | Validate hiring_pressure changes |
| layoffs.fyi | Layoff announcements | layoffs.fyi | Confirm/report declining_pain |
| Crunchbase | Funding rounds, acquisitions | crunchbase.com | Validate emerging_pain triggers |
| SEC 10-K/10-Q filings | Earnings language, risk factors | sec.gov | Validate tooling_inconsistency, process_inefficiency |
| Company engineering blog | Dev activity signals | Various | Validate engineering_hiring signals |
| Glassdoor | Employee sentiment | glassdoor.com | Validate CX friction claims |
| Google News | News events | news.google.com | Corroborate signal velocity spikes |
| Company careers page | Job posting count | Direct | Validate hiring_pressure + functional_area |

### 3.1 Evidence Collection Window

| Lookback | Use |
|----------|-----|
| 7 days | Real-time velocity validation |
| 30 days | Primary validation window (matches default API parameter) |
| 90 days | Long-term trend validation |
| 180 days | Strategic trend validation for high-snapshot companies |

---

## 4. Validation Methodology

### 4.1 API Calls per Company

For each company, execute these API calls and record the full response:

```
GET /api/v1/companies/{id}/temporal/deltas?lookback_days=30
GET /api/v1/companies/{id}/temporal/signals/velocity?lookback_days=30
GET /api/v1/companies/{id}/temporal/diagnostic?lookback_days=30
GET /api/v1/companies/{id}/temporal/verdict?lookback_days=30
GET /api/v1/companies/{id}/temporal/deltas?lookback_days=90
GET /api/v1/companies/{id}/temporal/diagnostic?lookback_days=90
```

Also record baseline data:
```
GET /api/v1/companies/{id}/evaluation
GET /api/v1/companies/{id}/verdict
GET /api/v1/companies/{id}/signals
```

### 4.2 Validation Dimensions

#### 4.2.1 Delta Accuracy

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| Direction correct | Compare FR delta direction (IMPROVING/DECLINING/STABLE) vs. public evidence of change | Direction matches evidence for ≥ 80% of companies with evidence |
| Magnitude plausible | Compare FR magnitude (MILD/MODERATE/STRONG) vs. magnitude of real-world change | Magnitude within 1 level of analyst-assessed magnitude for ≥ 85% of companies |
| Overall score matches | Manually compute expected delta from public evidence of hiring/operational changes | FR delta sign matches analyst delta sign for ≥ 85% of companies |

#### 4.2.2 Trend Plausibility

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| State plausible | Compare FR `temporal_state` vs. analyst-assessed state from evidence | State matches or is 1 step more conservative for ≥ 85% of companies |
| Spike/drought alignment | Verify FR spike detection aligns with known event bursts (e.g., mass hiring, layoffs announcement week) | Spike/drought detected only when corroborated by evidence |
| Confidence proportional | Verify `confidence` level (HIGH/MODERATE/LOW/NONE) aligns with signal density | Confidence is HIGH only when snapshots ≥ 3 AND scored signals ≥ 10 AND both delta+velocity agree |

#### 4.2.3 Evidence Completeness

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| No phantom categories | Verify each `category_deltas` entry corresponds to real signals in the company | 0 phantom categories (no delta for a category with 0 signals) |
| Source coverage | Check `source_summary` against known data sources for the company | All active sources reflected; no missing sources that have data |
| Signal count accuracy | Manually verify `total_signals`, `scored_signals`, `discovery_signals` match DB counts | Counts match DB within 5% tolerance |

#### 4.2.4 False Positive Rate

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| Phantom emerging_pain | Identify companies where FR reports `emerging_pain` or `accelerating_pain` but public evidence shows stability | ≤ 10% of emerging/accelerating calls are contradicted by evidence |
| Phantom DECLINING | Identify companies where FR reports `declining_pain` but evidence shows worsening or stable | ≤ 10% of declining calls are contradicted by evidence |
| Ineligible companies promoted | Identify companies promoted via temporal override that shouldn't be | 0 inappropriate promotions (override only for companies where public evidence supports it) |

#### 4.2.5 False Negative Rate

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| Missed emerging pain | Identify companies with known worsening conditions that FR classifies as STABLE or INSUFFICIENT | ≤ 15% of known worsening companies are missed |
| Missed acceleration | Identify companies with rapid worsening that FR classifies as MILD delta | ≤ 10% of rapid worsening companies are underrated |
| Missed declining | Identify companies with known improvement that FR classifies as STABLE or INSUFFICIENT | ≤ 15% of known improving companies are missed |

#### 4.2.6 Actionability

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| Verdict useful | Analyst reads `verdict.what_we_know` and `next_best_step` — can they take action? | ≥ 80% of verdicts provide specific, actionable guidance |
| Temporal enrichment adds value | Compare verdict with vs. without temporal enrichment — does it change the recommendation? | Temporal enrichment changes the recommendation for ≥ 30% of companies with temporal data |
| Eligibility override correct | For companies promoted via temporal override, analyst confirms the promotion is warranted | 100% of temporal overrides confirmed by analyst |

---

## 5. Analyst Review Template

### 5.1 Per-Company Review Form

```markdown
## Company Review: [Company Name]

### Basic Info
- **Company ID:** [UUID]
- **Domain:** [domain.com]
- **Sector:** [inferred_sector]
- **Company Size:** [company_size]
- **Snapshot Count:** [N]
- **Scored Signals:** [N]
- **Lookback Window:** 30 days / 90 days

### Temporal API Output
- **Diagnostic State:** [state]
- **Confidence:** [level]
- **Evidence Strength:** [level]
- **Overall Delta:** [value] ([trend], [magnitude])
- **Top Changing Category:** [category] — delta=[value], trend=[direction]
- **Signal Velocity:** [value] signals/period, pressure=[state]
- **Spike Detected:** [yes/no]
- **Drought Detected:** [yes/no], drought_days=[N]
- **Verdict Type:** [preliminary/final]
- **Temporal Status:** [status]
- **Trend Direction:** [direction]
- **Eligibility:** [eligible/conditional/ineligible]
- **Temporal Override:** [none/early_positioning/accelerated_positioning]

### Analyst Ground Truth
- **Known events in lookback window:**
  1. [Event 1 — source, date, description]
  2. [Event 2 — source, date, description]
- **Analyst-assessed actual trend:** [improving/stable/declining/volatile/insufficient_data]
- **Analyst-assessed pain direction:** [none/emerging/accelerating/declining]
- **Analyst confidence in ground truth:** [high/moderate/low]

### Validation Checks
- [ ] Delta direction matches evidence
- [ ] Delta magnitude within 1 level of analyst assessment
- [ ] Trend state matches analyst-assessed state (or more conservative)
- [ ] Spike/drought detection aligns with known event timing
- [ ] Confidence proportional to signal density
- [ ] No phantom categories in deltas
- [ ] Verdict provides actionable guidance
- [ ] Eligibility override is appropriate (if applicable)

### Issues Found
- [Describe any discrepancy between FR output and ground truth]

### Overall Assessment
- [ ] PASS — Temporal output is accurate and actionable
- [ ] PASS WITH NOTES — Generally accurate, minor discrepancies documented
- [ ] FAIL — Significant inaccuracy that could mislead positioning
```

### 5.2 Summary Rollup

After reviewing all 20 companies, complete:

```markdown
## Validation Rollup

### Summary Statistics
- Companies reviewed: [N]
- PASS: [N] ([%])
- PASS WITH NOTES: [N] ([%])
- FAIL: [N] ([%])

### Accuracy Metrics
- Delta direction accuracy: [N/20] = [%]
- Delta magnitude within 1 level: [N/20] = [%]
- State plausibility: [N/20] = [%]
- False positive rate: [N/20] = [%]
- False negative rate: [N/20] = [%]
- Actionability rate: [N/20] = [%]

### Key Findings
1. [Finding 1]
2. [Finding 2]
3. [Finding 3]

### Recommended Threshold Changes
1. [Change 1]
2. [Change 2]

### Go/No-Go Recommendation
- [ ] GO — Proceed to production
- [ ] GO WITH CONDITIONS — Proceed with threshold adjustments
- [ ] NO GO — Do not proceed; requires engine fixes
```

---

## 6. Review Rubric

### 6.1 Per-Dimension Scoring

Each dimension is scored 1-5:

| Score | Label | Definition |
|-------|-------|------------|
| 5 | Excellent | Matches evidence precisely; no discrepancies |
| 4 | Good | Minor discrepancies that do not affect interpretation |
| 3 | Adequate | Discrepancies present but direction is correct |
| 2 | Marginal | Direction sometimes wrong; magnitude significantly off |
| 1 | Poor | Direction frequently wrong; cannot be trusted for decisions |

### 6.2 Dimension Weights

| Dimension | Weight | Rationale |
|-----------|--------|-----------|
| Delta accuracy | 25% | Core measurement — must be correct |
| Trend plausibility | 25% | Drives all downstream decisions |
| False positive rate | 20% | Wrong emerging_pain = wasted positioning effort |
| False negative rate | 15% | Missed emerging_pain = lost opportunity |
| Evidence completeness | 10% | Gaps undermine trust |
| Actionability | 5% | Verdict must drive action |

### 6.3 Composite Score Calculation

```
Composite = (Delta_Accuracy × 0.25) + (Trend_Plausibility × 0.25)
          + (False_Positive_Score × 0.20) + (False_Negative_Score × 0.15)
          + (Evidence_Completeness × 0.10) + (Actionability × 0.05)
```

---

## 7. Pass/Fail Criteria

### 7.1 Per-Company

| Criterion | PASS | PASS WITH NOTES | FAIL |
|-----------|------|-----------------|------|
| Delta direction | Matches evidence | Matches direction, off on magnitude | Wrong direction |
| Trend state | Matches or more conservative | 1 step off | 2+ steps off or opposite |
| False positives | None | 1 minor | Any that would trigger incorrect positioning |
| False negatives | None | 1 minor category miss | Miss known significant change |
| Actionability | Specific guidance | Guidance present but vague | No actionable output |

### 7.2 Aggregate (All 20 Companies)

| Metric | PASS Threshold | FAIL Threshold |
|--------|---------------|----------------|
| Delta direction accuracy | ≥ 80% | < 70% |
| Delta magnitude within 1 level | ≥ 85% | < 75% |
| Trend state plausibility | ≥ 85% | < 75% |
| False positive rate | ≤ 10% | > 20% |
| False negative rate | ≤ 15% | > 25% |
| Actionability rate | ≥ 80% | < 70% |
| Composite score | ≥ 3.5 | < 3.0 |
| Temporal override accuracy | 100% | < 90% |

**Any single metric in the FAIL column = overall FAIL, regardless of other metrics.**

---

## 8. Threshold Tuning

### 8.1 Current Thresholds and Tuning Guidance

| Threshold | Current | Tuning Range | Guidance |
|-----------|---------|--------------|----------|
| `MIN_SNAPSHOTS` (delta engine) | 2 | 2-4 | Increasing reduces false positives from noisy 2-point comparisons but delays detection. **Start at 2; increase to 3 only if validation shows excessive noise.** |
| `STABLE_THRESHOLD` (delta engine) | 0.02 | 0.01-0.05 | Lower = more sensitive to small changes. Higher = more stable classification. **0.02 is appropriate for 0-1 normalized scores.** |
| `MAGNITUDE_THRESHOLDS[NEGLIGIBLE]` | 0.02 | 0.01-0.03 | Tight threshold on normalized scale. **Keep at 0.02 unless per-category deltas are systematically under/over-estimated.** |
| `EMERGING_DELTA_THRESHOLD` | 0.25 | 0.15-0.40 | Controls when "emerging_pain" triggers. Lower = more sensitive (more emerging calls). **Lower to 0.20 if validation shows missed emerging pain. Raise to 0.35 if too many false emerging calls.** |
| `ACCELERATING_DELTA_THRESHOLD` | 0.75 | 0.50-1.00 | Controls when "accelerating_pain" triggers. **Keep at 0.75 unless high-snapshot companies show acceleration at lower thresholds.** |
| `SPIKE_MULTIPLIER` | 3.0 | 2.0-5.0 | Lower = more spike detection. **Lower to 2.5 if validation misses event-driven spikes. Raise to 4.0 if spikes are over-detected on normal variation.** |
| `DROUGHT_MIN_DAYS` | 7 | 5-14 | Lower = more drought detection. **Raise to 10-14 for weekly collection cadences. Keep at 7 for daily collection.** |
| `ACCELERATING_THRESHOLD` (velocity) | 0.5 | 0.3-1.0 | Signals/period acceleration. **Lower to 0.3 if validation shows missed acceleration. Raise to 0.75 if too many false acceleration calls.** |
| `_TEMPORAL_MIN_SIGNALS` | 5 | 3-10 | Minimum signals for temporal override. **Keep at 5 for initial deployment. Can lower to 3 once confidence is established.** |
| `_TEMPORAL_MIN_SCORED` | 3 | 2-5 | Minimum scored signals for temporal override. **Keep at 3. This is the minimum to have any meaningful pattern.** |
| `_TEMPORAL_MIN_SNAPSHOTS` | 2 | 2-3 | Minimum score snapshots for temporal override. **Keep at 2 for initial deployment. Raise to 3 once sufficient historical data exists.** |
| `ELEVATED_FRICTION_THRESHOLD` | 1.0 | 0.5-1.5 | 0-5 scale. **Keep at 1.0. This means at least 1 category is moderately affected.** |
| `LOW_FRICTION_THRESHOLD` | 0.3 | 0.1-0.5 | 0-5 scale. **Keep at 0.3. Below this, friction is negligible.** |

### 8.2 Tuning Process

```
1. Run validation protocol with current thresholds.
2. For each FAIL metric, identify which threshold(s) contribute to the failure.
3. Adjust ONE threshold at a time.
4. Re-run validation protocol on the SAME 20 companies.
5. Compare before/after metrics.
6. If improvement ≥ 5% on the failing metric without regression > 2% on others:
   → Accept the change.
7. If improvement < 5% or regression > 2% on others:
   → Reject and try a different threshold.
8. Document all changes in the Threshold Change Log (Section 8.3).
```

### 8.3 Threshold Change Log Template

| Date | Threshold | Old Value | New Value | Rationale | Validation Result | Approved By |
|------|-----------|-----------|-----------|-----------|-------------------|-------------|
| | | | | | | |

### 8.4 Safety Constraints

**Never adjust these thresholds simultaneously:**
- `EMERGING_DELTA_THRESHOLD` and `ACCELERATING_DELTA_THRESHOLD` — they form a tiered system; adjusting both at once makes it impossible to isolate effects.
- `SPIKE_MULTIPLIER` and `DROUGHT_MIN_DAYS` — they detect opposite extremes; adjusting both at once obscures velocity effects.
- `_TEMPORAL_MIN_SIGNALS` and `_TEMPORAL_MIN_SCORED` — they form a joint gate; adjust one, re-validate, then adjust the other.

**Always re-validate the full protocol after any threshold change.**

---

## 9. Go/No-Go Criteria for Production

### 9.1 GO (Deploy to Production)

All of the following must be true:

- [ ] Aggregate delta direction accuracy ≥ 80%
- [ ] Aggregate delta magnitude within 1 level ≥ 85%
- [ ] Aggregate trend state plausibility ≥ 85%
- [ ] False positive rate ≤ 10% (no incorrect emerging/accelerating calls that trigger positioning)
- [ ] False negative rate ≤ 15% (no missed significant worsening)
- [ ] Actionability rate ≥ 80%
- [ ] Composite score ≥ 3.5
- [ ] Temporal override accuracy = 100% (every override confirmed by analyst)
- [ ] Zero phantom categories in deltas across all 20 companies
- [ ] No INSUFFICIENT state returned for companies with ≥ 3 snapshots and ≥ 10 scored signals
- [ ] All API endpoints return correct HTTP status codes (200, 400, 404, 422)
- [ ] Frontend dashboard renders correctly for all 5 temporal states + insufficient data

### 9.2 GO WITH CONDITIONS

- [ ] All GO criteria met, AND
- [ ] 1-3 "PASS WITH NOTES" companies with documented minor discrepancies
- [ ] Threshold adjustment plan documented with expected resolution date
- [ ] Re-validation scheduled for after threshold changes

### 9.3 NO GO

Any of the following is sufficient:

- [ ] False positive rate > 20%
- [ ] False negative rate > 25%
- [ ] Composite score < 3.0
- [ ] Any temporal override confirmed incorrect by analyst
- [ ] Delta direction accuracy < 70%
- [ ] More than 3 companies with FAIL assessment

---

## 10. Validation Execution Checklist

### Pre-Validation

- [ ] Confirm all 20 companies have ≥ 2 FrictionScore snapshots in the database
- [ ] Confirm `computed_at` timestamps are correct (no NULL values)
- [ ] Confirm scored signals exist for each company
- [ ] Collect public evidence for each company (layoffs.fyi, Crunchbase, LinkedIn, news)
- [ ] Set up API access and authentication
- [ ] Prepare the spreadsheet template (Section 11)

### During Validation

- [ ] Execute all 6 API calls per company (3 lookback windows × 2 endpoints)
- [ ] Record full API responses in the spreadsheet
- [ ] For each company, complete the Analyst Review Form
- [ ] Flag any discrepancies between FR output and public evidence
- [ ] For each temporal override, document why it is or isn't warranted
- [ ] Test all 5 frontend dashboard states (render each company in the UI)

### Post-Validation

- [ ] Complete the Validation Rollup
- [ ] Calculate aggregate metrics
- [ ] Identify threshold adjustment candidates
- [ ] Make go/no-go recommendation
- [ ] Schedule re-validation if threshold changes are made

---

## 11. Spreadsheet Template

### 11.1 Company Data Sheet

| Column | Description | Example |
|--------|-------------|---------|
| company_id | UUID from database | `abc123...` |
| company_name | Human-readable name | Acme Corp |
| domain | Company website | acme.com |
| inferred_sector | FR-inferred sector | Software & SaaS |
| company_size | Size category | Mid-market |
| snapshot_count | FrictionScore rows | 4 |
| scored_signals | Scored signal count | 23 |
| lookback_30_state | Diagnostic state (30d) | emerging_pain |
| lookback_30_confidence | Confidence (30d) | moderate |
| lookback_30_delta | Overall delta (30d) | +0.42 |
| lookback_30_trend | Trend (30d) | declining |
| lookback_30_magnitude | Magnitude (30d) | moderate |
| lookback_30_velocity | Velocity (30d) | 2.3 signals/week |
| lookback_30_pressure | Pressure (30d) | accelerating |
| lookback_90_state | Diagnostic state (90d) | stable_elevated_friction |
| lookback_90_confidence | Confidence (90d) | high |
| eligibility | Static eligibility | ineligible |
| temporal_eligibility | Temporal override result | conditional (early_positioning) |

### 11.2 Evidence Sheet

| Column | Description | Example |
|--------|-------------|---------|
| company_id | UUID | `abc123...` |
| evidence_date | Date of event | 2026-04-15 |
| evidence_type | layoffs / funding / acquisition / earnings / hiring / blog / other | layoffs |
| evidence_source | URL or description | layoffs.fyi/company/acme |
| evidence_description | What happened | 150 employees laid off from engineering team |
| expected_friction_impact | How this should affect friction | +process, +scaling |
| expected_trend | improving/stable/declining/volatile | declining |
| analyst_confidence | high/moderate/low | high |

### 11.3 Accuracy Sheet

| Column | Description | Values |
|--------|-------------|--------|
| company_id | UUID | |
| delta_direction_correct | Does FR delta match evidence? | yes/no/partial |
| delta_magnitude_correct | Is magnitude within 1 level? | yes/no |
| trend_state_correct | Does FR state match evidence? | yes/conservative/aggressive/wrong |
| spike_detection_correct | Were spikes detected appropriately? | correct/false_positive/false_negative/n/a |
| drought_detection_correct | Were droughts detected appropriately? | correct/false_positive/false_negative/n/a |
| confidence_appropriate | Is confidence proportional to evidence? | yes/too_high/too_low |
| false_positive | Did FR flag something not in evidence? | none/emerging_pain/accelerating_pain/other |
| false_negative | Did FR miss something in evidence? | none/emerging_pain/declining_pain/other |
| override_appropriate | Is temporal override warranted? | yes/no/n/a |
| verdict_actionable | Can analyst take action from verdict? | yes/partially/no |
| overall_assessment | PASS / PASS_WITH_NOTES / FAIL | |

### 11.4 Threshold Sensitivity Sheet

| Threshold | Current | Value_A | Value_B | Metric_With_Current | Metric_With_A | Metric_With_B | Recommended |
|-----------|---------|---------|---------|---------------------|---------------|---------------|-------------|
| EMERGING_DELTA_THRESHOLD | 0.25 | 0.20 | 0.35 | | | | |
| ACCELERATING_DELTA_THRESHOLD | 0.75 | 0.50 | 1.00 | | | | |
| SPIKE_MULTIPLIER | 3.0 | 2.5 | 4.0 | | | | |
| DROUGHT_MIN_DAYS | 7 | 5 | 14 | | | | |
| ACCELERATING_THRESHOLD (velocity) | 0.5 | 0.3 | 0.75 | | | | |
| _TEMPORAL_MIN_SIGNALS | 5 | 3 | 10 | | | | |
| _TEMPORAL_MIN_SCORED | 3 | 2 | 5 | | | | |
| _TEMPORAL_MIN_SNAPSHOTS | 2 | 2 | 3 | | | | |

---

## 12. Recommended Threshold Adjustments (Pre-Validation Baseline)

Based on code review of the engine logic, these are the **recommended starting adjustments** to validate alongside current thresholds:

### 12.1 Conservative Deployment Profile (Recommended for Initial Launch)

| Threshold | Current | Conservative | Rationale |
|-----------|---------|-------------|-----------|
| EMERGING_DELTA_THRESHOLD | 0.25 | **0.30** | Reduce false emerging_pain calls during initial deployment |
| ACCELERATING_DELTA_THRESHOLD | 0.75 | **0.75** | Keep — already appropriately high |
| SPIKE_MULTIPLIER | 3.0 | **3.5** | Reduce noise-triggered spikes during initial deployment |
| DROUGHT_MIN_DAYS | 7 | **10** | Avoid false droughts from weekend/weekly collection gaps |
| _TEMPORAL_MIN_SIGNALS | 5 | **8** | Higher evidence bar for override during initial deployment |
| _TEMPORAL_MIN_SCORED | 3 | **5** | Higher evidence bar for override during initial deployment |
| _TEMPORAL_MIN_SNAPSHOTS | 2 | **3** | Require more history for override during initial deployment |

**Why conservative?** In production, false positives (wrongly promoting a company) are more harmful than false negatives (missing an opportunity). Conservative thresholds reduce the risk of analysts acting on incorrect temporal signals while we build confidence in the system.

### 12.2 When to Switch to Standard Profile

After 30 days of production data with:
- ≤ 5% false positive rate (confirmed by analyst review)
- ≥ 70% actionability rate
- No incorrect temporal overrides

Transition from Conservative → Standard (current) thresholds by adjusting one parameter per week and monitoring metrics.

### 12.3 Aggressive Profile (Future Consideration)

Only after 90 days of stable production metrics:
- Lower EMERGING_DELTA_THRESHOLD to 0.20
- Lower SPIKE_MULTIPLIER to 2.5
- Lower _TEMPORAL_MIN_SIGNALS to 3

---

## 13. Appendix: Temporal State Decision Tree

For analyst reference, the complete decision tree the engines follow:

```
START
│
├─ Scored signals < 5 AND no delta available?
│  └─ YES → INSUFFICIENT (confidence=NONE, evidence=WEAK)
│
├─ Delta trend = VOLATILE OR velocity pressure = SPIKE?
│  └─ YES → VOLATILE
│
├─ (Delta available AND overall_delta > 0.25) OR (no delta AND velocity = ACCELERATING)?
│  ├─ Delta magnitude ≥ 0.75 OR velocity = ACCELERATING?
│  │  └─ YES → ACCELERATING_PAIN
│  └─ NO → EMERGING_PAIN
│
├─ (Delta available AND overall_delta < -0.25) OR velocity = DECELERATING?
│  └─ YES → DECLINING_PAIN
│
├─ Velocity pressure = DROUGHT?
│  └─ YES → DECLINING_PAIN (signal drought)
│
├─ Current friction ≥ 1.0?
│  └─ YES → STABLE_ELEVATED
│
└─ Otherwise → STABLE_LOW
```

**Eligibility Override (applied after static gates):**
```
Static result = INELIGIBLE?
│
├─ Temporal state = INSUFFICIENT?
│  └─ YES → No override
│
├─ Static state = no_signal AND temporal confidence = NONE or LOW?
│  └─ YES → No override
│
├─ Temporal state = EMERGING_PAIN or ACCELERATING_PAIN?
│  └─ YES (AND confidence = MODERATE or HIGH, AND signals ≥ 5, scored ≥ 3, snapshots ≥ 2)
│     ├─ EMERGING_PAIN → CONDITIONAL (early_positioning)
│     └─ ACCELERATING_PAIN → CONDITIONAL (accelerated_positioning)
│
└─ Otherwise → No override
```

---

**Document History**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-05-18 | Validation Team | Initial protocol |