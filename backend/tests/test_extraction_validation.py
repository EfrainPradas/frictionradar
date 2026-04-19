"""Extraction pipeline validation suite.

Tests every layer of the extraction system WITHOUT network calls
(unless marked as live). Designed to be runnable from:
  - CLI: pytest backend/tests/test_extraction_validation.py -v
  - API: POST /api/v1/validation/run (triggers this programmatically)

Structure:
  1. Constants & schemas
  2. Router decisions
  3. ATS adapter detection + parsing (mock data)
  4. HTTP static classifier + extractor (HTML fixtures)
  5. Playwright fallback contracts
  6. Dispatcher chain logic
  7. Pipeline compatibility (imports)
  8. Discovery module
"""

import sys
from pathlib import Path

# Ensure backend is importable
_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ════════════════════════════════════════════════════════════════════
# 1. CONSTANTS & SCHEMAS
# ════════════════════════════════════════════════════════════════════

def test_strategy_enum():
    from app.extraction.constants import ExtractionStrategy
    assert ExtractionStrategy.ATS_API.value == "ats_api"
    assert ExtractionStrategy.HTTP_STATIC.value == "http_static"
    assert ExtractionStrategy.PLAYWRIGHT.value == "playwright"


def test_reason_codes_complete():
    from app.extraction.constants import ReasonCode
    required = [
        "known_ats_json_available", "static_careers_page_detected",
        "spa_content_empty", "playwright_required", "cache_fresh",
        "fallback_from_ats_api", "fallback_from_http_static",
        "playwright_budget_exceeded", "playwright_capture_failed",
    ]
    values = {r.value for r in ReasonCode}
    for r in required:
        assert r in values, f"Missing reason code: {r}"


def test_ats_platforms():
    from app.extraction.constants import ATSPlatform, ATS_WITH_JSON_API
    assert ATSPlatform.GREENHOUSE in ATS_WITH_JSON_API
    assert ATSPlatform.LEVER in ATS_WITH_JSON_API
    assert ATSPlatform.ASHBY in ATS_WITH_JSON_API
    assert ATSPlatform.WORKDAY not in ATS_WITH_JSON_API


def test_normalized_jobs_result_empty():
    from app.extraction.schemas import NormalizedJobsResult
    r = NormalizedJobsResult(domain="test.com")
    assert not r.success
    assert r.jobs_count == 0


def test_normalized_jobs_result_with_data():
    from app.extraction.schemas import NormalizedJobsResult, NormalizedJob
    r = NormalizedJobsResult(domain="test.com", open_positions_count=42)
    r.jobs = [NormalizedJob(title="Engineer")]
    assert r.success
    assert r.jobs_count == 1


# ════════════════════════════════════════════════════════════════════
# 2. ROUTER DECISIONS
# ════════════════════════════════════════════════════════════════════

def test_router_cache_hit():
    from app.extraction.router import ExtractionRouter, RoutingContext
    from app.extraction.constants import ReasonCode
    ctx = RoutingContext(domain="cached.com", has_fresh_cache=True, cache_age_hours=1.0)
    d = ExtractionRouter().decide(ctx)
    assert d.reason == ReasonCode.CACHE_FRESH


def test_router_ats_api():
    from app.extraction.router import ExtractionRouter, RoutingContext
    from app.extraction.constants import ExtractionStrategy
    ctx = RoutingContext(domain="stripe.com", detected_ats_platform="greenhouse")
    d = ExtractionRouter().decide(ctx)
    assert d.strategy == ExtractionStrategy.ATS_API
    assert ExtractionStrategy.PLAYWRIGHT in d.fallback_chain


def test_router_ats_no_template():
    from app.extraction.router import ExtractionRouter, RoutingContext
    from app.extraction.constants import ExtractionStrategy, ReasonCode
    ctx = RoutingContext(domain="bigco.com", detected_ats_platform="workday")
    d = ExtractionRouter().decide(ctx)
    assert d.strategy == ExtractionStrategy.PLAYWRIGHT
    assert d.reason == ReasonCode.ATS_DETECTED_NO_TEMPLATE


def test_router_static_page():
    from app.extraction.router import ExtractionRouter, RoutingContext
    from app.extraction.constants import ExtractionStrategy
    ctx = RoutingContext(
        domain="example.com",
        careers_url="https://example.com/careers",
        careers_page_content_length=5000,
        careers_page_has_job_indicators=True,
    )
    d = ExtractionRouter().decide(ctx)
    assert d.strategy == ExtractionStrategy.HTTP_STATIC


def test_router_spa_shell():
    from app.extraction.router import ExtractionRouter, RoutingContext
    from app.extraction.constants import ExtractionStrategy, ReasonCode
    ctx = RoutingContext(
        domain="spa.com",
        careers_url="https://spa.com/careers",
        careers_page_content_length=150,
    )
    d = ExtractionRouter().decide(ctx)
    assert d.strategy == ExtractionStrategy.PLAYWRIGHT
    assert d.reason == ReasonCode.SPA_CONTENT_EMPTY


def test_router_no_url():
    from app.extraction.router import ExtractionRouter, RoutingContext
    from app.extraction.constants import ExtractionStrategy, ReasonCode
    ctx = RoutingContext(domain="unknown.com")
    d = ExtractionRouter().decide(ctx)
    assert d.strategy == ExtractionStrategy.PLAYWRIGHT
    assert d.reason == ReasonCode.NO_CAREERS_URL_FOUND


# ════════════════════════════════════════════════════════════════════
# 3. ATS ADAPTER DETECTION + PARSING
# ════════════════════════════════════════════════════════════════════

def test_greenhouse_detect():
    from app.extraction.adapters.greenhouse import GreenhouseAdapter
    gh = GreenhouseAdapter()
    assert gh.detect('<script src="https://boards.greenhouse.io/embed"></script>')
    assert not gh.detect("<html>no ats</html>")


def test_greenhouse_parse():
    from app.extraction.adapters.greenhouse import GreenhouseAdapter
    gh = GreenhouseAdapter()
    raw = {
        "jobs": [
            {
                "title": "Backend Engineer",
                "location": {"name": "NYC"},
                "departments": [{"name": "Engineering"}],
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "content": "<p>Build APIs</p>",
            },
            {
                "title": "PM",
                "location": {"name": "Remote"},
                "departments": [{"name": "Product"}],
            },
        ],
        "meta": {"total": 42},
    }
    result = gh.parse_jobs(raw, "https://api.greenhouse.io", "test.com")
    assert result.success
    assert result.open_positions_count == 42
    assert result.jobs_count == 2
    assert "Engineering" in result.hiring_areas
    assert result.jobs[0].title == "Backend Engineer"
    assert result.jobs[0].description_snippet is not None


def test_lever_detect():
    from app.extraction.adapters.lever import LeverAdapter
    lv = LeverAdapter()
    assert lv.detect('<iframe src="https://jobs.lever.co/company"></iframe>')
    assert not lv.detect("<html>normal</html>")


def test_lever_parse():
    from app.extraction.adapters.lever import LeverAdapter
    lv = LeverAdapter()
    raw = [
        {
            "text": "Data Analyst",
            "categories": {"team": "Data", "location": "SF"},
            "hostedUrl": "https://jobs.lever.co/co/123",
        },
        {
            "text": "Designer",
            "categories": {"team": "Design", "location": "Remote"},
        },
    ]
    result = lv.parse_jobs(raw, "https://api.lever.co/v0/postings/co", "test.com")
    assert result.success
    assert result.open_positions_count == 2
    assert result.jobs_count == 2
    assert "Data" in result.hiring_areas


def test_ashby_detect():
    from app.extraction.adapters.ashby import AshbyAdapter
    ab = AshbyAdapter()
    assert ab.detect('<script>ashbyhq.com</script>')
    assert not ab.detect("<html>normal</html>")


def test_ashby_parse():
    from app.extraction.adapters.ashby import AshbyAdapter
    ab = AshbyAdapter()
    raw = {
        "data": {
            "jobBoard": {
                "teams": [
                    {
                        "name": "Engineering",
                        "jobs": [
                            {"id": "a", "title": "SRE", "locationName": "NYC"},
                        ],
                    }
                ]
            }
        }
    }
    result = ab.parse_jobs(raw, "testslug", "test.com")
    assert result.success
    assert result.jobs_count == 1
    assert result.jobs[0].title == "SRE"


def test_adapter_registry():
    from app.extraction.adapters import ATS_ADAPTERS
    from app.extraction.constants import ATSPlatform
    assert ATSPlatform.GREENHOUSE in ATS_ADAPTERS
    assert ATSPlatform.LEVER in ATS_ADAPTERS
    assert ATSPlatform.ASHBY in ATS_ADAPTERS


# ════════════════════════════════════════════════════════════════════
# 4. CLASSIFIER + HTTP STATIC EXTRACTOR
# ════════════════════════════════════════════════════════════════════

def test_classifier_static_rich():
    from app.extraction.classifier import classify_page
    html = '<html><body><h1>Careers</h1>'
    for i in range(8):
        html += f'<div class="job-card"><a href="/j/{i}">Senior Engineer {i}</a></div>'
    html += "</body></html>"
    c = classify_page(html)
    assert c.page_type == "static_rich"
    assert c.confidence > 0.4


def test_classifier_spa_shell():
    from app.extraction.classifier import classify_page
    html = (
        '<html><body><div id="root"></div>'
        "<script>window.__NEXT_DATA__={}</script>"
        "<script>window.__APP_DATA__={}</script>"
        "<script>" + "x" * 5000 + "</script>"
        "</body></html>"
    )
    c = classify_page(html)
    assert c.page_type == "spa_shell"


def test_classifier_empty():
    from app.extraction.classifier import classify_page
    c = classify_page("")
    assert c.page_type == "unknown"


def test_http_static_jsonld():
    from app.extraction.http_static import extract_from_html
    html = """
    <html><body>
    <script type="application/ld+json">
    [{"@type": "JobPosting", "title": "Engineer", "jobLocation": {"address": {"addressLocality": "NYC"}}}]
    </script>
    </body></html>
    """
    result = extract_from_html(html, "https://co.com/careers", "co.com")
    assert result.success
    assert result.jobs_count >= 1
    assert result.jobs[0].title == "Engineer"


def test_http_static_dom_cards():
    from app.extraction.http_static import extract_from_html
    html = """
    <html><body>
    <h1>15 open positions</h1>
    <div class="job-card"><h3 class="title"><a href="/j/1">Senior Software Engineer</a></h3>
        <span class="location">NYC</span><span class="department">Engineering</span></div>
    <div class="job-card"><h3 class="title"><a href="/j/2">Product Manager</a></h3>
        <span class="location">SF</span><span class="department">Product</span></div>
    </body></html>
    """
    result = extract_from_html(html, "https://co.com/careers", "co.com")
    assert result.success
    assert result.open_positions_count == 15
    assert result.jobs_count >= 2


def test_http_static_link_fallback():
    from app.extraction.http_static import extract_from_html
    html = """
    <html><body><ul>
    <li><a href="/j/1">Senior Engineer - SF</a></li>
    <li><a href="/j/2">Product Manager - NYC</a></li>
    <li><a href="/j/3">Data Analyst - Remote</a></li>
    </ul></body></html>
    """
    result = extract_from_html(html, "https://co.com/careers", "co.com")
    assert result.success
    assert result.jobs_count >= 3


# ════════════════════════════════════════════════════════════════════
# 5. PLAYWRIGHT FALLBACK CONTRACTS
# ════════════════════════════════════════════════════════════════════

def test_playwright_budget_defaults():
    from app.extraction.playwright_fallback import DEFAULT_BUDGET
    assert DEFAULT_BUDGET.timeout_s == 45
    assert DEFAULT_BUDGET.capture_timeout_ms == 30000
    assert DEFAULT_BUDGET.max_attempts == 1
    assert DEFAULT_BUDGET.min_html_chars == 200


def test_playwright_reason_codes_exist():
    from app.extraction.constants import ReasonCode
    pw_codes = [r for r in ReasonCode if "playwright" in r.value]
    assert len(pw_codes) >= 4


# ════════════════════════════════════════════════════════════════════
# 6. DISPATCHER
# ════════════════════════════════════════════════════════════════════

def test_dispatcher_no_ats_returns_none():
    from app.extraction.dispatcher import try_ats_extraction
    r = try_ats_extraction(domain="random.com")
    assert r is None


def test_detect_ats_from_html():
    from app.extraction.dispatcher import detect_ats_from_html
    assert detect_ats_from_html('<div data-src="boards.greenhouse.io/x"></div>') == "greenhouse"
    assert detect_ats_from_html("<html>nothing</html>") is None


# ════════════════════════════════════════════════════════════════════
# 7. PIPELINE COMPATIBILITY
# ════════════════════════════════════════════════════════════════════

def test_collectors_import():
    from app.collectors import ACTIVE_COLLECTORS
    names = [c.collector_type for c in ACTIVE_COLLECTORS]
    assert "company_site" in names
    assert "careers" in names
    assert "ats_public" in names
    assert "newsroom" in names
    assert "dynamic_careers" in names


def test_scoring_import():
    from app.services.scoring_engine import compute_and_persist_score
    assert callable(compute_and_persist_score)


def test_evaluation_import():
    from app.services.company_evaluation import company_evaluation_engine
    assert hasattr(company_evaluation_engine, "evaluate")


def test_extraction_models_import():
    from app.models.extraction import (
        CompanyAtsDetection,
        CompanyExtractionCache,
        CompanyExtractionAttempt,
    )
    assert CompanyAtsDetection.__tablename__ == "company_ats_detection"


def test_all_extraction_imports():
    from app.extraction.constants import ExtractionStrategy, ReasonCode, ATSPlatform
    from app.extraction.schemas import NormalizedJobsResult, NormalizedJob
    from app.extraction.router import ExtractionRouter, RoutingContext
    from app.extraction.adapters import ATS_ADAPTERS
    from app.extraction.dispatcher import extract_company, try_ats_extraction
    from app.extraction.discovery import discover_careers_url
    from app.extraction.classifier import classify_page
    from app.extraction.http_static import extract_from_html
    from app.extraction.playwright_fallback import PlaywrightBudget
    from app.extraction.instrumentation import track_extraction
    assert True  # All imports succeeded


# ════════════════════════════════════════════════════════════════════
# 8. DISCOVERY MODULE
# ════════════════════════════════════════════════════════════════════

def test_discovery_result_dataclass():
    from app.extraction.discovery import DiscoveryResult
    d = DiscoveryResult()
    assert d.url is None
    assert d.strategy == "not_found"


# ════════════════════════════════════════════════════════════════════
# RUNNER — for programmatic execution from the API
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    """Run all tests and return a structured report.

    Called by the validation API endpoint.
    Returns: {passed, failed, errors, total, details: [{name, status, error}]}
    """
    import traceback

    tests = [
        # 1. Constants & schemas
        ("constants.strategy_enum", test_strategy_enum),
        ("constants.reason_codes", test_reason_codes_complete),
        ("constants.ats_platforms", test_ats_platforms),
        ("schemas.empty_result", test_normalized_jobs_result_empty),
        ("schemas.result_with_data", test_normalized_jobs_result_with_data),
        # 2. Router
        ("router.cache_hit", test_router_cache_hit),
        ("router.ats_api", test_router_ats_api),
        ("router.ats_no_template", test_router_ats_no_template),
        ("router.static_page", test_router_static_page),
        ("router.spa_shell", test_router_spa_shell),
        ("router.no_url", test_router_no_url),
        # 3. Adapters
        ("adapter.greenhouse_detect", test_greenhouse_detect),
        ("adapter.greenhouse_parse", test_greenhouse_parse),
        ("adapter.lever_detect", test_lever_detect),
        ("adapter.lever_parse", test_lever_parse),
        ("adapter.ashby_detect", test_ashby_detect),
        ("adapter.ashby_parse", test_ashby_parse),
        ("adapter.registry", test_adapter_registry),
        # 4. Classifier + HTTP static
        ("classifier.static_rich", test_classifier_static_rich),
        ("classifier.spa_shell", test_classifier_spa_shell),
        ("classifier.empty", test_classifier_empty),
        ("http_static.jsonld", test_http_static_jsonld),
        ("http_static.dom_cards", test_http_static_dom_cards),
        ("http_static.link_fallback", test_http_static_link_fallback),
        # 5. Playwright
        ("playwright.budget_defaults", test_playwright_budget_defaults),
        ("playwright.reason_codes", test_playwright_reason_codes_exist),
        # 6. Dispatcher
        ("dispatcher.no_ats_none", test_dispatcher_no_ats_returns_none),
        ("dispatcher.detect_html", test_detect_ats_from_html),
        # 7. Pipeline compat
        ("compat.collectors", test_collectors_import),
        ("compat.scoring", test_scoring_import),
        ("compat.evaluation", test_evaluation_import),
        ("compat.extraction_models", test_extraction_models_import),
        ("compat.all_extraction_imports", test_all_extraction_imports),
        # 8. Discovery
        ("discovery.dataclass", test_discovery_result_dataclass),
    ]

    passed = 0
    failed = 0
    errors = 0
    details = []

    for name, fn in tests:
        try:
            fn()
            passed += 1
            details.append({"name": name, "status": "passed"})
        except AssertionError as e:
            failed += 1
            details.append({"name": name, "status": "failed", "error": str(e)})
        except Exception as e:
            errors += 1
            details.append({
                "name": name,
                "status": "error",
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            })

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "total": len(tests),
        "success": failed == 0 and errors == 0,
        "details": details,
    }


if __name__ == "__main__":
    import json
    report = run_all_tests()
    print(json.dumps(report, indent=2))
