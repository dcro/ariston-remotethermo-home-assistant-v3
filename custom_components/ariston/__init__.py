"""The Ariston integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from .ariston import AristonAPI, DeviceFeatures
from .coordinator import DeviceDataUpdateCoordinator, DeviceEnergyUpdateCoordinator
from .const import (
    COORDINATOR,
    DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES,
    DEFAULT_EXTRA_ENERGY_FEATURES,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    ENERGY_COORDINATOR,
    ENERGY_SCAN_INTERVAL,
    EXTRA_ENERGY_FEATURES,
)
from .device import AristonDevice

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_SCAN_INTERVAL,
    Platform,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE,
)
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
]

SERVICE_SET_ITEM_BY_ID = "set_item_by_id"
ATTR_ITEM_ID = "item_id"
ATTR_ZONE = "zone"
ATTR_VALUE = "value"

SET_ITEM_BY_ID_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_ITEM_ID): cv.string,
        vol.Required(ATTR_ZONE): cv.positive_int,
        vol.Required(ATTR_VALUE): vol.Coerce(float),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ariston from a config entry."""
    api = AristonAPI(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    reponse = await api.async_connect()
    if not reponse:
        _LOGGER.error("Failed to connect to Ariston")
        return False

    extra_energy_features = entry.options.get(
        EXTRA_ENERGY_FEATURES, DEFAULT_EXTRA_ENERGY_FEATURES
    )

    device = AristonDevice(
        entry.data[CONF_DEVICE], api, extra_energy_features, hass.config.units.is_metric
    )
    await device.async_get_features()

    scan_interval_seconds = entry.options.get(
        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
    )
    coordinator = DeviceDataUpdateCoordinator(hass, device, scan_interval_seconds)

    hass.data.setdefault(DOMAIN, {}).setdefault(
        entry.unique_id, {COORDINATOR: {}, ENERGY_COORDINATOR: {}}
    )
    hass.data[DOMAIN][entry.unique_id][COORDINATOR] = coordinator

    platforms: list[str] = PLATFORMS.copy()

    if device.features[DeviceFeatures.HAS_BOILER]:
        platforms.append(Platform.WATER_HEATER)

    await coordinator.async_config_entry_first_refresh()

    if device.features[DeviceFeatures.HAS_METERING]:
        energy_interval_minutes = entry.options.get(
            ENERGY_SCAN_INTERVAL, DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES
        )
        energy_coordinator = DeviceEnergyUpdateCoordinator(
            hass, device, energy_interval_minutes
        )
        hass.data[DOMAIN][entry.unique_id][ENERGY_COORDINATOR] = energy_coordinator
        await energy_coordinator.async_config_entry_first_refresh()

    hass.config_entries.async_setup_platforms(entry, platforms)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    async def async_set_item_by_id_service(service_call):
        """Create a vacation on the target device."""
        device_id = service_call.data[ATTR_DEVICE_ID]
        item_id = service_call.data.get(ATTR_ITEM_ID)
        zone = service_call.data.get(ATTR_ZONE)
        value = service_call.data.get(ATTR_VALUE)

        device_registry = dr.async_get(hass)
        device = device_registry.devices[device_id]

        entry = hass.config_entries.async_get_entry(next(iter(device.config_entries)))
        coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
            COORDINATOR
        ]
        await coordinator.device.async_set_item_by_id(item_id, value, zone)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ITEM_BY_ID,
        async_set_item_by_id_service,
        schema=SET_ITEM_BY_ID_SCHEMA,
    )

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    platforms: list[str] = PLATFORMS.copy()

    if hass.data[DOMAIN][entry.unique_id][COORDINATOR].device.features[
        DeviceFeatures.HAS_BOILER
    ]:
        platforms.append(Platform.WATER_HEATER)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.unique_id)

    return unload_ok
