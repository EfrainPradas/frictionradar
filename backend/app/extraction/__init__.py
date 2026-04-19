"""Extraction routing layer.

Decides HOW to extract careers data from a company (ats_api, http_static,
or playwright) and provides a unified output contract.

Phase 1: infrastructure only — router, schemas, instrumentation, persistence.
Phase 2+: actual extractors wired through the router.
"""
