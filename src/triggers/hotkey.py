"""
Hotkey trigger (Method 1) — Manual mode.

User switches layout to the target language first,
selects text, then presses the hotkey.

The direction is determined by the CURRENT layout:
- Current = UA  → convert EN→UA (text was typed in EN, user wants UA)
- Current = EN  → convert UA→EN (text was typed in UA, user wants EN)
"""

import logging
from typing import Optional

from src.core.converter import TextConverter
from src.backends.base import (
    PlatformBackend, Hotkey, Subscription,
)

logger = logging.getLogger(__name__)

DEFAULT_HOTKEY = "ctrl+shift+k"


class HotkeyTrigger:
    """Registers a global hotkey — converts selected text based on current layout."""

    def __init__(
        self,
        backend: PlatformBackend,
        converter: TextConverter,
        layout_id: str,
        layout_ids_config: dict,
        hotkey: str = DEFAULT_HOTKEY,
    ):
        self._backend = backend
        self._converter = converter
        self._layout_id = layout_id
        self._layout_ids = layout_ids_config
        self._hotkey_str = hotkey
        self._subscription: Optional[Subscription] = None

        # Build lang map: KLID -> language code
        self._klid_to_lang: dict[str, str] = {}
        windows_ids = self._layout_ids.get("windows", [])
        lang_codes = ["en", "ua"]
        for klid, lang in zip(windows_ids, lang_codes):
            self._klid_to_lang[klid] = lang

    def enable(self) -> None:
        """Registers the hotkey."""
        hotkey_obj = Hotkey.parse(self._hotkey_str)
        self._subscription = self._backend.register_hotkey(
            hotkey_obj, self._on_hotkey
        )
        logger.info(
            "Hotkey '%s' registered (layout=%s)",
            self._hotkey_str, self._layout_id,
        )

    def disable(self) -> None:
        """Unregisters the hotkey."""
        if self._subscription:
            self._subscription.unsubscribe()
            self._subscription = None

    def _on_hotkey(self) -> None:
        """Hotkey handler — determines conversion direction from current layout."""
        try:
            current_klid = self._backend.get_current_layout_id()
            if not current_klid:
                logger.warning("Could not detect current layout")
                return

            current_lang = self._klid_to_lang.get(current_klid)
            if current_lang is None:
                logger.warning("Unrecognized layout: %s", current_klid)
                return

            logger.debug(
                "Layout=%s (lang=%s)", current_klid, current_lang,
            )

            selected = self._backend.get_selected_text()
            if not selected:
                logger.warning("No text selected")
                return

            logger.debug("Selected text: '%s'", selected)

            # Use auto-detection: direction determined from current layout
            converted = self._converter.convert_auto(
                selected, self._layout_id,
                current_layout_id=current_klid,
            )

            logger.debug("Converted: '%s'", converted)

            self._backend.replace_selected_text(converted)

        except Exception as e:
            logger.exception("Conversion error: %s", e)