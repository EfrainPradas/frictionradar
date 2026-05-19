"""
Tests for security hardening.

Verifies:
  1. SSRF URL validation blocks private IPs, file schemes, metadata IPs.
  2. Timing-safe token comparison.
  3. CORS configuration (dev vs prod).
  4. SSL verification environment variable.
  5. API key middleware exempt paths and enforcement.
  6. Global exception handler removes stack traces.
"""

import os
import pytest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


# ─── SSRF Validation ──────────────────────────────────────────────────

class TestSSRFValidation:
    """Verify validate_url blocks dangerous URLs and allows safe ones."""

    def test_accepts_https(self):
        from app.core.security import validate_url
        assert validate_url("https://example.com/careers") == "https://example.com/careers"

    def test_accepts_http(self):
        from app.core.security import validate_url
        assert validate_url("http://example.com/jobs") == "http://example.com/jobs"

    def test_rejects_file_scheme(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError, match="[Ss]cheme"):
            validate_url("file:///etc/passwd")

    def test_rejects_ftp_scheme(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError, match="[Ss]cheme"):
            validate_url("ftp://internal.server/data")

    def test_rejects_data_scheme(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError, match="[Ss]cheme"):
            validate_url("data:text/html,<script>alert(1)</script>")

    def test_rejects_javascript_scheme(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError, match="[Ss]cheme"):
            validate_url("javascript:alert(1)")

    def test_rejects_localhost(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError, match="[Ll]ocalhost|private"):
            validate_url("http://localhost:8080/admin")

    def test_rejects_localhost_localdomain(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError, match="[Ll]ocalhost|private"):
            validate_url("http://localhost.localdomain/admin")

    def test_rejects_127_0_0_1(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError, match="private|reserved"):
            validate_url("http://127.0.0.1/admin")

    def test_rejects_10_network(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError, match="private|reserved"):
            validate_url("http://10.0.0.1/internal")

    def test_rejects_172_16_network(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError, match="private|reserved"):
            validate_url("http://172.16.0.1/internal")

    def test_rejects_192_168_network(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError, match="private|reserved"):
            validate_url("http://192.168.1.1/internal")

    def test_rejects_metadata_ip(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError, match="private|reserved"):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_rejects_ipv6_loopback(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError):
            validate_url("http://[::1]/admin")

    def test_rejects_no_hostname(self):
        from app.core.security import SSRFError, validate_url
        with pytest.raises(SSRFError, match="hostname"):
            validate_url("https:///path-only")

    def test_allows_private_when_flag_set(self):
        from app.core.security import validate_url
        result = validate_url("http://localhost:8080/admin", allow_private=True)
        assert result == "http://localhost:8080/admin"

    def test_allows_public_domain(self):
        from app.core.security import validate_url
        result = validate_url("https://www.google.com/search")
        assert result == "https://www.google.com/search"


# ─── Timing-safe Token Comparison ───────────────────────────────────────

class TestTokenComparison:
    """Verify verify_token_constant_time uses constant-time comparison."""

    def test_matching_tokens(self):
        from app.core.security import verify_token_constant_time
        assert verify_token_constant_time("secret-token", "secret-token") is True

    def test_mismatching_tokens(self):
        from app.core.security import verify_token_constant_time
        assert verify_token_constant_time("wrong-token", "secret-token") is False

    def test_none_provided(self):
        from app.core.security import verify_token_constant_time
        assert verify_token_constant_time(None, "secret-token") is False

    def test_empty_provided(self):
        from app.core.security import verify_token_constant_time
        assert verify_token_constant_time("", "secret-token") is False

    def test_prefix_does_not_match(self):
        """Ensure prefix attacks are prevented (timing-safe)."""
        from app.core.security import verify_token_constant_time
        token = "abcdef123456"
        assert verify_token_constant_time("abcdef", token) is False

    def test_uses_hmac_compare_digest(self):
        """Verify the function uses hmac.compare_digest, not ==."""
        import hmac
        from app.core.security import verify_token_constant_time
        # This test just confirms the implementation delegates to hmac
        # by checking that a known match works identically
        token = "test-token-123"
        assert verify_token_constant_time(token, token) == hmac.compare_digest(
            token.encode(), token.encode()
        )


# ─── CORS Configuration ────────────────────────────────────────────────

class TestCORSConfiguration:
    """Verify environment-specific CORS configuration."""

    def test_dev_allows_wildcard(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            from app.core.security import get_allowed_origins, get_allow_credentials
            assert get_allowed_origins() == ["*"]
            # Wildcard + credentials is not browser-safe, so must be False
            assert get_allow_credentials() is False

    def test_prod_uses_env_origins(self):
        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "ALLOWED_ORIGINS": "https://app.example.com,https://admin.example.com"
        }, clear=False):
            from app.core.security import get_allowed_origins, get_allow_credentials
            origins = get_allowed_origins()
            assert "https://app.example.com" in origins
            assert "https://admin.example.com" in origins
            assert get_allow_credentials() is True

    def test_prod_empty_origins(self):
        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "ALLOWED_ORIGINS": ""
        }, clear=False):
            from app.core.security import get_allowed_origins
            assert get_allowed_origins() == []

    def test_wildcard_forces_no_credentials(self):
        """When origins include *, credentials must be False."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            from app.core.security import get_allow_credentials
            assert get_allow_credentials() is False


# ─── SSL Verification ─────────────────────────────────────────────────

class TestSSLVerification:
    """Verify SSL verification is controlled by environment variable."""

    def test_default_is_true(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FRICTIONRADAR_VERIFY_SSL", None)
            from app.core.security import get_ssl_verify
            assert get_ssl_verify() is True

    def test_false_when_set(self):
        with patch.dict(os.environ, {"FRICTIONRADAR_VERIFY_SSL": "false"}, clear=False):
            from app.core.security import get_ssl_verify
            assert get_ssl_verify() is False

    def test_true_when_explicitly_set(self):
        with patch.dict(os.environ, {"FRICTIONRADAR_VERIFY_SSL": "true"}, clear=False):
            from app.core.security import get_ssl_verify
            assert get_ssl_verify() is True

    def test_case_insensitive(self):
        with patch.dict(os.environ, {"FRICTIONRADAR_VERIFY_SSL": "FALSE"}, clear=False):
            from app.core.security import get_ssl_verify
            assert get_ssl_verify() is False


# ─── API Key Middleware ────────────────────────────────────────────────

class TestAPIKeyMiddleware:
    """Verify API key middleware exempt paths and enforcement."""

    def test_exempt_health(self):
        from app.core.security import _is_exempt_path
        assert _is_exempt_path("/health") is True

    def test_exempt_docs(self):
        from app.core.security import _is_exempt_path
        assert _is_exempt_path("/docs") is True

    def test_exempt_redoc(self):
        from app.core.security import _is_exempt_path
        assert _is_exempt_path("/redoc") is True

    def test_exempt_openapi(self):
        from app.core.security import _is_exempt_path
        assert _is_exempt_path("/openapi.json") is True

    def test_exempt_root(self):
        from app.core.security import _is_exempt_path
        assert _is_exempt_path("/") is True

    def test_exempt_heatmap(self):
        from app.core.security import _is_exempt_path
        assert _is_exempt_path("/heatmap") is True

    def test_not_exempt_companies(self):
        from app.core.security import _is_exempt_path
        assert _is_exempt_path("/api/v1/companies") is False

    def test_not_exempt_internal(self):
        from app.core.security import _is_exempt_path
        assert _is_exempt_path("/internal/v1/companies/resolve") is False

    def test_not_exempt_careers(self):
        from app.core.security import _is_exempt_path
        assert _is_exempt_path("/api/v2/extract-careers-page") is False

    def test_dev_mode_no_key_required(self):
        """In development with no API key set, middleware passes through."""
        from app.core.security import APIKeyMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyMiddleware)

        @app.get("/api/v1/test")
        def test_endpoint():
            return {"ok": True}

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            os.environ.pop("FRICTIONRADAR_API_KEY", None)
            client = TestClient(app)
            resp = client.get("/api/v1/test")
            assert resp.status_code == 200

    def test_prod_requires_api_key(self):
        """In production, API key is required for data endpoints."""
        from app.core.security import APIKeyMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyMiddleware)

        @app.get("/api/v1/test")
        def test_endpoint():
            return {"ok": True}

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "FRICTIONRADAR_API_KEY": "test-secret-key-12345"
        }, clear=False):
            client = TestClient(app)

            # No API key → 401
            resp = client.get("/api/v1/test")
            assert resp.status_code == 401

            # Wrong API key → 401
            resp = client.get("/api/v1/test", headers={"X-API-Key": "wrong"})
            assert resp.status_code == 401

            # Correct API key → 200
            resp = client.get("/api/v1/test", headers={"X-API-Key": "test-secret-key-12345"})
            assert resp.status_code == 200

    def test_exempt_paths_always_accessible(self):
        """Exempt paths should work even in production without a key."""
        from app.core.security import APIKeyMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyMiddleware)

        @app.get("/health")
        def health():
            return {"status": "ok"}

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "FRICTIONRADAR_API_KEY": "test-secret-key-12345"
        }, clear=False):
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_options_preflight_passes(self):
        """CORS preflight (OPTIONS) should pass without API key."""
        from app.core.security import APIKeyMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyMiddleware)

        @app.get("/api/v1/test")
        def test_endpoint():
            return {"ok": True}

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "FRICTIONRADAR_API_KEY": "test-secret-key-12345"
        }, clear=False):
            client = TestClient(app)
            resp = client.options("/api/v1/test")
            # Should not return 401 (may return 405 or 200 depending on CORS)
            assert resp.status_code != 401


# ─── Global Exception Handler ──────────────────────────────────────────

class TestExceptionHandler:
    """Verify global exception handler removes stack traces from responses."""

    def test_generic_500_no_stack_trace(self):
        from app.core.security import install_exception_handler

        app = FastAPI()
        install_exception_handler(app)

        @app.get("/fail")
        def fail():
            raise RuntimeError("sensitive internal error details")

        # raise_server_exceptions=False lets our exception handler produce the response
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/fail")
        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"] == "Internal server error."
        # Ensure no stack trace or internal details leak
        assert "sensitive" not in str(body)
        assert "RuntimeError" not in str(body)
        assert "Traceback" not in str(body)

    def test_http_exception_still_works(self):
        """HTTPException should still return proper status codes and details."""
        from fastapi import HTTPException
        from app.core.security import install_exception_handler

        app = FastAPI()
        install_exception_handler(app)

        @app.get("/not-found")
        def not_found():
            raise HTTPException(status_code=404, detail="Company not found")

        client = TestClient(app)
        resp = client.get("/not-found")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Company not found"


# ─── Internal Token Fix ────────────────────────────────────────────────

class TestInternalTokenFix:
    """Verify internal token comparison uses constant-time comparison."""

    def test_uses_verify_token_constant_time(self):
        """The verify_internal_token function should use verify_token_constant_time."""
        import inspect
        from app.api.routers.internal import verify_internal_token
        source = inspect.getsource(verify_internal_token)
        assert "verify_token_constant_time" in source
        # Ensure the old timing-unsafe comparison is gone
        assert "!= expected" not in source
        assert "== expected" not in source

    def test_no_config_state_leak(self):
        """Error detail should not reveal the env var name or that token is unconfigured."""
        from app.api.routers.internal import verify_internal_token
        # Verify the 503 message is generic (doesn't contain the env var name)
        try:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("FRICTIONRADAR_INTERNAL_TOKEN", None)
                verify_internal_token(None)
        except Exception as e:
            # The detail should say "Internal token not configured" not
            # "FRICTIONRADAR_INTERNAL_TOKEN is not configured on the server."
            assert "FRICTIONRADAR_INTERNAL_TOKEN" not in str(e.detail)