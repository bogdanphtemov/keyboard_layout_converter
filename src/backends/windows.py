"""
Windows implementation of PlatformBackend.

Uses:
- ctypes for Win32 system APIs
- 'keyboard' for global hotkeys
- 'pyperclip' for clipboard operations
- Polling GetKeyboardLayout for layout change detection
- Windows Registry for autostart
"""

import ctypes
import ctypes.wintypes
import logging
import sys
import threading
import time
import winreg
from typing import Callable, Optional

import keyboard
import pyperclip

from src.backends.base import (
    PlatformBackend, Hotkey, Subscription, Capability,
)

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.GetKeyboardLayout.argtypes = [ctypes.wintypes.DWORD]
user32.GetKeyboardLayout.restype = ctypes.wintypes.HKL

user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
user32.GetForegroundWindow.argtypes = []

user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.POINTER(ctypes.wintypes.DWORD),
]

user32.LoadKeyboardLayoutW.restype = ctypes.wintypes.HKL
user32.LoadKeyboardLayoutW.argtypes = [
    ctypes.wintypes.LPCWSTR,
    ctypes.wintypes.UINT,
]

user32.ActivateKeyboardLayout.restype = ctypes.wintypes.HKL
user32.ActivateKeyboardLayout.argtypes = [
    ctypes.wintypes.HKL,
    ctypes.wintypes.UINT,
]

user32.PostMessageW.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]
user32.PostMessageW.restype = ctypes.wintypes.BOOL


def _get_keyboard_layout_id() -> str:
    """Returns current keyboard KLID (e.g. '00000409')."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        # Fallback: current thread's layout
        tid = kernel32.GetCurrentThreadId()
    else:
        tid = user32.GetWindowThreadProcessId(hwnd, None)
    hkl = user32.GetKeyboardLayout(tid)
    klid = (hkl & 0xFFFF)
    # Return only the KLID (low 16 bits) as 8-digit hex
    return f"{klid:08X}"


def _retry_clipboard_read(max_attempts: int = 3, delay: float = 0.05) -> str:
    """Read clipboard with retry logic. Returns content or empty string."""
    for attempt in range(max_attempts):
        try:
            text = pyperclip.paste()
            if text:
                return text
        except Exception:
            pass
        if attempt < max_attempts - 1:
            time.sleep(delay)
    return ""


def _clear_clipboard() -> None:
    """Set clipboard to empty string to detect 'nothing selected'."""
    try:
        pyperclip.copy("")
    except Exception as e:
        logger.debug("Failed to clear clipboard: %s", e)


class _Subscription:
    """Simple subscription handle for internal use."""

    def __init__(self, cleanup: Callable[[], None]):
        self._cleanup = cleanup
        self._unsubscribed = False

    def unsubscribe(self) -> None:
        if not self._unsubscribed:
            self._unsubscribed = True
            self._cleanup()


class WindowsBackend(PlatformBackend):
    """PlatformBackend implementation for Windows."""

    def __init__(self):
        self._hotkey_registrations: dict[str, _Subscription] = {}
        self._layout_change_callbacks: list[Callable[[str, str], None]] = []
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._current_layout: Optional[str] = None

    # layouts

    def get_current_layout_id(self) -> Optional[str]:
        try:
            return _get_keyboard_layout_id()
        except Exception as e:
            logger.debug("get_current_layout_id failed: %s", e)
            return None

    def get_available_layouts(self) -> list[str]:
        layouts = []
        key_path = r"SYSTEM\CurrentControlSet\Control\Keyboard Layouts"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        layouts.append(subkey_name)
                        i += 1
                    except OSError:
                        break
        except OSError:
            pass
        return layouts

    def switch_layout(self, layout_id: str) -> bool:
        try:
            hkl = user32.LoadKeyboardLayoutW(layout_id, 0x0001)
            if not hkl:
                logger.warning("LoadKeyboardLayoutW failed for %s", layout_id)
                return False
            hwnd = user32.GetForegroundWindow()
            result = user32.PostMessageW(hwnd, 0x0050, 0, hkl)
            if not result:
                logger.warning("PostMessageW failed for layout %s", layout_id)
                return False
            return True
        except Exception as e:
            logger.exception("switch_layout failed: %s", e)
            return False

    def get_layout_name(self, layout_id: str) -> str:
        key_path = rf"SYSTEM\CurrentControlSet\Control\Keyboard Layouts\{layout_id}"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                name, _ = winreg.QueryValueEx(key, "Layout Text")
                return name
        except OSError:
            return layout_id

    # events

    def on_layout_change(
        self, callback: Callable[[str, str], None]
    ) -> Subscription:
        self._layout_change_callbacks.append(callback)

        def cleanup():
            try:
                self._layout_change_callbacks.remove(callback)
            except ValueError:
                pass

        return _Subscription(cleanup)

    def register_hotkey(
        self, hotkey: Hotkey, callback: Callable[[], None]
    ) -> Subscription:
        native = str(hotkey)
        if native in self._hotkey_registrations:
            raise ValueError(f"Hotkey {native} already registered")
        try:
            keyboard.add_hotkey(native, callback)
        except Exception as e:
            logger.exception("Failed to register hotkey %s", native)
            raise RuntimeError(f"Failed to register hotkey {native}") from e

        sub = _Subscription(
            cleanup=lambda: keyboard.remove_hotkey(native)
        )
        self._hotkey_registrations[native] = sub
        return sub

    def start_event_loop(self) -> None:
        self._running = True
        self._current_layout = self.get_current_layout_id()
        self._start_polling()

    def stop_event_loop(self) -> None:
        self._running = False
        for native, sub in list(self._hotkey_registrations.items()):
            sub.unsubscribe()
        self._hotkey_registrations.clear()

    # clipboard

    def get_selected_text(self) -> str:
        """Copies selected text: clear clipboard, Ctrl+C, read result."""
        old_clipboard = _retry_clipboard_read()
        _clear_clipboard()

        keyboard.send("ctrl+c")

        # Poll for clipboard change or timeout (300ms)
        deadline = time.monotonic() + 0.3
        text = ""
        while time.monotonic() < deadline:
            text = _retry_clipboard_read(max_attempts=1, delay=0)
            if text:
                break
            time.sleep(0.01)

        pyperclip.copy(old_clipboard)
        return text

    def replace_selected_text(self, text: str) -> bool:
        try:
            old_clipboard = _retry_clipboard_read()
            pyperclip.copy(text)
            keyboard.send("ctrl+v")
            # Wait longer — target app must read clipboard before we restore
            time.sleep(0.15)
            pyperclip.copy(old_clipboard)
            return True
        except Exception as e:
            logger.exception("replace_selected_text failed: %s", e)
            return False

    # autostart

    def set_autostart(
        self, enabled: bool, command: Optional[str] = None
    ) -> bool:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "KeyboardCharacterReplacement"

        if command is None:
            cmd_parts = [sys.executable]
            if not getattr(sys, "frozen", False):
                import os as _os
                script = _os.path.abspath(sys.argv[0])
                cmd_parts.append(script)
            command = " ".join(f'"{p}"' for p in cmd_parts)

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
            ) as key:
                if enabled:
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)
                else:
                    try:
                        winreg.DeleteValue(key, app_name)
                    except OSError:
                        pass
            return True
        except OSError as e:
            logger.warning("set_autostart failed: %s", e)
            return False

    def is_autostart_enabled(self) -> bool:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "KeyboardCharacterReplacement"

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ
            ) as key:
                winreg.QueryValueEx(key, app_name)
                return True
        except OSError:
            return False

    # capabilities

    def supports(self, capability: Capability) -> bool:
        return capability in {
            Capability.LAYOUT_CHANGE,
            Capability.HOTKEY,
            Capability.AUTOSTART,
        }

    # internal

    def _start_polling(self) -> None:
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._poll_thread = threading.Thread(
            target=self._poll_layout_loop, daemon=True,
        )
        self._poll_thread.start()

    def _poll_layout_loop(self) -> None:
        """Polling loop for the current layout (every 500ms)."""
        while self._running:
            current = self.get_current_layout_id()
            if current is None:
                time.sleep(0.5)
                continue
            if current != self._current_layout:
                old = self._current_layout
                self._current_layout = current
                if old is not None:
                    for cb in list(self._layout_change_callbacks):
                        try:
                            cb(old, current)
                        except Exception:
                            logger.exception("Layout change callback failed")
            time.sleep(0.5)