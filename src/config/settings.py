"""
Settings module — load/save user configuration.

Supports nested typed dataclasses with hotkey normalization.
Settings are stored in a user-specific path (APPDATA / XDG config).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# --- hotkey validation & normalization ---

HOTKEY_PATTERN = re.compile(
    r"^(ctrl|alt|shift|win)(\+(ctrl|alt|shift|win))*\+[a-z0-9]$"
)

MOD_ALIASES = {
    "cmd": "win",
    "meta": "win",
    "super": "win",
    "control": "ctrl",
}
"""Cross-platform modifier aliases: macOS cmd/meta → win, Linux super → win."""


def normalize_hotkey(raw: str) -> str:
    """Normalize a hotkey string to canonical form.

    'SHIFT+CTRL+K' -> 'ctrl+shift+k'
    'cmd+shift+k'  -> 'ctrl+shift+k'  (via MOD_ALIASES)
    Raises ValueError if format is invalid.
    """
    raw_stripped = raw.strip().lower()
    parts = raw_stripped.split("+")
    if len(parts) < 2:
        raise ValueError(f"Hotkey must have modifier(s) and a key: {raw!r}")

    valid_mods = {"ctrl", "alt", "shift", "win"}
    mods = sorted(
        MOD_ALIASES.get(p, p) for p in parts[:-1]
        if MOD_ALIASES.get(p, p) in valid_mods
    )
    if not mods:
        raise ValueError(f"No valid modifiers found in {raw!r}")
    key = parts[-1]
    result = "+".join(mods + [key])
    if not HOTKEY_PATTERN.match(result):
        raise ValueError(
            f"Invalid hotkey format: '{raw}'. "
            "Expected like 'ctrl+shift+k', modifiers: ctrl/alt/shift/win"
        )
    return result


def _coerce_bool(value: Any, default: bool) -> bool:
    """Convert various types to bool safely."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return default


# --- user config path ---


def _get_user_config_dir() -> str:
    """Platform-appropriate user config directory.

    Override via KCR_CONFIG_DIR env var (useful for tests).
    Windows: %APPDATA%/KeyboardCharReplacement
    Linux:   $XDG_CONFIG_HOME or ~/.config/KeyboardCharReplacement
    macOS:   ~/Library/Application Support/KeyboardCharReplacement
    """
    override = os.environ.get("KCR_CONFIG_DIR")
    if override:
        return override
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", "")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get(
            "XDG_CONFIG_HOME", os.path.expanduser("~/.config")
        )
    return os.path.join(base, "KeyboardCharReplacement")
# --- dataclasses ---


@dataclass
class HotkeySettings:
    enabled: bool = True
    combination: str = "ctrl+shift+k"


@dataclass
class LayoutChangeSettings:
    enabled: bool = False


@dataclass
class TriggerSettings:
    hotkey: HotkeySettings = field(default_factory=HotkeySettings)
    layout_change: LayoutChangeSettings = field(
        default_factory=LayoutChangeSettings
    )


@dataclass
class ConversionSettings:
    active_layouts: list[str] = field(default_factory=lambda: ["en_ua"])


@dataclass
class AutostartSettings:
    enabled: bool = False


@dataclass
class LoggingSettings:
    level: str = "INFO"


@dataclass
class AppSettings:
    """Application settings with typed nested groups."""

    version: str = "1.0"
    triggers: TriggerSettings = field(default_factory=TriggerSettings)
    conversion: ConversionSettings = field(
        default_factory=ConversionSettings
    )
    autostart: AutostartSettings = field(default_factory=AutostartSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)

    # computed properties

    @property
    def hotkey_combination(self) -> str:
        return self.triggers.hotkey.combination

    @property
    def is_hotkey_enabled(self) -> bool:
        return self.triggers.hotkey.enabled

    @property
    def is_auto_enabled(self) -> bool:
        return self.triggers.layout_change.enabled

    @property
    def is_autostart_enabled(self) -> bool:
        return self.autostart.enabled

    # load / save

    @classmethod
    def default(cls) -> "AppSettings":
        return cls()

    @classmethod
    def load(cls, path: Optional[str] = None) -> "AppSettings":
        """Load settings from JSON file.

        Returns defaults with logging if the file is missing or corrupt.
        """
        path = path or cls._resolve_path()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.info("No settings at %s, using defaults", path)
            return cls.default()
        except json.JSONDecodeError as e:
            logger.error(
                "Invalid JSON in %s (line %d): %s. Using defaults.",
                path, e.lineno, e.msg,
            )
            return cls.default()
        except OSError as e:
            logger.error("Cannot read %s: %s. Using defaults.", path, e)
            return cls.default()

        try:
            return cls._from_dict(data)
        except (TypeError, KeyError, ValueError) as e:
            logger.error(
                "Invalid structure in %s: %s. Using defaults.", path, e
            )
            return cls.default()

    def save(self, path: Optional[str] = None) -> bool:
        """Save settings to JSON file (user config dir by default).

        Uses atomic write: writes to temp file, then renames.
        Returns True on success, False on failure.
        """
        path = path or self._user_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                dir=os.path.dirname(path), suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(
                        self._to_dict(), f, indent=2, ensure_ascii=False,
                    )
                os.replace(tmp, path)
                return True
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except (OSError, TypeError) as e:
            logger.error("Failed to save settings to %s: %s", path, e)
            return False

    def set_hotkey(self, raw: str) -> str:
        """Set and normalize the hotkey combination."""
        normalized = normalize_hotkey(raw)
        self.triggers.hotkey.combination = normalized
        return normalized

    # internal

    @classmethod
    def _from_dict(cls, data: dict) -> "AppSettings":
        settings = cls.default()
        if "version" in data:
            settings.version = str(data["version"])

        triggers = data.get("triggers", {})
        if isinstance(triggers, dict):
            hotkey = triggers.get("hotkey", {})
            if isinstance(hotkey, dict):
                settings.triggers.hotkey.enabled = _coerce_bool(
                    hotkey.get("enabled"), True
                )
                if "combination" in hotkey:
                    try:
                        settings.triggers.hotkey.combination = (
                            normalize_hotkey(str(hotkey["combination"]))
                        )
                    except ValueError as e:
                        logger.warning("Invalid hotkey in settings: %s", e)

            lc = triggers.get("layout_change", {})
            if isinstance(lc, dict):
                settings.triggers.layout_change.enabled = _coerce_bool(
                    lc.get("enabled"), False
                )

        conversion = data.get("conversion", {})
        if isinstance(conversion, dict) and "active_layouts" in conversion:
            layouts = conversion["active_layouts"]
            if isinstance(layouts, list):
                settings.conversion.active_layouts = [
                    str(x) for x in layouts if isinstance(x, str)
                ]

        autostart = data.get("autostart", {})
        if isinstance(autostart, dict):
            settings.autostart.enabled = _coerce_bool(
                autostart.get("enabled"), False
            )

        logging_cfg = data.get("logging", {})
        if isinstance(logging_cfg, dict) and "level" in logging_cfg:
            settings.logging.level = str(logging_cfg["level"]).upper()

        return settings

    def _to_dict(self) -> dict:
        """Serialize to a JSON-serializable dict."""
        return {
            "version": self.version,
            "triggers": {
                "hotkey": {
                    "enabled": self.triggers.hotkey.enabled,
                    "combination": self.triggers.hotkey.combination,
                },
                "layout_change": {
                    "enabled": self.triggers.layout_change.enabled,
                },
            },
            "conversion": {
                "active_layouts": self.conversion.active_layouts,
            },
            "autostart": {
                "enabled": self.autostart.enabled,
            },
            "logging": {
                "level": self.logging.level,
            },
        }

    @classmethod
    def _resolve_path(cls) -> str:
        """Resolve settings path: user dir first, legacy repo dir fallback."""
        user_path = cls._user_path()
        if os.path.exists(user_path):
            return user_path
        legacy = _legacy_path()
        if os.path.exists(legacy):
            logger.info("Using legacy settings from %s", legacy)
            return legacy
        return user_path

    @staticmethod
    def _user_path() -> str:
        return os.path.join(_get_user_config_dir(), "settings.json")


def _legacy_path() -> str:
    """Path in the repo directory (for migration fallback)."""
    return str(Path(__file__).resolve().parents[2] / "config" / "settings.json")