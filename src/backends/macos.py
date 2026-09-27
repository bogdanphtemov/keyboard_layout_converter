"""
Stub for macOS. Will be implemented later.
"""

from typing import Optional

from src.backends.base import (
    PlatformBackend, Hotkey, Subscription, Capability,
)


class MacBackend(PlatformBackend):
    """macOS implementation — stub."""

    def get_current_layout_id(self) -> Optional[str]:
        return "com.apple.keylayout.US"

    def get_available_layouts(self) -> list[str]:
        return ["com.apple.keylayout.US"]

    def switch_layout(self, layout_id: str) -> bool:
        return False

    def get_layout_name(self, layout_id: str) -> str:
        return layout_id

    def on_layout_change(self, callback) -> Subscription:
        return _FakeSubscription()

    def register_hotkey(self, hotkey: Hotkey, callback) -> Subscription:
        return _FakeSubscription()

    def start_event_loop(self) -> None:
        pass

    def stop_event_loop(self) -> None:
        pass

    def get_selected_text(self) -> str:
        return ""

    def replace_selected_text(self, text: str) -> bool:
        return False

    def set_autostart(self, enabled: bool, command: Optional[str] = None) -> bool:
        return False

    def is_autostart_enabled(self) -> bool:
        return False

    def supports(self, capability: Capability) -> bool:
        return False


class _FakeSubscription:
    def unsubscribe(self) -> None:
        pass