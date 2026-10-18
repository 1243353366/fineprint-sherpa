import os
import pytest
from backend.app.external_terms import MockExternalTermsClient, ExternalTermsClient, ExternalTermsError


def test_mock_not_enabled_by_default(monkeypatch):
    # ensure that without EXTERNAL_TERMS_ALLOW_MOCK, factory fails when no TERMS_API_BASE
    monkeypatch.delenv("TERMS_API_BASE", raising=False)
    monkeypatch.delenv("EXTERNAL_TERMS_ALLOW_MOCK", raising=False)
    from backend.app.external_terms import get_terms_client
    with pytest.raises(ExternalTermsError):
        get_terms_client()


def test_mock_enabled(monkeypatch):
    monkeypatch.delenv("TERMS_API_BASE", raising=False)
    monkeypatch.setenv("EXTERNAL_TERMS_ALLOW_MOCK", "true")
    c = get_terms_client()
    assert isinstance(c, MockExternalTermsClient)

