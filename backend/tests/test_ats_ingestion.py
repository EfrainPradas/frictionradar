"""
ATS adapter ingestion path tests.

Verifies the API-first → HTTP parse → Playwright fallback pipeline:
  1. GreenhouseAdapter: detect, resolve_endpoint, fetch_jobs, parse_jobs
  2. LeverAdapter: detect, resolve_endpoint, fetch_jobs, parse_jobs
  3. AshbyAdapter: detect, resolve_endpoint, fetch_jobs, parse_jobs
  4. NormalizedJobsResult contract: success property, required fields
  5. BaseATSAdapter retry logic: transient errors retried, permanent errors fail fast
  6. slugify_company generates plausible slugs
  7. Full extract() pipeline: API success → no Playwright fallback
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from app.extraction.adapters.base import BaseATSAdapter, slugify_company
from app.extraction.adapters.greenhouse import GreenhouseAdapter
from app.extraction.adapters.lever import LeverAdapter
from app.extraction.adapters.ashby import AshbyAdapter
from app.extraction.constants import ATSPlatform, ExtractionStrategy, ReasonCode
from app.extraction.schemas import NormalizedJob, NormalizedJobsResult


# ---------------------------------------------------------------------------
# Greenhouse adapter
# ---------------------------------------------------------------------------

class TestGreenhouseDetect:
    """Greenhouse detection should match known HTML patterns."""

    def test_detect_greenhouse_embed(self):
        adapter = GreenhouseAdapter()
        assert adapter.detect('<script src="https://boards.greenhouse.io/embed"></script>') is True

    def test_detect_greenhouse_url(self):
        adapter = GreenhouseAdapter()
        assert adapter.detect("Visit boards.greenhouse.io/acme for jobs") is True

    def test_no_false_positive(self):
        adapter = GreenhouseAdapter()
        assert adapter.detect("<html><body>No ATS here</body></html>") is False

    def test_platform_attribute(self):
        assert GreenhouseAdapter.platform == ATSPlatform.GREENHOUSE


class TestGreenhouseParse:
    """Greenhouse parse_jobs should extract structured data from raw JSON."""

    def test_parse_typical_response(self):
        adapter = GreenhouseAdapter()
        raw_data = {
            "jobs": [
                {
                    "title": "Senior Engineer",
                    "location": {"name": "Remote"},
                    "departments": [{"name": "Engineering"}],
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
                    "content": "<p>Build amazing products</p>",
                },
                {
                    "title": "Product Manager",
                    "location": {"name": "New York"},
                    "departments": [{"name": "Product"}],
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/456",
                },
            ],
            "meta": {"total": 2},
        }
        result = adapter.parse_jobs(raw_data, "https://boards.greenhouse.io/v1/boards/acme/jobs", "acme.com")

        assert result.success is True
        assert result.open_positions_count == 2
        assert len(result.jobs) == 2
        assert result.jobs[0].title == "Senior Engineer"
        assert result.jobs[0].department == "Engineering"
        assert result.jobs[0].location == "Remote"
        assert result.ats_platform == ATSPlatform.GREENHOUSE.value
        assert result.strategy_used == ExtractionStrategy.ATS_API

    def test_parse_empty_jobs(self):
        adapter = GreenhouseAdapter()
        raw_data = {"jobs": [], "meta": {"total": 0}}
        result = adapter.parse_jobs(raw_data, "https://boards.greenhouse.io/v1/boards/acme/jobs", "acme.com")

        assert result.open_positions_count == 0
        assert len(result.jobs) == 0
        # With 0 jobs but open_positions_count present, success should be True
        assert result.success is True

    def test_parse_jobs_without_title_skipped(self):
        adapter = GreenhouseAdapter()
        raw_data = {
            "jobs": [
                {"title": "Engineer"},
                {"location": {"name": "NYC"}},  # no title → skip
            ],
        }
        result = adapter.parse_jobs(raw_data, "https://example.com", "acme.com")
        assert len(result.jobs) == 1
        assert result.jobs[0].title == "Engineer"


class TestGreenhouseFetch:
    """Greenhouse fetch_jobs should append content=true and return data."""

    @patch.object(GreenhouseAdapter, "_get_json")
    def test_fetch_appends_content_param(self, mock_get_json):
        mock_get_json.return_value = {"jobs": [], "meta": {"total": 0}}
        adapter = GreenhouseAdapter()
        result = adapter.fetch_jobs("https://boards.greenhouse.io/v1/boards/acme/jobs")
        mock_get_json.assert_called_once()
        call_url = mock_get_json.call_args[0][0]
        assert "content=true" in call_url

    @patch.object(GreenhouseAdapter, "_get_json")
    def test_fetch_returns_none_on_failure(self, mock_get_json):
        mock_get_json.return_value = None
        adapter = GreenhouseAdapter()
        result = adapter.fetch_jobs("https://boards.greenhouse.io/v1/boards/acme/jobs")
        assert result is None


# ---------------------------------------------------------------------------
# Lever adapter
# ---------------------------------------------------------------------------

class TestLeverDetect:
    """Lever detection should match known HTML patterns."""

    def test_detect_lever_embed(self):
        adapter = LeverAdapter()
        assert adapter.detect('<script src="https://jobs.lever.co/embed"></script>') is True

    def test_detect_lever_url(self):
        adapter = LeverAdapter()
        assert adapter.detect("See jobs.lever.co/acme for openings") is True

    def test_no_false_positive(self):
        adapter = LeverAdapter()
        assert adapter.detect("<html><body>No ATS here</body></html>") is False

    def test_platform_attribute(self):
        assert LeverAdapter.platform == ATSPlatform.LEVER


class TestLeverParse:
    """Lever parse_jobs should extract structured data from raw JSON."""

    def test_parse_typical_response(self):
        adapter = LeverAdapter()
        raw_data = [
            {
                "text": "Software Engineer",
                "categories": {"location": "San Francisco", "team": "Engineering"},
                "descriptionPlain": "Build great software",
                "hostedUrl": "https://jobs.lever.co/acme/123",
            },
        ]
        result = adapter.parse_jobs(raw_data, "https://api.lever.co/v0/postings/acme?mode=json", "acme.com")

        assert result.success is True
        assert result.open_positions_count == 1
        assert len(result.jobs) == 1
        assert result.jobs[0].title == "Software Engineer"
        assert result.jobs[0].department == "Engineering"
        assert result.jobs[0].location == "San Francisco"
        assert result.ats_platform == ATSPlatform.LEVER.value

    def test_parse_empty_list(self):
        adapter = LeverAdapter()
        result = adapter.parse_jobs([], "https://api.lever.co/v0/postings/acme?mode=json", "acme.com")
        assert result.open_positions_count == 0
        assert len(result.jobs) == 0


# ---------------------------------------------------------------------------
# Ashby adapter
# ---------------------------------------------------------------------------

class TestAshbyDetect:
    """Ashby detection should match known HTML patterns."""

    def test_detect_ashby_embed(self):
        adapter = AshbyAdapter()
        assert adapter.detect('<iframe src="https://jobs.ashbyhq.com/acme"></iframe>') is True

    def test_no_false_positive(self):
        adapter = AshbyAdapter()
        assert adapter.detect("<html><body>No ATS here</body></html>") is False

    def test_platform_attribute(self):
        assert AshbyAdapter.platform == ATSPlatform.ASHBY


class TestAshbyParse:
    """Ashby parse_jobs should extract structured data from GraphQL response."""

    def test_parse_typical_response(self):
        adapter = AshbyAdapter()
        raw_data = {
            "data": {
                "jobBoard": {
                    "teams": [
                        {"id": "team-1", "name": "Engineering", "parentTeamId": None},
                        {"id": "team-2", "name": "Product", "parentTeamId": None},
                    ],
                    "jobPostings": [
                        {
                            "id": "job-1",
                            "title": "Senior Engineer",
                            "teamId": "team-1",
                            "locationName": "Remote",
                            "employmentType": "Full-time",
                        },
                        {
                            "id": "job-2",
                            "title": "Product Designer",
                            "teamId": "team-2",
                            "locationName": "New York",
                            "employmentType": "Full-time",
                        },
                    ],
                },
            },
        }
        result = adapter.parse_jobs(raw_data, "acme", "acme.com")

        assert result.success is True
        assert result.open_positions_count == 2
        assert len(result.jobs) == 2
        assert result.jobs[0].title == "Senior Engineer"
        assert result.jobs[0].department == "Engineering"
        assert "Engineering" in result.hiring_areas
        assert result.ats_platform == ATSPlatform.ASHBY.value

    def test_parse_empty_job_board(self):
        adapter = AshbyAdapter()
        raw_data = {
            "data": {
                "jobBoard": {
                    "teams": [],
                    "jobPostings": [],
                },
            },
        }
        result = adapter.parse_jobs(raw_data, "acme", "acme.com")
        assert result.open_positions_count == 0
        assert len(result.jobs) == 0

    def test_parse_malformed_data_graceful(self):
        adapter = AshbyAdapter()
        raw_data = {"data": {}}
        result = adapter.parse_jobs(raw_data, "acme", "acme.com")
        assert result.open_positions_count == 0
        assert len(result.jobs) == 0


# ---------------------------------------------------------------------------
# NormalizedJobsResult contract
# ---------------------------------------------------------------------------

class TestNormalizedJobsResultContract:
    """Verify the NormalizedJobsResult dataclass meets its contract."""

    def test_success_with_jobs(self):
        result = NormalizedJobsResult(
            domain="acme.com",
            open_positions_count=5,
            jobs=[NormalizedJob(title="Engineer")],
            hiring_areas=["Engineering"],
        )
        assert result.success is True
        assert result.jobs_count == 1

    def test_success_with_zero_positions_explicit(self):
        """open_positions_count=0 with no error should be success=True."""
        result = NormalizedJobsResult(
            domain="acme.com",
            open_positions_count=0,
        )
        assert result.success is True

    def test_failure_with_error(self):
        result = NormalizedJobsResult(
            domain="acme.com",
            error="Connection refused",
        )
        assert result.success is False

    def test_success_from_hiring_areas_only(self):
        """No open_positions_count but hiring_areas → success=True."""
        result = NormalizedJobsResult(
            domain="acme.com",
            hiring_areas=["Engineering", "Sales"],
        )
        assert result.success is True

    def test_default_values(self):
        result = NormalizedJobsResult()
        assert result.domain == ""
        assert result.strategy_used == ExtractionStrategy.PLAYWRIGHT
        assert result.evidence_quality == "none"
        assert result.confidence == 0.0
        assert result.error is None
        assert result.used_cache is False

    def test_required_output_fields(self):
        result = NormalizedJobsResult(domain="acme.com")
        # Fields that downstream code depends on
        assert hasattr(result, "domain")
        assert hasattr(result, "open_positions_count")
        assert hasattr(result, "jobs")
        assert hasattr(result, "hiring_areas")
        assert hasattr(result, "locations")
        assert hasattr(result, "strategy_used")
        assert hasattr(result, "reason_code")
        assert hasattr(result, "ats_platform")
        assert hasattr(result, "evidence_quality")
        assert hasattr(result, "confidence")
        assert hasattr(result, "error")
        assert hasattr(result, "success")


# ---------------------------------------------------------------------------
# BaseATSAdapter retry logic
# ---------------------------------------------------------------------------

class TestBaseATSAdapterRetry:
    """Verify _request_with_retry retries on transient errors."""

    @patch("app.extraction.adapters.base.requests.request")
    def test_retry_on_503(self, mock_request):
        """Should retry on 503 and succeed on second attempt."""
        mock_response_503 = MagicMock()
        mock_response_503.status_code = 503
        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {"jobs": []}
        mock_response_ok.raise_for_status.return_value = None

        mock_request.side_effect = [mock_response_503, mock_response_ok]
        adapter = GreenhouseAdapter()
        result = adapter._request_with_retry("GET", "https://example.com/api")
        assert result.status_code == 200
        assert mock_request.call_count == 2

    @patch("app.extraction.adapters.base.requests.request")
    def test_no_retry_on_404(self, mock_request):
        """Should NOT retry on 404 (permanent client error)."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("404")
        mock_request.return_value = mock_response

        adapter = GreenhouseAdapter()
        # The retry logic should not retry 404s since they're not in TRANSIENT_STATUS_CODES
        try:
            adapter._request_with_retry("GET", "https://example.com/api")
        except Exception:
            pass
        # Should only be called once (no retry for 404)
        assert mock_request.call_count <= 1

    @patch("app.extraction.adapters.base.requests.request")
    def test_retry_exhausted_returns_none(self, mock_request):
        """Should return None after MAX_RETRIES exhausted."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_request.return_value = mock_response

        adapter = GreenhouseAdapter()
        result = adapter._request_with_retry("GET", "https://example.com/api")
        # Returns None when all retries exhausted with transient errors
        assert result is None
        # Should have been called MAX_RETRIES times
        assert mock_request.call_count == 3

    @patch("app.extraction.adapters.base.requests.request")
    def test_retry_on_connection_error(self, mock_request):
        """Should retry on ConnectionError and succeed on second attempt."""
        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200
        mock_response_ok.raise_for_status.return_value = None

        # Use ConnectionError from requests.exceptions
        from requests.exceptions import ConnectionError as RequestsConnectionError
        mock_request.side_effect = [
            RequestsConnectionError("Connection refused"),
            mock_response_ok,
        ]
        adapter = GreenhouseAdapter()
        result = adapter._request_with_retry("GET", "https://example.com/api")
        assert result.status_code == 200


# ---------------------------------------------------------------------------
# slugify_company
# ---------------------------------------------------------------------------

class TestSlugifyCompany:
    """slugify_company should generate plausible ATS slugs."""

    def test_domain_prefix_slug(self):
        slugs = slugify_company("Acme Corp", "acme.com")
        assert "acme" in slugs

    def test_name_slug(self):
        slugs = slugify_company("Acme Technologies", "acmetech.com")
        # Should include a hyphenated or bare version of the name
        assert any("acme" in s for s in slugs)

    def test_suffix_stripped(self):
        slugs = slugify_company("Acme Inc", "acme.com")
        assert any("acme" in s for s in slugs)

    def test_empty_name_uses_domain(self):
        slugs = slugify_company("", "stripe.com")
        assert "stripe" in slugs

    def test_no_duplicates(self):
        slugs = slugify_company("Test Company", "test.com")
        assert len(slugs) == len(set(slugs))


# ---------------------------------------------------------------------------
# Full extract pipeline (mocked HTTP)
# ---------------------------------------------------------------------------

class TestExtractPipeline:
    """Test the full extract() pipeline: API success should skip Playwright."""

    @patch.object(GreenhouseAdapter, "fetch_jobs")
    @patch.object(GreenhouseAdapter, "resolve_endpoint")
    def test_extract_api_success(self, mock_resolve, mock_fetch):
        """When API succeeds, extract() should return NormalizedJobsResult with ATS_API strategy."""
        mock_resolve.return_value = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
        mock_fetch.return_value = {
            "jobs": [
                {"title": "Engineer", "location": {"name": "Remote"}, "departments": [{"name": "Eng"}]},
            ],
            "meta": {"total": 1},
        }

        adapter = GreenhouseAdapter()
        result = adapter.extract(domain="acme.com", company_name="Acme")

        assert result.strategy_used == ExtractionStrategy.ATS_API
        assert result.ats_platform == ATSPlatform.GREENHOUSE.value
        assert len(result.jobs) == 1

    @patch.object(GreenhouseAdapter, "resolve_endpoint")
    def test_extract_api_failure_returns_no_result(self, mock_resolve):
        """When resolve_endpoint returns None, extract() should return a no-result."""
        mock_resolve.return_value = None

        adapter = GreenhouseAdapter()
        result = adapter.extract(domain="unknown.com")

        # Should return a NormalizedJobsResult indicating no ATS found
        assert isinstance(result, NormalizedJobsResult)
        # No jobs from API, strategy may vary (could be PLAYWRIGHT or ATS_API with empty data)
        assert result.domain == "unknown.com"