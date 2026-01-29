from __future__ import annotations

from tescmd.models.auth import (
    DEFAULT_REDIRECT_URI,
    DEFAULT_SCOPES,
    AuthConfig,
    TokenData,
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


class TestAuthConfig:
    def test_construction(self) -> None:
        cfg = AuthConfig(client_id="cid", client_secret="csec")
        assert cfg.client_id == "cid"
        assert cfg.client_secret == "csec"
        assert cfg.redirect_uri == DEFAULT_REDIRECT_URI
        assert cfg.scopes == DEFAULT_SCOPES
