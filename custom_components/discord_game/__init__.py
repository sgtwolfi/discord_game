"""Component to integrate with Discord and get information about users online and game status."""
from homeassistant import config_entries, core
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv

from .const import DATA_HASS_CONFIG, DOMAIN
from .panel import async_register_panel, async_unregister_panel
from .services import async_setup_services, async_unload_services
from .websocket import async_register_websocket

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(
        hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Set up platform from a ConfigEntry."""
    # Merge data and options so sensor.py reads the latest values
    config = {**entry.data, **entry.options}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = config

    unsub = entry.add_update_listener(_async_options_updated)
    hass.data[DOMAIN][f"{entry.entry_id}_unsub_options"] = unsub

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_services(hass)
    await async_register_panel(hass)
    async_register_websocket(hass)

    return True


async def _async_options_updated(
        hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
        hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
        unsub = hass.data[DOMAIN].pop(f"{entry.entry_id}_unsub_options", None)
        if unsub:
            unsub()
        await async_unload_services(hass)
        remaining_entries = [
            key for key in hass.data.get(DOMAIN, {})
            if not key.startswith("_") and not key.endswith("_unsub_options")
        ]
        if not remaining_entries:
            async_unregister_panel(hass)

    return unload_ok


async def async_setup(hass: core.HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DATA_HASS_CONFIG] = config
    return True
