"""
Cross-platform clipboard utility.

Wraps pyperclip with additional features:
- save/restore original clipboard content
- work with selected text (Ctrl+C / Ctrl+V)
"""

import time
from typing import Optional

import pyperclip


class ClipboardManager:
    """Clipboard manager with automatic save/restore."""

    def __init__(self):
        self._saved: Optional[str] = None

    def save(self) -> None:
        """Saves current clipboard content."""
        try:
            self._saved = pyperclip.paste()
        except Exception:
            self._saved = None

    def restore(self) -> None:
        """Restores the saved clipboard content."""
        if self._saved is not None:
            try:
                pyperclip.copy(self._saved)
            except Exception:
                pass

    def get_text(self) -> str:
        """Reads text from clipboard."""
        return pyperclip.paste()

    def set_text(self, text: str) -> None:
        """Writes text to clipboard."""
        pyperclip.copy(text)

    def copy_selected(self, delay: float = 0.05) -> str:
        """Copies selected text via Ctrl+C.

        Args:
            delay: delay after Ctrl+C (seconds)

        Returns:
            text from clipboard
        """
        self.save()
        try:
            import keyboard
            keyboard.send("ctrl+c")
            time.sleep(delay)
            return self.get_text()
        finally:
            self.restore()

    def paste_text(self, text: str, delay: float = 0.05) -> None:
        """Pastes text via Ctrl+V.

        Args:
            text: text to paste
            delay: delay after Ctrl+V (seconds)
        """
        self.save()
        try:
            self.set_text(text)
            import keyboard
            keyboard.send("ctrl+v")
            time.sleep(delay)
        finally:
            self.restore()