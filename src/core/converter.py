"""
Module for converting characters between keyboard layouts.

Usage:
    converter = TextConverter(config)

    # Explicit direction
    result = converter.convert("ghbdsn", "en_ua", "en_to_ua")
    # -> "привіт"

    # Auto-detect direction by content
    result = converter.convert_auto("ghbdsn", "en_ua")
    # -> "привіт" (text is Latin -> convert to Cyrillic)

    # Auto-detect direction by current system layout
    result = converter.convert_auto("ghbdsn", "en_ua", current_layout_id="00000422")
    # -> "привіт" (system is UA -> convert en_to_ua)
"""

from __future__ import annotations

import logging

from src.core.layout_loader import LayoutConfig

logger = logging.getLogger(__name__)

# Unicode ranges for language detection
CYRILLIC_RANGE = range(0x0400, 0x04FF + 1)


class TextConverter:
    """Converts text between layouts using mappings from config."""

    def __init__(self, config: LayoutConfig):
        self._config = config

    # public API

    def convert(
        self, text: str, layout_id: str, mapping_name: str
    ) -> str:
        """Convert text according to the specified mapping.

        Args:
            text: input string
            layout_id: layout identifier (e.g. 'en_ua')
            mapping_name: mapping direction (e.g. 'en_to_ua')

        Returns:
            Converted string, or input unchanged if mapping is missing.
        """
        try:
            mapping = self._config.get_mapping(layout_id, mapping_name)
        except (KeyError, ValueError) as e:
            logger.warning(
                "No mapping %s/%s: %s. Returning text unchanged.",
                layout_id, mapping_name, e,
            )
            return text

        if not mapping:
            logger.warning("Empty mapping %s/%s", layout_id, mapping_name)
            return text

        logger.debug(
            "Converting %r with %s/%s", text[:50], layout_id, mapping_name,
        )
        result = self._apply_mapping(text, mapping)
        logger.debug("Result: %r", result[:50])
        return result

    def convert_auto(
        self,
        text: str,
        layout_id: str,
        current_layout_id: str | None = None,
    ) -> str:
        """Auto-detect direction and convert.

        Detection priority:
            1. Content-based detection — analyzes the text characters.
               If text is mostly Latin → convert to Cyrillic (en_to_ua).
               If text is mostly Cyrillic → convert to Latin (ua_to_en).
               Skips mixed text (ratio < 70%) to avoid false conversions.
            2. Layout-based fallback — uses the current system layout
               to guess the direction (less reliable).

        Args:
            text: input string
            layout_id: layout pair identifier (e.g. 'en_ua')
            current_layout_id: current system layout KLID (e.g. '00000409').
                               Used as fallback when content is ambiguous.

        Returns:
            Converted string, or input unchanged if direction is unknown.
        """
        direction = self._detect_direction(text, layout_id, current_layout_id)
        if direction is None:
            logger.warning(
                "Cannot detect direction for %r in %s",
                text[:50], layout_id,
            )
            return text

        logger.debug("Auto-detected direction: %s", direction)
        return self.convert(text, layout_id, direction)

    # direction detection

    def _detect_direction(
        self,
        text: str,
        layout_id: str,
        current_layout_id: str | None,
    ) -> str | None:
        """Detect conversion direction.

        Priority:
            1. Content-based — analyze text characters (most reliable).
            2. Layout-based — use current system layout as fallback.
        """
        direction = self._detect_by_content(text, layout_id)
        if direction is not None:
            return direction

        if current_layout_id is not None:
            return self._detect_by_layout(layout_id, current_layout_id)

        return None

    def _detect_by_layout(
        self, layout_id: str, current_layout_id: str
    ) -> str | None:
        """Detect direction using the current system layout.

        The user is now in `current_layout_id`. They probably just switched
        to this layout, meaning the selected text was typed in the OTHER layout.
        So we convert FROM the other layout TO the current one.
        """
        try:
            ids = self._config.get_layout_ids(layout_id, "windows")
        except (KeyError, ValueError):
            return None

        if len(ids) < 2:
            return None

        parts = layout_id.split("_")
        if len(parts) != 2:
            return None
        lang_a, lang_b = parts[0], parts[1]

        if current_layout_id == ids[0]:
            # System is now in first language -> convert second_to_first
            return f"{lang_b}_to_{lang_a}"
        if current_layout_id == ids[1]:
            # System is now in second language -> convert first_to_second
            return f"{lang_a}_to_{lang_b}"
        return None

    def _detect_by_content(self, text: str, layout_id: str) -> str | None:
        """Guess direction from text content.

        Only converts when one language strongly dominates (>= 70%).
        Skips mixed text to avoid false conversions.

        If text is mostly Cyrillic -> user wanted Latin (ua_to_en).
        If text is mostly Latin -> user wanted Cyrillic (en_to_ua).
        """
        if not text:
            return None

        cyrillic = sum(1 for c in text if ord(c) in CYRILLIC_RANGE)
        latin = sum(1 for c in text if c.isascii() and c.isalpha())
        total = cyrillic + latin

        if total == 0:
            return None

        # Mixed text is ambiguous — skip
        ratio = max(cyrillic, latin) / total
        if ratio < 0.7:
            logger.debug(
                "Mixed text (cyrillic=%d, latin=%d, ratio=%.2f),"
                " skipping content-based detection",
                cyrillic, latin, ratio,
            )
            return None

        parts = layout_id.split("_")
        if len(parts) != 2:
            return None
        lang_a, lang_b = parts[0], parts[1]

        if cyrillic > latin:
            return f"{lang_b}_to_{lang_a}"
        return f"{lang_a}_to_{lang_b}"

    @staticmethod
    def _apply_mapping(text: str, mapping: dict[str, str]) -> str:
        """Replace characters in a string according to the mapping.

        Characters not in the mapping are left unchanged.
        """
        return "".join(mapping.get(c, c) for c in text)