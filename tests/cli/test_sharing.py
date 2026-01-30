"""Tests for the sharing CLI commands."""

from __future__ import annotations

from click.testing import CliRunner

from tescmd.cli.main import cli


class TestSharingHelp:
    def test_sharing_help(self) -> None:
        result = CliRunner().invoke(cli, ["sharing", "--help"])
        assert result.exit_code == 0
        assert "add-driver" in result.output
        assert "remove-driver" in result.output
        assert "create-invite" in result.output
        assert "redeem-invite" in result.output
        assert "revoke-invite" in result.output
        assert "list-invites" in result.output

    def test_sharing_in_root_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert "sharing" in result.output


class TestSharingAddDriver:
    def test_add_driver_help(self) -> None:
        result = CliRunner().invoke(cli, ["sharing", "add-driver", "--help"])
        assert result.exit_code == 0
        assert "EMAIL" in result.output
        assert "VIN" in result.output

    def test_add_driver_requires_email(self) -> None:
        """add-driver should fail when no email is provided."""
        result = CliRunner().invoke(cli, ["sharing", "add-driver"])
        assert result.exit_code != 0


class TestSharingRemoveDriver:
    def test_remove_driver_help(self) -> None:
        result = CliRunner().invoke(cli, ["sharing", "remove-driver", "--help"])
        assert result.exit_code == 0
        assert "SHARE_USER_ID" in result.output
        assert "VIN" in result.output

    def test_remove_driver_requires_share_user_id(self) -> None:
        """remove-driver should fail when no share_user_id is provided."""
        result = CliRunner().invoke(cli, ["sharing", "remove-driver"])
        assert result.exit_code != 0


class TestSharingCreateInvite:
    def test_create_invite_help(self) -> None:
        result = CliRunner().invoke(cli, ["sharing", "create-invite", "--help"])
        assert result.exit_code == 0
        assert "invite" in result.output.lower()

    def test_create_invite_accepts_vin(self) -> None:
        result = CliRunner().invoke(cli, ["sharing", "create-invite", "--help"])
        assert result.exit_code == 0
        assert "VIN" in result.output


class TestSharingRedeemInvite:
    def test_redeem_invite_help(self) -> None:
        result = CliRunner().invoke(cli, ["sharing", "redeem-invite", "--help"])
        assert result.exit_code == 0
        assert "CODE" in result.output
        assert "VIN" in result.output

    def test_redeem_invite_requires_code(self) -> None:
        """redeem-invite should fail when no code is provided."""
        result = CliRunner().invoke(cli, ["sharing", "redeem-invite"])
        assert result.exit_code != 0


class TestSharingRevokeInvite:
    def test_revoke_invite_help(self) -> None:
        result = CliRunner().invoke(cli, ["sharing", "revoke-invite", "--help"])
        assert result.exit_code == 0
        assert "INVITE_ID" in result.output
        assert "VIN" in result.output

    def test_revoke_invite_requires_invite_id(self) -> None:
        """revoke-invite should fail when no invite_id is provided."""
        result = CliRunner().invoke(cli, ["sharing", "revoke-invite"])
        assert result.exit_code != 0


class TestSharingListInvites:
    def test_list_invites_help(self) -> None:
        result = CliRunner().invoke(cli, ["sharing", "list-invites", "--help"])
        assert result.exit_code == 0
        assert "invite" in result.output.lower()

    def test_list_invites_accepts_vin(self) -> None:
        result = CliRunner().invoke(cli, ["sharing", "list-invites", "--help"])
        assert result.exit_code == 0
        assert "VIN" in result.output
