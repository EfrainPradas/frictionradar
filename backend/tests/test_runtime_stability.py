"""
Tests for runtime stability fixes.

Verifies that:
  1. Background tasks create their own DB session (closed-session safety).
  2. NormalizedJobsResult.success treats open_positions_count=0 as success.
  3. ATS adapters retry on transient HTTP errors with exponential backoff.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from uuid import uuid4

from app.extraction.schemas import NormalizedJobsResult, NormalizedJob
from app.extraction.constants import ExtractionStrategy, ReasonCode


# ─── Fix 1: Background task DB session ──────────────────────────────────

class TestBackgroundTaskSessionSafety:
    """Verify run_collection_for_company creates its own DB session."""

    def test_creates_own_session(self):
        """run_collection_for_company should create a SessionLocal() session."""
        with patch("app.db.session.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            # Make the DB queries return None so we get the early exit
            mock_db.query.return_value.filter.return_value.first.return_value = None

            from app.services.collection_orchestrator import run_collection_for_company

            company_id = uuid4()
            run_id = uuid4()
            result = run_collection_for_company(company_id, run_id)

            mock_session_local.assert_called_once()
            mock_db.close.assert_called_once()

    def test_session_closed_even_on_error(self):
        """DB session should be closed even if the inner function raises."""
        with patch("app.db.session.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db
            # Make the query itself raise
            mock_db.query.side_effect = RuntimeError("db error")

            from app.services.collection_orchestrator import run_collection_for_company

            company_id = uuid4()
            run_id = uuid4()
            # Should not raise — the inner function catches and logs
            # but the finally block still closes the session
            try:
                run_collection_for_company(company_id, run_id)
            except RuntimeError:
                pass

            mock_db.close.assert_called_once()

    def test_no_db_parameter_in_signature(self):
        """run_collection_for_company should not accept a db parameter."""
        from app.services.collection_orchestrator import run_collection_for_company
        import inspect
        sig = inspect.signature(run_collection_for_company)
        param_names = list(sig.parameters.keys())
        assert "db" not in param_names, f"db should not be a parameter, got: {param_names}"


# ─── Fix 4: NormalizedJobsResult.success ────────────────────────────────

class TestNormalizedJobsResultSuccess:
    """Verify success property handles open_positions_count=0 correctly."""

    def test_zero_positions_is_success(self):
        """open_positions_count=0 with no error means collection succeeded."""
        result = NormalizedJobsResult(
            domain="example.com",
            open_positions_count=0,
            strategy_used=ExtractionStrategy.ATS_API,
            reason_code=ReasonCode.KNOWN_ATS_JSON_AVAILABLE,
        )
        assert result.success is True

    def test_zero_positions_with_jobs_is_success(self):
        """open_positions_count=0 with jobs also succeeds."""
        result = NormalizedJobsResult(
            domain="example.com",
            open_positions_count=0,
            jobs=[NormalizedJob(title="Engineer")],
            strategy_used=ExtractionStrategy.ATS_API,
            reason_code=ReasonCode.KNOWN_ATS_JSON_AVAILABLE,
        )
        assert result.success is True

    def test_none_positions_with_jobs_is_success(self):
        """open_positions_count=None but with jobs is still success."""
        result = NormalizedJobsResult(
            domain="example.com",
            open_positions_count=None,
            jobs=[NormalizedJob(title="Engineer")],
            strategy_used=ExtractionStrategy.ATS_API,
            reason_code=ReasonCode.KNOWN_ATS_JSON_AVAILABLE,
        )
        assert result.success is True

    def test_none_positions_with_areas_is_success(self):
        """open_positions_count=None but with hiring areas is still success."""
        result = NormalizedJobsResult(
            domain="example.com",
            open_positions_count=None,
            hiring_areas=["Engineering"],
            strategy_used=ExtractionStrategy.ATS_API,
            reason_code=ReasonCode.KNOWN_ATS_JSON_AVAILABLE,
        )
        assert result.success is True

    def test_none_positions_no_data_is_failure(self):
        """open_positions_count=None with no jobs or areas is failure."""
        result = NormalizedJobsResult(
            domain="example.com",
            open_positions_count=None,
            strategy_used=ExtractionStrategy.ATS_API,
            reason_code=ReasonCode.KNOWN_ATS_JSON_AVAILABLE,
        )
        assert result.success is False

    def test_error_overrides_zero_positions(self):
        """Error field always means failure, even with valid data."""
        result = NormalizedJobsResult(
            domain="example.com",
            open_positions_count=5,
            jobs=[NormalizedJob(title="Engineer")],
            strategy_used=ExtractionStrategy.ATS_API,
            reason_code=ReasonCode.KNOWN_ATS_JSON_AVAILABLE,
            error="something went wrong",
        )
        assert result.success is False

    def test_positive_positions_is_success(self):
        """open_positions_count=5 with no error is success."""
        result = NormalizedJobsResult(
            domain="example.com",
            open_positions_count=5,
            strategy_used=ExtractionStrategy.ATS_API,
            reason_code=ReasonCode.KNOWN_ATS_JSON_AVAILABLE,
        )
        assert result.success is True


# ─── Fix 5: ATS adapter retry ──────────────────────────────────────────

class TestATSAdapterRetry:
    """Verify retry with exponential backoff for transient errors."""

    def _make_adapter(self):
        """Create a concrete adapter for testing."""
        from app.extraction.adapters.base import BaseATSAdapter
        from app.extraction.constants import ATSPlatform

        class TestAdapter(BaseATSAdapter):
            platform = ATSPlatform.GREENHOUSE

            def detect(self, html: str) -> bool:
                return False

            def resolve_endpoint(self, domain, company_name=None):
                return None

            def fetch_jobs(self, api_url):
                return None

            def parse_jobs(self, raw_data, api_url, domain):
                return NormalizedJobsResult(domain=domain)

        return TestAdapter()

    @patch("app.extraction.adapters.base.requests.request")
    def test_retry_on_503(self, mock_request):
        """Should retry on 503 and succeed on second attempt."""
        adapter = self._make_adapter()

        # First call returns 503, second returns 200
        response_503 = MagicMock()
        response_503.status_code = 503
        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.json.return_value = {"data": "ok"}

        mock_request.side_effect = [response_503, response_200]

        result = adapter._get_json("https://example.com/api/jobs")
        assert result == {"data": "ok"}
        assert mock_request.call_count == 2

    @patch("app.extraction.adapters.base.requests.request")
    def test_retry_exhausted_on_persistent_503(self, mock_request):
        """Should return None after exhausting retries on persistent 503."""
        adapter = self._make_adapter()

        response_503 = MagicMock()
        response_503.status_code = 503
        mock_request.return_value = response_503

        result = adapter._get_json("https://example.com/api/jobs")
        assert result is None
        assert mock_request.call_count == 3  # MAX_RETRIES

    @patch("app.extraction.adapters.base.time.sleep")
    @patch("app.extraction.adapters.base.requests.request")
    def test_backoff_timing(self, mock_request, mock_sleep):
        """Should sleep with exponential backoff between retries."""
        adapter = self._make_adapter()

        response_503 = MagicMock()
        response_503.status_code = 503
        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.json.return_value = {}

        mock_request.side_effect = [response_503, response_503, response_200]

        adapter._get_json("https://example.com/api/jobs")
        # RETRY_BACKOFF_BASE=1.0, so delays: 1.0, 2.0
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)  # 1st retry: 1.0 * 2^0 = 1.0
        mock_sleep.assert_any_call(2.0)  # 2nd retry: 1.0 * 2^1 = 2.0

    @patch("app.extraction.adapters.base.requests.request")
    def test_no_retry_on_404(self, mock_request):
        """Should NOT retry on 404 (non-transient error)."""
        adapter = self._make_adapter()

        response_404 = MagicMock()
        response_404.status_code = 404
        mock_request.return_value = response_404

        result = adapter._get_json("https://example.com/api/jobs")
        assert result is None
        assert mock_request.call_count == 1  # No retry

    @patch("app.extraction.adapters.base.requests.request")
    def test_retry_on_timeout(self, mock_request):
        """Should retry on Timeout and succeed on second attempt."""
        adapter = self._make_adapter()

        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.json.return_value = {"data": "ok"}

        mock_request.side_effect = [
            requests.exceptions.Timeout("connection timed out"),
            response_200,
        ]

        result = adapter._get_json("https://example.com/api/jobs")
        assert result == {"data": "ok"}
        assert mock_request.call_count == 2

    @patch("app.extraction.adapters.base.requests.request")
    def test_retry_on_connection_error(self, mock_request):
        """Should retry on ConnectionError and succeed on second attempt."""
        adapter = self._make_adapter()

        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.json.return_value = {"data": "ok"}

        mock_request.side_effect = [
            requests.exceptions.ConnectionError("refused"),
            response_200,
        ]

        result = adapter._get_json("https://example.com/api/jobs")
        assert result == {"data": "ok"}
        assert mock_request.call_count == 2

    @patch("app.extraction.adapters.base.requests.request")
    def test_no_retry_on_generic_request_exception(self, mock_request):
        """Should NOT retry on generic RequestException (non-transient)."""
        adapter = self._make_adapter()

        mock_request.side_effect = requests.exceptions.RequestException("generic error")

        result = adapter._get_json("https://example.com/api/jobs")
        assert result is None
        assert mock_request.call_count == 1  # No retry

    @patch("app.extraction.adapters.base.requests.request")
    def test_retry_on_429(self, mock_request):
        """Should retry on 429 (rate limit)."""
        adapter = self._make_adapter()

        response_429 = MagicMock()
        response_429.status_code = 429
        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.json.return_value = {"data": "ok"}

        mock_request.side_effect = [response_429, response_200]

        result = adapter._get_json("https://example.com/api/jobs")
        assert result == {"data": "ok"}
        assert mock_request.call_count == 2

    @patch("app.extraction.adapters.base.requests.request")
    def test_head_ok_retries(self, mock_request):
        """_head_ok should also retry on transient errors."""
        adapter = self._make_adapter()

        response_502 = MagicMock()
        response_502.status_code = 502
        response_200 = MagicMock()
        response_200.status_code = 200

        mock_request.side_effect = [response_502, response_200]

        result = adapter._head_ok("https://example.com/api/jobs")
        assert result is True
        assert mock_request.call_count == 2

    @patch("app.extraction.adapters.base.requests.request")
    def test_post_json_retries(self, mock_request):
        """_post_json should retry on transient errors."""
        adapter = self._make_adapter()

        response_503 = MagicMock()
        response_503.status_code = 503
        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.json.return_value = {"data": {"jobBoard": {"jobPostings": []}}}

        mock_request.side_effect = [response_503, response_200]

        result = adapter._post_json(
            "https://example.com/graphql",
            {"query": "test"},
        )
        assert result is not None
        assert mock_request.call_count == 2


# ─── Fix 2-3: asyncio.set_event_loop removal ───────────────────────────

class TestEventLoopSafety:
    """Verify that dispatcher and scoring don't call asyncio.set_event_loop."""

    def test_dispatcher_no_set_event_loop(self):
        """dispatcher.py should NOT call asyncio.set_event_loop."""
        import inspect
        from app.extraction import dispatcher
        source = inspect.getsource(dispatcher)
        assert "set_event_loop" not in source, (
            "dispatcher.py should not call asyncio.set_event_loop()"
        )

    def test_scoring_no_set_event_loop(self):
        """scoring.py should NOT call asyncio.set_event_loop."""
        import inspect
        from app.api.routers import scoring
        source = inspect.getsource(scoring)
        assert "set_event_loop" not in source, (
            "scoring.py should not call asyncio.set_event_loop()"
        )

    def test_scoring_endpoint_is_async(self):
        """scoring.py trigger_scoring should be an async function."""
        from app.api.routers.scoring import trigger_scoring
        import inspect
        assert inspect.iscoroutinefunction(trigger_scoring), (
            "trigger_scoring should be an async function"
        )


# Need to import requests for the test assertions
import requests.exceptions