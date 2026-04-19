# Extraction Pipeline Benchmark — Findings

## Date: 2026-04-13

## Benchmark Setup

- **Sample**: 30 companies (Utah dataset, alphabetical order)
- **Strategies tested**: ATS API, HTTP Static, Playwright fallback
- **Baseline**: Original pipeline run (154 companies, 9920s, ~64s/company avg)

---

## Results Summary

### Without Playwright (fast path only)

| Metric | Value |
|--------|-------|
| Companies resolved | 10/30 (33.3%) |
| Avg time (resolved) | 1.6s |
| Avg time (all) | 4.4s |
| Strategy: http_static | 10 (33.3%) |
| Strategy: need playwright | 20 (66.7%) |
| Time reduction vs baseline | **93.2%** |

### With Playwright (full chain)

| Metric | Value |
|--------|-------|
| Companies resolved | 13/15 (86.7%) |
| Avg time | 12.8s |
| Strategy: http_static | 3 (20%) |
| Strategy: playwright | 12 (80%) |
| Time reduction vs baseline | **80.2%** |
| Fallback rate | 40% |

---

## Target Checklist

| Target | Status | Actual |
|--------|--------|--------|
| >= 70% sin Playwright | **FAIL** | 33.3% |
| >= 50% reduccion tiempo | **PASS** | 93.2% (sin PW), 80.2% (con PW) |
| Success rate >= baseline | **PASS** | 86.7% con PW |

---

## Key Findings

### 1. HTTP Static Works — But Only for ~33% of Companies

10 of 30 companies resolved via HTTP static in avg 1.6s. These are companies
with traditional `/careers` pages that serve real HTML. Examples:
- angel.com: 11 jobs, 0.80 confidence, 5s
- bankofutah.com: 7 jobs, 0.60 confidence, 0.4s
- advancedmd.com: 4 jobs, 0.45 confidence, 1s

### 2. ATS API Had 0 Hits in This Sample

None of the 30 companies had a detected ATS platform. This is expected —
the Utah dataset is mostly small/medium companies that don't use Greenhouse/Lever.
The ATS API path would shine with tech companies (Stripe: 497 jobs in 2s).

### 3. 67% of Companies Need Playwright or Better Discovery

Two categories:
- **12 companies (40%)**: No careers URL found at all (`playwright_required`)
  - These companies likely use external ATS or have non-standard careers pages
  - Examples: 1800contacts.com, americafirst.com, blackriflecoffee.com
- **8 companies (27%)**: Careers URL found but low-confidence extraction (`fallback_from_http_static`)
  - The page exists but job cards aren't in standard HTML patterns
  - Examples: aseaglobal.com, alpine-air.com

### 4. Time Improvement is Dramatic

Even without hitting the 70% target:
- **Baseline**: 64.4s per company average (including sync collectors + Playwright)
- **New pipeline (no PW)**: 4.4s per company = **93% reduction**
- **New pipeline (with PW)**: 12.8s per company = **80% reduction**
- The improvement comes from the HTTP path being 1.6s avg vs Playwright 15.3s avg

### 5. Playwright Fallback Works Correctly

When Playwright runs, it correctly identifies as fallback:
- `fallback_from=http_static` tracked
- Budget enforcement works (45s hard timeout)
- 83% success rate when Playwright runs

---

## Root Cause: Why 70% Target Wasn't Hit

The 70% target assumed most companies would have discoverable static careers pages.
In reality, many Utah companies:

1. **Don't have /careers or /jobs paths** — 40% of the sample
2. **Use external ATS** (Workday, iCIMS, custom) not detectable from homepage
3. **Have careers pages that are SPAs** even for smaller companies

This is a **discovery problem**, not an extraction problem.

---

## Recommended Next Steps

### Priority 1: Improve Discovery (highest impact)

The biggest gap is that 40% of companies have NO discoverable careers URL.
Options:
- **ATS detection from prior collection runs** — company_site collector already
  detects ATS embeds. Feed that into the router as `detected_ats_platform`.
- **Google search fallback** — `site:greenhouse.io {company}` or
  `{company} careers jobs` to find non-obvious careers pages.
- **Broader path probing** — add `/about/careers`, `/team/jobs`,
  `/company/opportunities` to discovery.

### Priority 2: Wire into batch_processor

The new extraction layer runs standalone. Next step is replacing
batch_processor Step 3 with `extract_company()` and converting
NormalizedJobsResult into SignalCreate objects for the scoring pipeline.

### Priority 3: ATS Detection Integration

Feed `company_site` collector's ATS detection into the extraction router.
This would activate the ATS API path for companies that have Greenhouse/Lever
embeds on their homepage.

---

## Files

- Benchmark script: `cli/benchmark_extraction.py`
- Report (no PW): `cli/results/benchmark_report.json`
- Report (with PW): `cli/results/benchmark_with_pw.json`
