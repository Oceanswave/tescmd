"""Command dispatcher for inbound OpenClaw gateway requests.

Maps OpenClaw method names (e.g. ``door.lock``, ``battery.get``) to
Tesla Fleet API calls.  Read handlers check the :class:`TelemetryStore`
first; write handlers call the command API, auto-wake once on
:class:`VehicleAsleepError`, and invalidate the cache on success.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from tescmd._internal.units import celsius_to_fahrenheit, fahrenheit_to_celsius
from tescmd.api.errors import VehicleAsleepError
from tescmd.cli._client import (
    check_command_guards,
    get_command_api,
    get_vehicle_api,
    invalidate_cache_for_vin,
)
from tescmd.triggers.models import TriggerCondition, TriggerDefinition, TriggerOperator

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext
    from tescmd.openclaw.telemetry_store import TelemetryStore
    from tescmd.triggers.manager import TriggerManager

logger = logging.getLogger(__name__)


# API snake_case → OpenClaw dot notation aliases for system.run
_METHOD_ALIASES: dict[str, str] = {
    "door_lock": "door.lock",
    "door_unlock": "door.unlock",
    "auto_conditioning_start": "climate.on",
    "auto_conditioning_stop": "climate.off",
    "set_temps": "climate.set_temp",
    "set_preconditioning_max": "climate.defrost",
    "charge_start": "charge.start",
    "charge_stop": "charge.stop",
    "set_charge_limit": "charge.set_limit",
    "actuate_trunk": "trunk.open",
    "flash_lights": "flash_lights",
    "honk_horn": "honk_horn",
    "share": "nav.send",
    "navigation_gps_request": "nav.gps",
    "navigation_sc_request": "nav.supercharger",
    "navigation_waypoints_request": "nav.waypoints",
    "trigger_homelink": "homelink.trigger",
    "list_triggers": "trigger.list",
}


class CommandDispatcher:
    """Dispatch OpenClaw inbound requests to the Tesla Fleet API.

    Parameters
    ----------
    vin:
        Vehicle Identification Number to target.
    app_ctx:
        CLI application context (provides API client builders and cache).
    telemetry_store:
        Optional in-memory store of recent telemetry values.  When
        available, read handlers check here first before hitting the API.
    """

    def __init__(
        self,
        vin: str,
        app_ctx: AppContext,
        telemetry_store: TelemetryStore | None = None,
        trigger_manager: TriggerManager | None = None,
    ) -> None:
        self._vin = vin
        self._app_ctx = app_ctx
        self._store = telemetry_store
        self._trigger_manager = trigger_manager
        self._vehicle_data_cache: dict[str, Any] | None = None
        self._fetch_task: asyncio.Task[None] | None = None
        self._handlers: dict[str, Any] = {
            # Reads
            "location.get": self._handle_location_get,
            "battery.get": self._handle_battery_get,
            "temperature.get": self._handle_temperature_get,
            "speed.get": self._handle_speed_get,
            "charge_state.get": self._handle_charge_state_get,
            "security.get": self._handle_security_get,
            "telemetry.get": self._handle_telemetry_get,
            # Writes
            "door.lock": self._handle_door_lock,
            "door.unlock": self._handle_door_unlock,
            "climate.on": self._handle_climate_on,
            "climate.off": self._handle_climate_off,
            "climate.set_temp": self._handle_climate_set_temp,
            "climate.defrost": self._handle_climate_defrost,
            "charge.start": self._handle_charge_start,
            "charge.stop": self._handle_charge_stop,
            "charge.set_limit": self._handle_charge_set_limit,
            "trunk.open": self._handle_trunk_open,
            "frunk.open": self._handle_frunk_open,
            "flash_lights": self._handle_flash_lights,
            "honk_horn": self._handle_honk_horn,
            "sentry.on": self._handle_sentry_on,
            "sentry.off": self._handle_sentry_off,
            "nav.send": self._handle_nav_send,
            "nav.gps": self._handle_nav_gps,
            "nav.supercharger": self._handle_nav_supercharger,
            "nav.waypoints": self._handle_nav_waypoints,
            "homelink.trigger": self._handle_homelink,
            "system.run": self._handle_system_run,
            # Shared trigger operations
            "trigger.create": self._handle_trigger_create,
            "trigger.list": self._handle_trigger_list_all,
            "trigger.delete": self._handle_trigger_delete,
            # Domain-specific trigger CRUD
            "cabin_temp.trigger": self._handle_cabin_temp_trigger,
            "cabin_temp.trigger.list": self._handle_cabin_temp_list,
            "cabin_temp.trigger.delete": self._handle_trigger_delete,
            "outside_temp.trigger": self._handle_outside_temp_trigger,
            "outside_temp.trigger.list": self._handle_outside_temp_list,
            "outside_temp.trigger.delete": self._handle_trigger_delete,
            "battery.trigger": self._handle_battery_trigger,
            "battery.trigger.list": self._handle_battery_list,
            "battery.trigger.delete": self._handle_trigger_delete,
            "location.trigger": self._handle_location_trigger,
            "location.trigger.list": self._handle_location_list,
            "location.trigger.delete": self._handle_trigger_delete,
        }

    async def dispatch(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        """Dispatch an inbound request to the appropriate handler.

        Returns ``None`` for unknown methods (gateway sends error
        response).  Raises on handler errors (gateway catches and
        returns error response).
        """
        method = msg.get("method", "")
        logger.debug("Dispatch: method=%s id=%s", method, msg.get("id", "?"))
        handler = self._handlers.get(method)
        if handler is None:
            logger.warning("No handler for method: %s", method)
            return None
        params = msg.get("params", {})
        result: dict[str, Any] | None = await handler(params)
        logger.debug("Dispatch result for %s: %s", method, result)
        return result

    # -- Read helpers --------------------------------------------------------

    def _store_get(self, field_name: str) -> Any | None:
        """Return the latest value from the telemetry store, or None."""
        if self._store is None:
            return None
        snap = self._store.get(field_name)
        return snap.value if snap is not None else None

    async def _get_vehicle_data(self) -> dict[str, Any]:
        """Fetch full vehicle data via the API (with auto-wake retry).

        Caches the result so subsequent read handlers within the same
        request batch don't trigger duplicate API calls.
        """
        if self._vehicle_data_cache is not None:
            return self._vehicle_data_cache
        logger.debug("Fetching vehicle data from Fleet API for %s", self._vin)
        client, vehicle_api = get_vehicle_api(self._app_ctx)
        try:
            vdata = await self._auto_wake(lambda: vehicle_api.get_vehicle_data(self._vin))
            data: dict[str, Any] = vdata.model_dump()
            self._vehicle_data_cache = data
            return data
        finally:
            await client.close()

    def _get_vehicle_data_or_none(self) -> dict[str, Any] | None:
        """Return cached vehicle data if available, else ``None``."""
        return self._vehicle_data_cache

    def _schedule_vehicle_data_fetch(self) -> None:
        """Kick off a background fetch if one isn't already running."""
        if self._fetch_task is not None and not self._fetch_task.done():
            return

        async def _bg_fetch() -> None:
            try:
                await self._get_vehicle_data()
                logger.info("Background vehicle data fetch complete")
            except Exception:
                logger.warning("Background vehicle data fetch failed", exc_info=True)

        self._fetch_task = asyncio.create_task(_bg_fetch())

    # -- Read handlers -------------------------------------------------------

    def _read_from_api_cache(self, extractor: str) -> dict[str, Any] | None:
        """Try to answer from the cached vehicle data.

        *extractor* is a dot path like ``"drive_state"`` or
        ``"charge_state"``.  Returns the sub-dict or ``None`` if no
        cached data is available.  Kicks off a background fetch if the
        cache is empty.
        """
        vdata = self._get_vehicle_data_or_none()
        if vdata is None:
            self._schedule_vehicle_data_fetch()
            return None
        return vdata.get(extractor) or {}

    async def _handle_location_get(self, params: dict[str, Any]) -> dict[str, Any]:
        loc = self._store_get("Location")
        if loc is not None and isinstance(loc, dict):
            return {
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
                "heading": loc.get("heading"),
                "speed": loc.get("speed"),
            }
        drive = self._read_from_api_cache("drive_state")
        if drive is None:
            return {"pending": True}
        return {
            "latitude": drive.get("latitude"),
            "longitude": drive.get("longitude"),
            "heading": drive.get("heading"),
            "speed": drive.get("speed"),
        }

    async def _handle_battery_get(self, params: dict[str, Any]) -> dict[str, Any]:
        soc = self._store_get("Soc") or self._store_get("BatteryLevel")
        range_mi = self._store_get("EstBatteryRange")
        if soc is not None:
            result: dict[str, Any] = {"battery_level": soc}
            if range_mi is not None:
                result["range_miles"] = range_mi
            return result
        cs = self._read_from_api_cache("charge_state")
        if cs is None:
            return {"pending": True}
        return {
            "battery_level": cs.get("battery_level"),
            "range_miles": cs.get("battery_range"),
        }

    async def _handle_temperature_get(self, params: dict[str, Any]) -> dict[str, Any]:
        inside = self._store_get("InsideTemp")
        outside = self._store_get("OutsideTemp")
        if inside is not None or outside is not None:
            result: dict[str, Any] = {}
            if inside is not None:
                result["inside_temp_c"] = inside
            if outside is not None:
                result["outside_temp_c"] = outside
            return result
        climate = self._read_from_api_cache("climate_state")
        if climate is None:
            return {"pending": True}
        return {
            "inside_temp_c": climate.get("inside_temp"),
            "outside_temp_c": climate.get("outside_temp"),
        }

    async def _handle_speed_get(self, params: dict[str, Any]) -> dict[str, Any]:
        speed = self._store_get("VehicleSpeed")
        if speed is not None:
            return {"speed_mph": speed}
        drive = self._read_from_api_cache("drive_state")
        if drive is None:
            return {"pending": True}
        return {"speed_mph": drive.get("speed")}

    async def _handle_charge_state_get(self, params: dict[str, Any]) -> dict[str, Any]:
        state = self._store_get("ChargeState") or self._store_get("DetailedChargeState")
        if state is not None:
            return {"charge_state": state}
        cs = self._read_from_api_cache("charge_state")
        if cs is None:
            return {"pending": True}
        return {"charge_state": cs.get("charging_state")}

    async def _handle_security_get(self, params: dict[str, Any]) -> dict[str, Any]:
        locked = self._store_get("Locked")
        sentry = self._store_get("SentryMode")
        if locked is not None or sentry is not None:
            result: dict[str, Any] = {}
            if locked is not None:
                result["locked"] = locked
            if sentry is not None:
                result["sentry_mode"] = sentry
            return result
        vs = self._read_from_api_cache("vehicle_state")
        if vs is None:
            return {"pending": True}
        return {
            "locked": vs.get("locked"),
            "sentry_mode": vs.get("sentry_mode"),
        }

    async def _handle_telemetry_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Read the latest value of any telemetry field from the store."""
        field = params.get("field", "")
        if not field:
            raise ValueError("telemetry.get requires 'field' parameter")
        value = self._store_get(field)
        if value is None:
            return {"field": field, "pending": True}
        return {"field": field, "value": value}

    # -- Write helpers -------------------------------------------------------

    async def _auto_wake(self, operation: Any) -> Any:
        """Retry *operation* once after waking on VehicleAsleepError."""
        try:
            return await operation()
        except VehicleAsleepError:
            pass

        logger.info("Vehicle asleep — sending wake for %s", self._vin)
        client, vehicle_api = get_vehicle_api(self._app_ctx)
        try:
            await vehicle_api.wake(self._vin)
        finally:
            await client.close()

        return await operation()

    async def _execute_command(self, method_name: str, body: dict[str, Any] | None = None) -> str:
        """Execute a vehicle command and return the reason string."""
        client, _vehicle_api, cmd_api = get_command_api(self._app_ctx)
        check_command_guards(cmd_api, method_name)
        try:
            method = getattr(cmd_api, method_name)

            async def _call() -> Any:
                return await method(self._vin, **body) if body else await method(self._vin)

            result = await self._auto_wake(_call)
        finally:
            await client.close()

        invalidate_cache_for_vin(self._app_ctx, self._vin)
        return result.response.reason or "ok"

    # -- Write handlers ------------------------------------------------------

    async def _simple_command(
        self, method_name: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a command and return ``{result: True, reason: ...}``."""
        reason = await self._execute_command(method_name, body)
        return {"result": True, "reason": reason}

    async def _handle_door_lock(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("door_lock")

    async def _handle_door_unlock(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("door_unlock")

    async def _handle_climate_on(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("auto_conditioning_start")

    async def _handle_climate_off(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("auto_conditioning_stop")

    async def _handle_climate_set_temp(self, params: dict[str, Any]) -> dict[str, Any]:
        temp = params.get("temp")
        if temp is None:
            raise ValueError("climate.set_temp requires 'temp' parameter")
        temp_f = float(temp)
        return await self._simple_command(
            "set_temps", {"driver_temp": temp_f, "passenger_temp": temp_f}
        )

    async def _handle_climate_defrost(self, params: dict[str, Any]) -> dict[str, Any]:
        on = params.get("on", True)
        return await self._simple_command(
            "set_preconditioning_max", {"on": bool(on), "manual_override": True}
        )

    async def _handle_charge_start(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("charge_start")

    async def _handle_charge_stop(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("charge_stop")

    async def _handle_charge_set_limit(self, params: dict[str, Any]) -> dict[str, Any]:
        percent = params.get("percent")
        if percent is None:
            raise ValueError("charge.set_limit requires 'percent' parameter")
        return await self._simple_command("set_charge_limit", {"percent": int(percent)})

    async def _handle_trunk_open(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("actuate_trunk", {"which_trunk": "rear"})

    async def _handle_frunk_open(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("actuate_trunk", {"which_trunk": "front"})

    async def _handle_flash_lights(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("flash_lights")

    async def _handle_honk_horn(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("honk_horn")

    async def _handle_sentry_on(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("set_sentry_mode", {"on": True})

    async def _handle_sentry_off(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("set_sentry_mode", {"on": False})

    # -- Navigation handlers -------------------------------------------------

    async def _handle_nav_send(self, params: dict[str, Any]) -> dict[str, Any]:
        address = params.get("address")
        if not address:
            raise ValueError("nav.send requires 'address' parameter")
        return await self._simple_command("share", {"address": address})

    async def _handle_nav_gps(self, params: dict[str, Any]) -> dict[str, Any]:
        lat = params.get("lat")
        lon = params.get("lon")
        if lat is None or lon is None:
            raise ValueError("nav.gps requires 'lat' and 'lon' parameters")
        body: dict[str, Any] = {"lat": float(lat), "lon": float(lon)}
        order = params.get("order")
        if order is not None:
            body["order"] = int(order)
        return await self._simple_command("navigation_gps_request", body)

    async def _handle_nav_supercharger(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._simple_command("navigation_sc_request")

    async def _handle_nav_waypoints(self, params: dict[str, Any]) -> dict[str, Any]:
        waypoints = params.get("waypoints")
        if not waypoints:
            raise ValueError("nav.waypoints requires 'waypoints' parameter")
        return await self._simple_command("navigation_waypoints_request", {"waypoints": waypoints})

    async def _handle_homelink(self, params: dict[str, Any]) -> dict[str, Any]:
        lat = params.get("lat")
        lon = params.get("lon")
        if lat is None or lon is None:
            raise ValueError("homelink.trigger requires 'lat' and 'lon' parameters")
        return await self._simple_command(
            "trigger_homelink", {"lat": float(lat), "lon": float(lon)}
        )

    # -- Meta-dispatch handler -----------------------------------------------

    async def _handle_system_run(self, params: dict[str, Any]) -> dict[str, Any] | None:
        """Invoke any registered handler by name.

        Accepts both OpenClaw-style (``door.lock``) and API-style
        (``door_lock``) method names via :data:`_METHOD_ALIASES`.

        The target method can be specified as ``method`` or ``command``
        (the latter mirrors the gateway protocol's field name).

        Returns ``None`` for unknown inner methods so the gateway can
        send a clean error response without a traceback.
        """
        raw = params.get("method", "") or params.get("command", "")
        # Normalize: bots may send a list like ["door.lock"] instead of a string
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        method = str(raw).strip() if raw else ""
        if not method:
            raise ValueError("system.run requires 'method' (or 'command') parameter")
        resolved = _METHOD_ALIASES.get(method, method)
        if resolved == "system.run":
            raise ValueError("system.run cannot invoke itself")
        logger.info("system.run → %s", resolved)
        inner_params = params.get("params", {})
        result = await self.dispatch({"method": resolved, "params": inner_params})
        if result is None:
            logger.warning("system.run: unknown inner method %s (resolved: %s)", method, resolved)
        return result

    # -- Trigger handlers ----------------------------------------------------

    def _require_trigger_manager(self) -> TriggerManager:
        """Return the trigger manager or raise if unavailable."""
        if self._trigger_manager is None:
            raise RuntimeError("Triggers not available")
        return self._trigger_manager

    async def _handle_trigger_create(self, params: dict[str, Any]) -> dict[str, Any]:
        """Create a new trigger from the given condition parameters.

        After creation, immediately evaluates the trigger against the
        current telemetry store value.  If the condition is already
        satisfied, the event is fired and the trigger is deleted — the
        response includes ``"immediate": True`` so the caller knows.
        """
        mgr = self._require_trigger_manager()
        field = params.get("field", "")
        if not field:
            raise ValueError("trigger.create requires 'field' parameter")

        op_str = params.get("operator", "")
        if not op_str:
            raise ValueError("trigger.create requires 'operator' parameter")

        operator = TriggerOperator(op_str)
        condition = TriggerCondition(
            field=field,
            operator=operator,
            value=params.get("value"),
        )
        trigger = TriggerDefinition(
            condition=condition,
            once=params.get("once", False),
            cooldown_seconds=params.get("cooldown_seconds", 60.0),
        )
        created = mgr.create(trigger)

        result: dict[str, Any] = {
            "id": created.id,
            "field": created.condition.field,
            "operator": created.condition.operator.value,
        }

        # Immediate evaluation: if the telemetry store already has a
        # value for this field that satisfies the condition, fire now.
        # One-shot triggers are NOT deleted here — the push callback
        # handles deletion after confirmed WebSocket delivery.
        if self._store is not None:
            snap = self._store.get(field)
            if snap is not None:
                from datetime import UTC, datetime

                fired = await mgr.evaluate_single(
                    created.id, snap.value, None, datetime.now(UTC)
                )
                if fired:
                    result["immediate"] = True
                    logger.info(
                        "Trigger %s fired immediately (value=%s)%s",
                        created.id,
                        snap.value,
                        " — once, pending delivery" if created.once else " — kept (persistent)",
                    )

        return result

    async def _handle_trigger_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        """Delete a trigger by ID."""
        mgr = self._require_trigger_manager()
        trigger_id = params.get("id", "")
        if not trigger_id:
            raise ValueError("trigger.delete requires 'id' parameter")
        deleted = mgr.delete(trigger_id)
        return {"deleted": deleted, "id": trigger_id}

    def _list_triggers_for_field(
        self, field: str, *, show_fahrenheit: bool = False
    ) -> dict[str, Any]:
        """List triggers filtered to a specific telemetry field.

        When *show_fahrenheit* is ``True``, a ``value_f`` display field is
        added for numeric thresholds (temperature triggers stored in °C).
        """
        mgr = self._require_trigger_manager()
        triggers = [t for t in mgr.list_all() if t.condition.field == field]
        result = []
        for t in triggers:
            entry: dict[str, Any] = {
                "id": t.id,
                "field": t.condition.field,
                "operator": t.condition.operator.value,
                "value": t.condition.value,
                "once": t.once,
                "cooldown_seconds": t.cooldown_seconds,
            }
            if show_fahrenheit and t.condition.value is not None:
                try:
                    entry["value_f"] = celsius_to_fahrenheit(float(t.condition.value))
                except (TypeError, ValueError):
                    logger.debug(
                        "Could not convert trigger %s value %r to Fahrenheit",
                        t.id,
                        t.condition.value,
                    )
            result.append(entry)
        return {"triggers": result}

    async def _handle_cabin_temp_list(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._list_triggers_for_field("InsideTemp", show_fahrenheit=True)

    async def _handle_outside_temp_list(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._list_triggers_for_field("OutsideTemp", show_fahrenheit=True)

    async def _handle_battery_list(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._list_triggers_for_field("BatteryLevel")

    async def _handle_location_list(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._list_triggers_for_field("Location")

    async def _handle_trigger_list_all(self, params: dict[str, Any]) -> dict[str, Any]:
        """List ALL triggers across all fields."""
        mgr = self._require_trigger_manager()
        triggers = mgr.list_all()
        result = []
        for t in triggers:
            entry: dict[str, Any] = {
                "id": t.id,
                "field": t.condition.field,
                "operator": t.condition.operator.value,
                "value": t.condition.value,
                "once": t.once,
                "cooldown_seconds": t.cooldown_seconds,
            }
            result.append(entry)
        return {"triggers": result}

    # -- Convenience trigger aliases -----------------------------------------

    async def _handle_cabin_temp_trigger(self, params: dict[str, Any]) -> dict[str, Any]:
        converted = {**params, "field": "InsideTemp"}
        if "value" in converted and converted["value"] is not None:
            f_val = float(converted["value"])
            converted["value"] = fahrenheit_to_celsius(f_val)
            logger.debug(
                "cabin_temp.trigger: converted %.1f°F → %.1f°C", f_val, converted["value"]
            )
        return await self._handle_trigger_create(converted)

    async def _handle_outside_temp_trigger(self, params: dict[str, Any]) -> dict[str, Any]:
        converted = {**params, "field": "OutsideTemp"}
        if "value" in converted and converted["value"] is not None:
            f_val = float(converted["value"])
            converted["value"] = fahrenheit_to_celsius(f_val)
            logger.debug(
                "outside_temp.trigger: converted %.1f°F → %.1f°C", f_val, converted["value"]
            )
        return await self._handle_trigger_create(converted)

    async def _handle_battery_trigger(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._handle_trigger_create({**params, "field": "BatteryLevel"})

    async def _handle_location_trigger(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._handle_trigger_create({**params, "field": "Location"})
