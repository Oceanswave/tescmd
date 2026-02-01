"""Tests for the CSVLogSink wide-format CSV telemetry log."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from tescmd.telemetry.csv_sink import CSVLogSink, create_log_path
from tescmd.telemetry.decoder import TelemetryDatum, TelemetryFrame

if TYPE_CHECKING:
    from pathlib import Path

VIN = "5YJ3E1EA0KF000001"


def _frame(
    *fields: tuple[str, int, Any, str],
    vin: str = VIN,
    ts: datetime | None = None,
) -> TelemetryFrame:
    return TelemetryFrame(
        vin=vin,
        created_at=ts or datetime.now(UTC),
        data=[
            TelemetryDatum(field_name=name, field_id=fid, value=val, value_type=vtype)
            for name, fid, val, vtype in fields
        ],
    )


# ---------------------------------------------------------------------------
# create_log_path
# ---------------------------------------------------------------------------


class TestCreateLogPath:
    def test_creates_log_directory(self, tmp_path: Path) -> None:
        path = create_log_path(VIN, config_dir=tmp_path)
        assert path.parent.exists()
        assert path.parent.name == "logs"

    def test_filename_contains_vin(self, tmp_path: Path) -> None:
        path = create_log_path(VIN, config_dir=tmp_path)
        assert VIN in path.name

    def test_filename_ends_with_csv(self, tmp_path: Path) -> None:
        path = create_log_path(VIN, config_dir=tmp_path)
        assert path.suffix == ".csv"

    def test_default_config_dir(self) -> None:
        path = create_log_path(VIN)
        assert ".config" in str(path) or "tescmd" in str(path)


# ---------------------------------------------------------------------------
# CSVLogSink — basic output
# ---------------------------------------------------------------------------


class TestCSVLogSinkBasic:
    @pytest.mark.asyncio
    async def test_single_frame_writes_header_and_row(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)

        await sink.on_frame(_frame(("BatteryLevel", 8, 80, "int")))
        sink.close()

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["BatteryLevel"] == "80"
        assert rows[0]["vin"] == VIN
        assert "timestamp" in rows[0]

    @pytest.mark.asyncio
    async def test_multiple_fields_in_one_frame(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)

        await sink.on_frame(
            _frame(
                ("BatteryLevel", 8, 80, "int"),
                ("InsideTemp", 33, 22.5, "float"),
                ("VehicleSpeed", 29, 65, "int"),
            )
        )
        sink.close()

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["BatteryLevel"] == "80"
        assert rows[0]["InsideTemp"] == "22.5"
        assert rows[0]["VehicleSpeed"] == "65"

    @pytest.mark.asyncio
    async def test_multiple_frames(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)

        await sink.on_frame(_frame(("BatteryLevel", 8, 80, "int")))
        await sink.on_frame(_frame(("BatteryLevel", 8, 79, "int")))
        await sink.on_frame(_frame(("BatteryLevel", 8, 78, "int")))
        sink.close()

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 3
        assert rows[0]["BatteryLevel"] == "80"
        assert rows[1]["BatteryLevel"] == "79"
        assert rows[2]["BatteryLevel"] == "78"

    @pytest.mark.asyncio
    async def test_frame_count(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)

        assert sink.frame_count == 0
        await sink.on_frame(_frame(("BatteryLevel", 8, 80, "int")))
        assert sink.frame_count == 1
        await sink.on_frame(_frame(("BatteryLevel", 8, 79, "int")))
        assert sink.frame_count == 2
        sink.close()

    @pytest.mark.asyncio
    async def test_log_path_property(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)
        assert sink.log_path == csv_path
        sink.close()


# ---------------------------------------------------------------------------
# CSVLogSink — dynamic field discovery
# ---------------------------------------------------------------------------


class TestCSVLogSinkDynamicFields:
    @pytest.mark.asyncio
    async def test_new_field_extends_header(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)

        # First frame has BatteryLevel only.
        await sink.on_frame(_frame(("BatteryLevel", 8, 80, "int")))

        # Second frame introduces InsideTemp.
        await sink.on_frame(
            _frame(
                ("BatteryLevel", 8, 79, "int"),
                ("InsideTemp", 33, 22.5, "float"),
            )
        )
        sink.close()

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Both rows should exist; first row has empty InsideTemp.
        assert len(rows) == 2
        assert "InsideTemp" in reader.fieldnames  # type: ignore[operator]
        assert rows[0]["InsideTemp"] == ""
        assert rows[1]["InsideTemp"] == "22.5"

    @pytest.mark.asyncio
    async def test_sparse_rows(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)

        # Frame 1: field A
        await sink.on_frame(_frame(("FieldA", 1, 100, "int")))
        # Frame 2: field B only (A absent)
        await sink.on_frame(_frame(("FieldB", 2, 200, "int")))
        sink.close()

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert rows[0]["FieldA"] == "100"
        assert rows[0].get("FieldB", "") == ""
        assert rows[1].get("FieldA", "") == ""
        assert rows[1]["FieldB"] == "200"


# ---------------------------------------------------------------------------
# CSVLogSink — VIN filtering
# ---------------------------------------------------------------------------


class TestCSVLogSinkVINFilter:
    @pytest.mark.asyncio
    async def test_wrong_vin_ignored(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)

        await sink.on_frame(_frame(("BatteryLevel", 8, 80, "int"), vin="OTHER_VIN"))
        sink.close()

        assert sink.frame_count == 0
        # File should not even be created (lazy open).
        assert not csv_path.exists()

    @pytest.mark.asyncio
    async def test_no_vin_filter_logs_all(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=None)

        await sink.on_frame(_frame(("BatteryLevel", 8, 80, "int"), vin="VIN_A"))
        await sink.on_frame(_frame(("BatteryLevel", 8, 79, "int"), vin="VIN_B"))
        sink.close()

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 2
        assert rows[0]["vin"] == "VIN_A"
        assert rows[1]["vin"] == "VIN_B"


# ---------------------------------------------------------------------------
# CSVLogSink — special values
# ---------------------------------------------------------------------------


class TestCSVLogSinkSpecialValues:
    @pytest.mark.asyncio
    async def test_location_dict_flattened(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)

        await sink.on_frame(
            _frame(("Location", 9, {"latitude": 37.77, "longitude": -122.42}, "location"))
        )
        sink.close()

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert "latitude=37.77" in rows[0]["Location"]
        assert "longitude=-122.42" in rows[0]["Location"]

    @pytest.mark.asyncio
    async def test_boolean_values(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)

        await sink.on_frame(_frame(("Locked", 50, True, "bool")))
        sink.close()

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert rows[0]["Locked"] == "True"

    @pytest.mark.asyncio
    async def test_none_value(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)

        await sink.on_frame(_frame(("FieldX", 99, None, "invalid")))
        sink.close()

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert rows[0]["FieldX"] == ""


# ---------------------------------------------------------------------------
# CSVLogSink — flush behavior
# ---------------------------------------------------------------------------


class TestCSVLogSinkFlush:
    @pytest.mark.asyncio
    async def test_periodic_flush(self, tmp_path: Path) -> None:
        """After 10 frames the file should be flushed (readable without close)."""
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)

        for i in range(11):
            await sink.on_frame(_frame(("BatteryLevel", 8, 80 - i, "int")))

        # File should be readable without closing the sink.
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) >= 10
        sink.close()

    @pytest.mark.asyncio
    async def test_close_flushes(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)

        await sink.on_frame(_frame(("BatteryLevel", 8, 80, "int")))
        sink.close()

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_double_close_is_safe(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        sink = CSVLogSink(csv_path, vin=VIN)
        await sink.on_frame(_frame(("BatteryLevel", 8, 80, "int")))
        sink.close()
        sink.close()  # Should not raise.
