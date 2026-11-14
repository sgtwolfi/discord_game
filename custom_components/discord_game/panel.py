"""Register the GHOST administration panel in the Home Assistant sidebar."""

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PANEL_PATH = "ghost-assistant"
STATIC_URL = f"/{DOMAIN}_ghost"
STATIC_DIR = Path(__file__).parent / "frontend"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the GHOST panel and its static JavaScript module once."""
    if hass.data.setdefault(DOMAIN, {}).get("_ghost_panel_registered"):
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(STATIC_DIR), cache_headers=False)]
    )
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="discord-game-ghost-panel",
        frontend_url_path=PANEL_PATH,
        sidebar_title="GHOST",
        sidebar_icon="mdi:robot",
        module_url=f"{STATIC_URL}/ghost-panel.js",
        require_admin=True,
        embed_iframe=False,
    )
    hass.data[DOMAIN]["_ghost_panel_registered"] = True


def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the panel after the final Discord Game entry is unloaded."""
    frontend.async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)
    hass.data.get(DOMAIN, {}).pop("_ghost_panel_registered", None)
