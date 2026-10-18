import os
import pytest
from backend.app.external_terms import ExternalTermsError, get_terms_client


def test_service_unavailable_by_default(monkeypatch):
    # Ensure that when TERMS_API_BASE is not set and mock not allowed, get_terms_client raises
    monkeypatch.delenv("TERMS_API_BASE", raising=False)
    monkeypatch.delenv("EXTERNAL_TERMS_ALLOW_MOCK", raising=False)
    with pytest.raises(ExternalTermsError):
        get_terms_client()


def test_mock_requires_explicit_env(monkeypatch):
    monkeypatch.delenv("TERMS_API_BASE", raising=False)
    monkeypatch.setenv("EXTERNAL_TERMS_ALLOW_MOCK", "false")
    with pytest.raises(ExternalTermsError):
        get_terms_client()
