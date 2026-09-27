"""
Abstract base class for platform-dependent implementations.

Each platform (Windows, Linux, macOS) implements these methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Protocol, runtime_checkable

__all__ = [
    "PlatformBackend",
    "Hotkey",
    "Subscription",
    "Capability",
]


# --- Supporting types ---


# Valid modifiers for hotkey combinations
VALID_MODIFIERS = frozenset({"ctrl", "alt", "shift", "win", "cmd", "meta"})


@dataclass(frozen=True)
class Hotkey:
    """Structured hotkey representation.

    Use Hotkey.parse('ctrl+shift+k') to construct from string.
    Each backend maps this to its own native format.
    """
    modifiers: frozenset[str]
    key: str

    @classmethod
    def parse(cls, raw: str) -> "Hotkey":
        """Parse a hotkey string like 'ctrl+shift+k' into a structured object.

        Raises ValueError on invalid format (empty key, unknown modifier).
        """
        parts = raw.lower().replace(" ", "").split("+")
        if len(parts) < 2 or not parts[-1]:
            raise ValueError(
                f"Hotkey must have at least one modifier and a key: {raw!r}"
            )
        modifiers = frozenset(parts[:-1])
        unknown = modifiers - VALID_MODIFIERS
        if unknown:
            raise ValueError(f"Unknown modifiers: {sorted(unknown)}")
        return cls(modifiers=modifiers, key=parts[-1])

    def __str__(self) -> str:
        return "+".join(sorted(self.modifiers) + [self.key])


@runtime_checkable
class Subscription(Protocol):
    """Handle returned when registering a callback.

    Call unsubscribe() to remove the listener / hotkey.
    """
    def unsubscribe(self) -> None: ...


class Capability(Enum):
    """Features that a backend may or may not support."""
    LAYOUT_CHANGE = "layout_change"
    HOTKEY = "hotkey"
    AUTOSTART = "autostart"
    UNICODE_INPUT = "unicode_input"


# --- Interface ---


class PlatformBackend(ABC):
    """Interface for interacting with the system regardless of OS."""

    # --- layouts ---

    @abstractmethod
    def get_current_layout_id(self) -> Optional[str]:
        """Returns current layout ID (e.g. '00000409'), or None on failure."""

    @abstractmethod
    def get_available_layouts(self) -> list[str]:
        """List of all installed layout IDs."""

    @abstractmethod
    def switch_layout(self, layout_id: str) -> bool:
        """Switches system layout. Returns True on success."""

    @abstractmethod
    def get_layout_name(self, layout_id: str) -> str:
        """Human-readable layout name (e.g. 'English')."""

    # --- events ---

    @abstractmethod
    def on_layout_change(
        self, callback: Callable[[str, str], None]
    ) -> Subscription:
        """Register a layout-change listener.

        Callback receives (old_layout_id, new_layout_id).
        Only fires when both IDs are known and different.
        Returns Subscription; call .unsubscribe() to stop listening.
        """

    @abstractmethod
    def register_hotkey(
        self, hotkey: Hotkey, callback: Callable[[], None]
    ) -> Subscription:
        """Register a global hotkey. Returns a Subscription handle.

        Call .unsubscribe() to unregister the hotkey.
        """

    @abstractmethod
    def start_event_loop(self) -> None:
        """Start the platform event loop. Blocks until stop_event_loop()."""

    @abstractmethod
    def stop_event_loop(self) -> None:
        """Stop the event loop started by start_event_loop()."""

    # --- text I/O ---

    @abstractmethod
    def get_selected_text(self) -> str:
        """Copy selected text from the active window.

        Simulates Ctrl+C, reads clipboard, returns string.
        Returns empty string if nothing is selected.
        Should preserve/restore the user's clipboard content.
        """

    @abstractmethod
    def replace_selected_text(self, text: str) -> bool:
        """Replace selection with `text`. Returns True on success.

        Copies text to clipboard, simulates Ctrl+V.
        Preserves the user's clipboard content.
        """

    # --- autostart ---

    @abstractmethod
    def set_autostart(
        self, enabled: bool, command: Optional[str] = None
    ) -> bool:
        """Add/remove program from autostart. Returns True on success.

        Args:
            enabled: True to add, False to remove.
            command: Full command to run. If None, uses sys.executable.
        """

    @abstractmethod
    def is_autostart_enabled(self) -> bool:
        """Check if program is in autostart."""

    # --- capabilities ---

    @abstractmethod
    def supports(self, capability: Capability) -> bool:
        """Whether this backend supports the given feature."""