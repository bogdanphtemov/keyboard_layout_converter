"""
Module for loading layout configuration from JSON.

To add a new layout = simply add an object to config/layouts.json
Use "_invert" as the mapping value to auto-generate the reverse mapping.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

INVERT_MARKER = "_invert"


def _invert_mapping(mapping: dict[str, str]) -> dict[str, str]:
    """Invert {from: to} -> {to: from}. Raises on non-bijective input."""
    inverted: dict[str, str] = {}
    for k, v in mapping.items():
        if v in inverted:
            raise ValueError(
                f"Cannot invert mapping: duplicate value '{v}' "
                f"(from keys '{inverted[v]}' and '{k}')"
            )
        inverted[v] = k
    return inverted


def _find_source_name(
    mappings: dict, invert_name: str
) -> str | None:
    """Find source mapping to invert ('ua_to_en' -> 'en_to_ua')."""
    parts = invert_name.split("_to_")
    if len(parts) == 2:
        expected = f"{parts[1]}_to_{parts[0]}"
        if expected in mappings and isinstance(mappings[expected], dict):
            return expected
    return None


def _invert_source_name(mapping_name: str) -> str:
    """Given 'ua_to_en', return the expected source 'en_to_ua'."""
    parts = mapping_name.split("_to_")
    if len(parts) == 2:
        return f"{parts[1]}_to_{parts[0]}"
    return mapping_name


class LayoutConfig:
    """Stores all layouts from the configuration file."""

    def __init__(self, config_path: str | None = None):
        self._config_path = config_path or self._default_path()
        self._layouts: list[dict[str, Any]] = []
        self._load()

    # public

    @property
    def layouts(self) -> list[dict[str, Any]]:
        return list(self._layouts)

    def get_by_id(self, layout_id: str) -> dict[str, Any] | None:
        for layout in self._layouts:
            if layout["id"] == layout_id:
                return layout
        return None

    def get_active(
        self, active_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Returns layouts filtered by active_ids from settings.

        If active_ids is None, returns all layouts.
        """
        if active_ids is None:
            return list(self._layouts)
        return [l for l in self._layouts if l["id"] in active_ids]

    def get_mapping(
        self, layout_id: str, mapping_name: str
    ) -> dict[str, str]:
        """Get character mapping for a specific layout and direction.

        Raises ValueError if layout or mapping not found or invalid.
        """
        layout = self.get_by_id(layout_id)
        if layout is None:
            raise ValueError(f"Layout '{layout_id}' not found")
        mapping = layout["mappings"].get(mapping_name)
        if mapping is None:
            raise ValueError(
                f"Mapping '{mapping_name}' not found in layout '{layout_id}'"
            )
        if not isinstance(mapping, dict):
            raise ValueError(
                f"Mapping '{mapping_name}' in '{layout_id}' is not a dict "
                f"(got {type(mapping).__name__})"
            )
        return mapping

    def get_layout_ids(
        self, layout_id: str, platform: str = "windows"
    ) -> list[str]:
        """Get OS-specific layout IDs for a layout."""
        layout = self.get_by_id(layout_id)
        if layout is None:
            raise ValueError(f"Layout '{layout_id}' not found")
        return list(layout.get("layout_ids", {}).get(platform, []))

    def get_all_mappings(
        self, layout_id: str
    ) -> dict[str, dict[str, str]]:
        """All mappings for a layout (e.g. en_to_ua, ua_to_en)."""
        layout = self.get_by_id(layout_id)
        if layout is None:
            raise ValueError(f"Layout '{layout_id}' not found")
        return dict(layout["mappings"])

    # internal

    def _load(self) -> None:
        """Load and validate layouts from JSON config."""
        try:
            with open(self._config_path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Layout config not found: {self._config_path}"
            ) from None
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON in {self._config_path} "
                f"(line {e.lineno}): {e.msg}"
            ) from e

        if not isinstance(data, dict):
            raise ValueError(
                f"Layout config root must be an object, "
                f"got {type(data).__name__}"
            )

        layouts = data.get("layouts")
        if not isinstance(layouts, list):
            raise ValueError("'layouts' must be a list")

        self._validate(layouts)

        # Resolve _invert markers
        for layout in layouts:
            mappings = layout["mappings"]
            for name in list(mappings.keys()):
                if mappings[name] != INVERT_MARKER:
                    continue
                source_name = _find_source_name(mappings, name)
                if source_name is None:
                    raise ValueError(
                        f"Layout '{layout['id']}': mapping '{name}' uses "
                        f"'{INVERT_MARKER}' but no source mapping found. "
                        f"Expected '{_invert_source_name(name)}'."
                    )
                try:
                    mappings[name] = _invert_mapping(mappings[source_name])
                except ValueError as e:
                    raise ValueError(
                        f"Layout '{layout['id']}': {e}"
                    ) from e

        self._layouts = layouts

    @staticmethod
    def _validate(layouts: list) -> None:
        """Validate loaded layouts. Raises ValueError on first error."""
        seen_ids: set[str] = set()

        for idx, layout in enumerate(layouts):
            prefix = f"layouts[{idx}]"

            if not isinstance(layout, dict):
                raise ValueError(f"{prefix}: must be an object")

            layout_id = layout.get("id")
            if not isinstance(layout_id, str) or not layout_id:
                raise ValueError(f"{prefix}: 'id' must be a non-empty string")
            if layout_id in seen_ids:
                raise ValueError(f"Duplicate layout id: '{layout_id}'")
            seen_ids.add(layout_id)

            if not isinstance(layout.get("name"), str):
                raise ValueError(f"'{layout_id}': 'name' must be a string")

            mappings = layout.get("mappings")
            if not isinstance(mappings, dict) or not mappings:
                raise ValueError(
                    f"'{layout_id}': 'mappings' must be a non-empty object"
                )

            for m_name, m_value in mappings.items():
                if m_value == INVERT_MARKER:
                    continue
                if not isinstance(m_value, dict):
                    raise ValueError(
                        f"'{layout_id}.{m_name}': must be a dict "
                        f"or '{INVERT_MARKER}'"
                    )
                for k, v in m_value.items():
                    if not isinstance(k, str) or not isinstance(v, str):
                        raise ValueError(
                            f"'{layout_id}.{m_name}': "
                            f"keys and values must be strings"
                        )

            layout_ids = layout.get("layout_ids", {})
            if not isinstance(layout_ids, dict):
                raise ValueError(
                    f"'{layout_id}': 'layout_ids' must be an object"
                )

    @staticmethod
    def _default_path() -> str:
        """Get default path to config/layouts.json."""
        return str(
            Path(__file__).resolve().parents[2] / "config" / "layouts.json"
        )