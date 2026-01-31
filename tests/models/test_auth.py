from __future__ import annotations

import base64
import json

from tescmd.models.auth import (
    DEFAULT_REDIRECT_URI,
    DEFAULT_SCOPES,
    AuthConfig,
    TokenData,
    decode_jwt_scopes,
)


class TestTokenData:
    def test_from_response(self) -> None:
        payload = {
            "access_token": "abc123",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "ref456",
            "id_token": "id789",
        }
        token = TokenData.model_validate(payload)
        assert token.access_token == "abc123"
        assert token.token_type == "Bearer"
        assert token.expires_in == 3600
        assert token.refresh_token == "ref456"
        assert token.id_token == "id789"

    def test_optional_fields(self) -> None:
        token = TokenData(
            access_token="abc",
            token_type="Bearer",
            expires_in=300,
        )
        assert token.refresh_token is None
        assert token.id_token is None

    def test_scope_field_parsed(self) -> None:
        payload = {
            "access_token": "abc",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "openid user_data vehicle_device_data",
        }
        token = TokenData.model_validate(payload)
        assert token.scope == "openid user_data vehicle_device_data"


def _make_jwt(payload: dict[str, object]) -> str:
    """Build a fake JWT (header.payload.signature) for testing."""
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=").decode()
    return f"{header}.{body}.{sig}"


class TestDecodeJwtScopes:
    def test_extracts_scp_claim(self) -> None:
        token = _make_jwt({"scp": ["openid", "user_data", "vehicle_device_data"]})
        assert decode_jwt_scopes(token) == ["openid", "user_data", "vehicle_device_data"]

    def test_returns_none_for_non_jwt(self) -> None:
        assert decode_jwt_scopes("not-a-jwt") is None

    def test_returns_none_when_no_scp_claim(self) -> None:
        token = _make_jwt({"sub": "user123", "aud": "fleet-api"})
        assert decode_jwt_scopes(token) is None

    def test_returns_none_for_invalid_payload(self) -> None:
        # Three segments but middle isn't valid base64/JSON
        assert decode_jwt_scopes("aaa.!!!invalid.ccc") is None

    def test_missing_scopes_detected(self) -> None:
        """Simulate Tesla silently dropping user_data."""
        token = _make_jwt({"scp": ["openid", "vehicle_device_data"]})
        granted = decode_jwt_scopes(token)
        assert granted is not None
        assert "user_data" not in granted


class TestAuthConfig:
    def test_construction(self) -> None:
        cfg = AuthConfig(client_id="cid", client_secret="csec")
        assert cfg.client_id == "cid"
        assert cfg.client_secret == "csec"
        assert cfg.redirect_uri == DEFAULT_REDIRECT_URI
        assert cfg.scopes == DEFAULT_SCOPES
