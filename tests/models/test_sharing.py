from __future__ import annotations

from tescmd.models.sharing import ShareDriverInfo, ShareInvite


class TestShareDriverInfo:
    def test_all_fields(self) -> None:
        info = ShareDriverInfo(
            share_user_id=1,
            email="a@b.com",
            status="active",
            public_key="pk123",
        )
        assert info.share_user_id == 1
        assert info.email == "a@b.com"
        assert info.status == "active"
        assert info.public_key == "pk123"

    def test_extra_fields_captured(self) -> None:
        info = ShareDriverInfo(
            share_user_id=1,
            email="a@b.com",
            status="active",
            public_key="pk123",
            some_future_field="hello",  # type: ignore[call-arg]
        )
        assert info.share_user_id == 1
        assert info.model_extra is not None
        assert info.model_extra["some_future_field"] == "hello"

    def test_defaults_none(self) -> None:
        info = ShareDriverInfo()
        assert info.share_user_id is None
        assert info.email is None
        assert info.status is None
        assert info.public_key is None


class TestShareInvite:
    def test_all_fields(self) -> None:
        invite = ShareInvite(
            id="inv1",
            code="abc",
            created_at="2024-01-01",
            expires_at="2024-02-01",
            status="pending",
        )
        assert invite.id == "inv1"
        assert invite.code == "abc"
        assert invite.created_at == "2024-01-01"
        assert invite.expires_at == "2024-02-01"
        assert invite.status == "pending"

    def test_extra_fields_captured(self) -> None:
        invite = ShareInvite(
            id="inv1",
            code="abc",
            unknown_api_field=42,  # type: ignore[call-arg]
        )
        assert invite.id == "inv1"
        assert invite.model_extra is not None
        assert invite.model_extra["unknown_api_field"] == 42

    def test_defaults_none(self) -> None:
        invite = ShareInvite()
        assert invite.id is None
        assert invite.code is None
        assert invite.created_at is None
        assert invite.expires_at is None
        assert invite.status is None
