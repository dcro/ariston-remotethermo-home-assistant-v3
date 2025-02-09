"""Support for Ariston sensors."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
)

from .entity import AristonEntity
from .const import (
    ARISTON_BINARY_SENSOR_TYPES,
    COORDINATOR,
    DOMAIN,
    AristonBinarySensorEntityDescription,
)
from .coordinator import DeviceDataUpdateCoordinator, DeviceEnergyUpdateCoordinator
from .ariston import (
    DeviceAttribute,
    DeviceProperties,
    PropertyType,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_CREATE_VACATION = "create_vacation"
ATTR_END_DATE = "end_date"

CREATE_VACATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_END_DATE): cv.date,
    }
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    ariston_binary_sensors: list[AristonBinarySensor] = []
    for description in ARISTON_BINARY_SENSOR_TYPES:
        coordinator: DeviceDataUpdateCoordinator or DeviceEnergyUpdateCoordinator = (
            hass.data[DOMAIN][entry.unique_id][description.coordinator]
        )
        if coordinator.device.are_device_features_available(
            description.device_features, description.extra_energy_feature
        ):
            ariston_binary_sensors.append(AristonBinarySensor(coordinator, description))

    async_add_entities(ariston_binary_sensors)

    async def async_create_vacation_service(service_call):
        """Create a vacation on the target device."""
        device_id = service_call.data[ATTR_DEVICE_ID]
        end_date = service_call.data.get(ATTR_END_DATE, None)

        device_registry = dr.async_get(hass)
        device = device_registry.devices[device_id]

        entry = hass.config_entries.async_get_entry(next(iter(device.config_entries)))
        coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
            COORDINATOR
        ]
        await coordinator.device.async_set_holiday(end_date)
        for ariston_binary_sensor in ariston_binary_sensors:
            if ariston_binary_sensor.entity_description.key is DeviceProperties.HOLIDAY:
                ariston_binary_sensor.async_write_ha_state()

    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_VACATION,
        async_create_vacation_service,
        schema=CREATE_VACATION_SCHEMA,
    )


class AristonBinarySensor(AristonEntity, BinarySensorEntity):
    """Base class for specific ariston binary sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator or DeviceEnergyUpdateCoordinator,
        description: AristonBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description)

    @property
    def unique_id(self):
        """Return the unique id."""
        return (
            f"{self.coordinator.device.attributes[DeviceAttribute.GW_ID]}-{self.name}"
        )

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        return self.coordinator.device.get_item_by_id(
            self.entity_description.key, PropertyType.VALUE
        )
