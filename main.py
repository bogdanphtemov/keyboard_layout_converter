"""
Keyboard Character Replacement
==============================
Program for automatic character replacement when switching keyboard layout.

Method 1 (manual): Hotkey Ctrl+Shift+K -> converts selected text
Method 2 (auto): Automatically on Windows layout switch

Autostart: registers in registry HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

Usage:
    python main.py                          # both modes
    python main.py --mode manual            # manual mode only
    python main.py --mode auto              # auto mode only
    python main.py --setup                  # interactive setup menu
    python main.py --no-autostart           # without autostart
    python main.py --hotkey ctrl+shift+l    # custom hotkey
"""

import argparse
import logging
import logging.handlers
import os
import signal
import sys
import time
from typing import Optional

from src.core.converter import TextConverter
from src.core.layout_loader import LayoutConfig
from src.config.settings import AppSettings
from src.backends.factory import create_backend
from src.backends.base import PlatformBackend
from src.triggers.hotkey import HotkeyTrigger, DEFAULT_HOTKEY
from src.triggers.layout_watcher import LayoutWatcherTrigger
from src.utils.autostart import enable_autostart, disable_autostart

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# File logging (rotating, ~1MB per file, keep 3 backups)
# Log directory: platform-appropriate (not %TEMP%, which gets cleaned)
if sys.platform == "win32":
    _log_dir = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
elif sys.platform == "darwin":
    _log_dir = os.path.expanduser("~/Library/Logs")
else:
    _log_dir = os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state"))
_log_dir = os.path.join(_log_dir, "KeyboardCharReplacement", "logs")
os.makedirs(_log_dir, exist_ok=True)
_file_handler = logging.handlers.RotatingFileHandler(
    os.path.join(_log_dir, "app.log"),
    maxBytes=1_048_576,  # 1 MB
    backupCount=3,
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
logging.getLogger().addHandler(_file_handler)


def _acquire_single_instance_lock() -> bool:
    """Try to acquire a single-instance lock.

    Returns:
        True if this is the only instance, False otherwise.
    """
    global _lock_file
    _lock_file = os.path.join(_log_dir, "app.lock")
    try:
        fd = os.open(_lock_file, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.close(fd)
        return True
    except FileExistsError:
        logger.warning("Another instance is already running! Exiting.")
        return False
    except OSError:
        return True


def _release_single_instance_lock() -> None:
    """Remove the lock file if it exists."""
    global _lock_file
    try:
        if _lock_file and os.path.exists(_lock_file):
            os.unlink(_lock_file)
    except OSError:
        pass


_lock_file: str | None = None


class App:
    """Main application class."""

    def __init__(
        self,
        config_path: Optional[str] = None,
        hotkey: str = DEFAULT_HOTKEY,
        autostart: bool = False,
        mode: str = "both",
        settings: Optional[AppSettings] = None,
    ):
        self._config = LayoutConfig(config_path)
        logger.info("Loaded %d layout(s)", len(self._config.layouts))

        active = self._config.get_active(
            settings.conversion.active_layouts if settings else None)
        if not active:
            raise RuntimeError("No active layouts in config!")
        self._active_layout = active[0]
        logger.info("Active layout: %s", self._active_layout["name"])

        self._backend: PlatformBackend = create_backend()
        logger.info("Platform: %s", sys.platform)

        self._converter = TextConverter(self._config)
        self._settings = settings or AppSettings.load()
        self._mode = mode

        self._hotkey_trigger: Optional[HotkeyTrigger] = None
        self._layout_watcher: Optional[LayoutWatcherTrigger] = None

        if mode in ("manual", "both"):
            self._hotkey_trigger = HotkeyTrigger(
                backend=self._backend,
                converter=self._converter,
                layout_id=self._active_layout["id"],
                layout_ids_config=self._active_layout.get("layout_ids", {}),
                hotkey=hotkey,
            )
        if mode in ("auto", "both"):
            self._layout_watcher = LayoutWatcherTrigger(
                backend=self._backend,
                converter=self._converter,
                layout_id=self._active_layout["id"],
                layout_ids_config=self._active_layout.get("layout_ids", {}),
            )

        self._autostart = autostart

    def run(self) -> None:
        """Starts the application."""
        logger.info("Starting KeyboardCharacterReplacement...")

        if self._autostart:
            enable_autostart()
            logger.info("Autostart enabled")

        if self._hotkey_trigger:
            self._hotkey_trigger.enable()
            logger.info("Manual mode ON - hotkey: %s", self._settings.hotkey_combination)
        else:
            logger.info("Manual mode OFF")

        if self._layout_watcher:
            self._layout_watcher.enable()
            logger.info("Auto mode ON - Win+Space auto-convert")
        else:
            logger.info("Auto mode OFF")

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("Program is running in background...")
        self._backend.start_event_loop()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self._shutdown()

    def _signal_handler(self, signum, frame) -> None:
        logger.info("Received signal %s, shutting down...", signum)
        self._shutdown()

    def _shutdown(self) -> None:
        logger.info("Shutting down...")
        if self._hotkey_trigger:
            self._hotkey_trigger.disable()
        if self._layout_watcher:
            self._layout_watcher.disable()
        self._backend.stop_event_loop()
        _release_single_instance_lock()
        logger.info("Goodbye!")
        sys.exit(0)
def run_setup() -> None:
    """Interactive CLI setup menu."""
    settings = AppSettings.load()

    while True:
        print()
        print(" " * 3 + "Keyboard Character Replacement -- Setup")
        print(" " * 3 + "=" * 42)
        print()
        print(f"  [1] Hotkey mode (Ctrl+Shift+K)   : {'ON' if settings.is_hotkey_enabled else 'OFF'}")
        print(f"  [2] Auto mode (Win+Space)        : {'ON' if settings.is_auto_enabled else 'OFF'}")
        print(f"  [3] Autostart with Windows        : {'ON' if settings.is_autostart_enabled else 'OFF'}")
        print(f"  [4] Change hotkey                 : {settings.hotkey_combination}")
        print(f"  [5] Save & Exit")
        print(f"  [6] Exit without saving")
        print()

        choice = input("  Choose an option [1-6]: ").strip()

        if choice == "1":
            settings.triggers.hotkey.enabled = not settings.triggers.hotkey.enabled
            print(f"  -> Hotkey mode toggled to {'ON' if settings.triggers.hotkey.enabled else 'OFF'}")
        elif choice == "2":
            enabled = settings.triggers.layout_change.enabled
            settings.triggers.layout_change.enabled = not enabled
            print(f"  -> Auto mode toggled to {'ON' if settings.triggers.layout_change.enabled else 'OFF'}")
        elif choice == "3":
            enabled = settings.autostart.enabled
            settings.autostart.enabled = not enabled
            if settings.autostart.enabled:
                enable_autostart()
            else:
                disable_autostart()
            print(f"  -> Autostart toggled to {'ON' if settings.autostart.enabled else 'OFF'}")
        elif choice == "4":
            new_hk = input(f"  Enter new hotkey (current: {settings.hotkey_combination}): ").strip()
            if new_hk:
                try:
                    normalized = settings.set_hotkey(new_hk)
                    print(f"  -> Hotkey changed to: {normalized}")
                except ValueError as e:
                    print(f"  -> Error: {e}")
        elif choice == "5":
            settings.save()
            print("  -> Settings saved. Run without --setup to start.")
            break
        elif choice == "6":
            print("  -> Exiting without saving.")
            break
        else:
            print("  Invalid choice. Enter 1-6.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keyboard Character Replacement",
    )
    parser.add_argument("--setup", action="store_true", help="Open interactive setup")
    parser.add_argument(
        "--mode", type=str, choices=["manual", "auto", "both"], default=None,
        help="Conversion mode (manual=hotkey, auto=Win+Space, both=default)",
    )
    parser.add_argument("--no-autostart", action="store_true", help="Do not autostart")
    parser.add_argument(
        "--hotkey", type=str, default=None,
        help=f"Hotkey (default: {DEFAULT_HOTKEY})",
    )
    parser.add_argument("--config", type=str, default=None, help="Path to layouts JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.setup:
        run_setup()
        return

    # Single instance check (skip for setup)
    if not _acquire_single_instance_lock():
        sys.exit(1)

    settings = AppSettings.load()

    if args.mode:
        mode = args.mode
    elif settings.is_hotkey_enabled and settings.is_auto_enabled:
        mode = "both"
    elif settings.is_hotkey_enabled and not settings.is_auto_enabled:
        mode = "manual"
    elif not settings.is_hotkey_enabled and settings.is_auto_enabled:
        mode = "auto"
    else:
        mode = "both"

    hotkey = args.hotkey or settings.hotkey_combination
    autostart = not args.no_autostart if args.no_autostart else settings.is_autostart_enabled

    app = App(
        config_path=args.config,
        hotkey=hotkey,
        autostart=autostart,
        mode=mode,
        settings=settings,
    )
    app.run()


if __name__ == "__main__":
    main()