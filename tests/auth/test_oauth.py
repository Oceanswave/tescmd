"""Tests for tescmd.auth.oauth — PKCE helpers and URL building."""

from __future__ import annotations

from tescmd.auth.oauth import (
    _generate_code_challenge,
    _generate_code_verifier,
    build_auth_url,
)


class TestCodeVerifier:
    def test_code_verifier_length(self) -> None:
        verifier = _generate_code_verifier()
        assert len(verifier) == 128

    def test_code_verifier_unique(self) -> None:
        a = _generate_code_verifier()
        b = _generate_code_verifier()
        assert a != b


class TestCodeChallenge:
    def test_code_challenge_is_sha256(self) -> None:
        verifier = _generate_code_verifier()
        challenge = _generate_code_challenge(verifier)
        assert len(challenge) == 43


class TestBuildAuthUrl:
    def test_build_auth_url(self) -> None:
        url = build_auth_url(
            client_id="cid",
            redirect_uri="https://localhost/callback",
            scopes=["openid", "offline_access"],
            code_challenge="challenge123",
            state="state456",
        )
        assert "client_id=cid" in url
        assert "state=state456" in url
        assert "code_challenge=challenge123" in url
        assert "code_challenge_method=S256" in url
        assert "response_type=code" in url
        assert "auth.tesla.com" in url
