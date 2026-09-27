"""
Layout change watcher trigger (Method 2).

User selects text -> switches layout using standard OS method
(Win+Space / Alt+Shift / click) -> program AUTOMATICALLY detects it
-> copies text -> converts -> pastes result.
"""

import logging
from typing import Optional

from src.core.converter import TextConverter
from src.backends.base import PlatformBackend, Subscription

logger = logging.getLogger(__name__)


class LayoutWatcherTrigger:
    """Watches for layout changes and automatically converts selected text."""

    def __init__(
        self,
        backend: PlatformBackend,
        converter: TextConverter,
        layout_id: str,
        layout_ids_config: dict,
    ):
        """
        Args:
            backend: platform-dependent backend
            converter: character converter
            layout_id: layout ID from config (e.g. 'en_ua')
            layout_ids_config: platform -> [id1, id2] mapping
                              (e.g. {"windows": ["00000409", "00000422"]})
        """
        self._backend = backend
        self._converter = converter
        self._layout_id = layout_id
        self._layout_ids = layout_ids_config
        self._enabled = False

        # Map: KLID -> language code ("00000409" -> "en", "00000422" -> "ua")
        self._subscription: Optional[Subscription] = None
        self._klid_to_lang: dict[str, str] = {}
        self._lang_to_mapping: dict[str, str] = {}

    def enable(self) -> None:
        """Starts watching for layout changes."""
        if self._enabled:
            return

        self._build_lang_map()
        self._subscription = self._backend.on_layout_change(self._on_layout_change)
        self._enabled = True
        logger.info("LayoutWatcherTrigger enabled")

    def disable(self) -> None:
        """Stops watching for layout changes."""
        self._enabled = False
        if self._subscription:
            self._subscription.unsubscribe()
            self._subscription = None

    def _build_lang_map(self) -> None:
        """Builds KLID -> language mapping from config.

        Example: for en_ua and windows:
            "00000409" -> "en"
            "00000422" -> "ua"
        """
        windows_ids = self._layout_ids.get("windows", [])
        if len(windows_ids) >= 2:
            # Assume order [en_id, ua_id] from layout_ids
            lang_codes = ["en", "ua"]
            for klid, lang in zip(windows_ids, lang_codes):
                self._klid_to_lang[klid] = lang
                self._lang_to_mapping[lang] = f"{lang}_to_{self._other_lang(lang)}"

    @staticmethod
    def _other_lang(lang: str) -> str:
        return "ua" if lang == "en" else "en"

    @staticmethod
    def _should_convert(text: str, old_lang: str, new_lang: str) -> bool:
        """Heuristic: should we convert this text?

        Only converts when text looks like it was typed in the wrong layout:
        - EN->UA: convert if text has NO Cyrillic characters
        - UA->EN: convert if text HAS Cyrillic characters
        - Otherwise skip to avoid false triggers
        """
        contains_cyrillic = any(
            "\u0400" <= c <= "\u04FF" or "\u0500" <= c <= "\u052F"
            for c in text
        )

        if new_lang == "ua":
            return not contains_cyrillic
        elif new_lang == "en":
            return contains_cyrillic
        return False

    def _on_layout_change(self, old_layout_id: str, new_layout_id: str) -> None:
        """Called when the system layout changes."""
        if not self._enabled:
            return

        old_lang = self._klid_to_lang.get(old_layout_id)
        new_lang = self._klid_to_lang.get(new_layout_id)

        if old_lang is None or new_lang is None:
            logger.debug("Unrecognized layout change: %s -> %s", old_layout_id, new_layout_id)
            return

        if old_lang == new_lang:
            return  # same language

        logger.info("Layout change: %s -> %s", old_lang, new_lang)

        try:
            # Convert: selected text was typed in old_lang,
            # now needs to be transformed to new_lang
            mapping_name = f"{old_lang}_to_{new_lang}"

            selected = self._backend.get_selected_text()
            if not selected:
                logger.debug("No text selected - nothing to convert")
                return

            # Heuristic: only convert if the text actually needs conversion
            # EN->UA: skip if text contains Cyrillic (already Ukrainian)
            # UA->EN: skip if text is only ASCII (already English)
            if not self._should_convert(selected, old_lang, new_lang):
                logger.debug("Skipping: text doesn't look like '%s' input", old_lang)
                return

            logger.debug("Selected text: '%s'", selected)

            converted = self._converter.convert(
                selected, self._layout_id, mapping_name,
            )

            logger.debug("Converted: '%s'", converted)

            self._backend.replace_selected_text(converted)

        except Exception as e:
            logger.exception("Auto-conversion error: %s", e)