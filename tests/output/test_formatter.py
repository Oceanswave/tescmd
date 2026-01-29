from __future__ import annotations

import io
import json

from tescmd.output.formatter import OutputFormatter


class TestFormatDetection:
    """Verify the auto-detection and force_format logic."""

    def test_forced_json(self) -> None:
        fmt = OutputFormatter(force_format="json")
        assert fmt.format == "json"

    def test_forced_rich(self) -> None:
        fmt = OutputFormatter(force_format="rich")
        assert fmt.format == "rich"

    def test_forced_quiet(self) -> None:
        fmt = OutputFormatter(force_format="quiet")
        assert fmt.format == "quiet"

    def test_non_tty_defaults_to_json(self) -> None:
        """A non-TTY stream (like StringIO) should auto-select JSON."""
        stream = io.StringIO()
        fmt = OutputFormatter(stream=stream)
        assert fmt.format == "json"

    def test_rich_property_returns_rich_output(self) -> None:
        from tescmd.output.rich_output import RichOutput

        fmt = OutputFormatter(force_format="rich")
        assert isinstance(fmt.rich, RichOutput)


class TestOutput:
    """Verify that :meth:`OutputFormatter.output` routes correctly."""

    def test_json_output(self, capsys: object) -> None:
        fmt = OutputFormatter(force_format="json")
        fmt.output({"key": "value"}, command="test.cmd")
        # capsys is a pytest fixture — use it via the real type
        import _pytest.capture

        assert isinstance(capsys, _pytest.capture.CaptureFixture)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["ok"] is True
        assert parsed["command"] == "test.cmd"

    def test_json_error_output(self, capsys: object) -> None:
        fmt = OutputFormatter(force_format="json")
        fmt.output_error(code="ERR", message="fail", command="test.cmd")

        import _pytest.capture

        assert isinstance(capsys, _pytest.capture.CaptureFixture)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["ok"] is False
        assert parsed["error"]["code"] == "ERR"
