from __future__ import annotations

from tescmd.models.energy import CalendarHistory, GridImportExportConfig, SiteInfo


class TestSiteInfo:
    def test_all_fields(self) -> None:
        si = SiteInfo(
            energy_site_id=12345,
            site_name="Home Battery",
            resource_type="battery",
            backup_reserve_percent=20.0,
            default_real_mode="self_consumption",
            storm_mode_enabled=True,
            installation_date="2023-05-10",
        )
        assert si.energy_site_id == 12345
        assert si.site_name == "Home Battery"
        assert si.resource_type == "battery"
        assert si.backup_reserve_percent == 20.0
        assert si.default_real_mode == "self_consumption"
        assert si.storm_mode_enabled is True
        assert si.installation_date == "2023-05-10"

    def test_extra_fields_captured(self) -> None:
        si = SiteInfo(
            energy_site_id=12345,
            site_name="Home Battery",
            firmware_version="24.12.1",  # type: ignore[call-arg]
        )
        assert si.energy_site_id == 12345
        assert si.model_extra is not None
        assert si.model_extra["firmware_version"] == "24.12.1"

    def test_defaults_none(self) -> None:
        si = SiteInfo()
        assert si.energy_site_id is None
        assert si.site_name is None
        assert si.resource_type is None
        assert si.backup_reserve_percent is None
        assert si.default_real_mode is None
        assert si.storm_mode_enabled is None
        assert si.installation_date is None


class TestCalendarHistory:
    def test_with_time_series(self) -> None:
        entries = [
            {"timestamp": "2024-01-01T00:00:00Z", "solar_energy": 12.5},
            {"timestamp": "2024-01-02T00:00:00Z", "solar_energy": 10.3},
        ]
        ch = CalendarHistory(serial_number="SN001", time_series=entries)
        assert ch.serial_number == "SN001"
        assert len(ch.time_series) == 2
        assert ch.time_series[0]["solar_energy"] == 12.5
        assert ch.time_series[1]["timestamp"] == "2024-01-02T00:00:00Z"

    def test_defaults_empty_list(self) -> None:
        ch = CalendarHistory()
        assert ch.serial_number is None
        assert ch.time_series == []

    def test_extra_fields_captured(self) -> None:
        ch = CalendarHistory(
            serial_number="SN001",
            period="day",  # type: ignore[call-arg]
        )
        assert ch.serial_number == "SN001"
        assert ch.model_extra is not None
        assert ch.model_extra["period"] == "day"


class TestGridImportExportConfig:
    def test_all_fields(self) -> None:
        cfg = GridImportExportConfig(
            disallow_charge_from_grid_with_solar_installed=True,
            customer_preferred_export_rule="pv_only",
        )
        assert cfg.disallow_charge_from_grid_with_solar_installed is True
        assert cfg.customer_preferred_export_rule == "pv_only"

    def test_extra_fields_captured(self) -> None:
        cfg = GridImportExportConfig(
            customer_preferred_export_rule="battery_ok",
            grid_region="US-CA",  # type: ignore[call-arg]
        )
        assert cfg.customer_preferred_export_rule == "battery_ok"
        assert cfg.model_extra is not None
        assert cfg.model_extra["grid_region"] == "US-CA"

    def test_defaults_none(self) -> None:
        cfg = GridImportExportConfig()
        assert cfg.disallow_charge_from_grid_with_solar_installed is None
        assert cfg.customer_preferred_export_rule is None
