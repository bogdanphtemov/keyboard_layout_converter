"""
Utility for managing program autostart.

Windows : HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run registry key
Linux   : ~/.config/autostart/ (desktop file)
macOS   : ~/Library/LaunchAgents/ (plist)
"""

import os
import sys
from typing import Optional

# ── Windows ─────────────────────────────────────────────────────


def _enable_windows(app_name: str, exe_path: str) -> None:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)


def _disable_windows(app_name: str) -> None:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
    ) as key:
        try:
            winreg.DeleteValue(key, app_name)
        except OSError:
            pass


def _is_enabled_windows(app_name: str) -> bool:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ
        ) as key:
            winreg.QueryValueEx(key, app_name)
            return True
    except OSError:
        return False


# public API


def enable_autostart(app_name: str = "KeyboardCharacterReplacement",
                     exe_path: Optional[str] = None) -> None:
    """Adds the program to autostart."""
    if exe_path is None:
        exe_path = sys.executable
    system = sys.platform
    if system == "win32":
        _enable_windows(app_name, exe_path)
    elif system == "linux":
        _create_linux_autostart(app_name, exe_path)
    elif system == "darwin":
        _create_macos_launchd(app_name, exe_path)


def disable_autostart(app_name: str = "KeyboardCharacterReplacement") -> None:
    """Removes the program from autostart."""
    system = sys.platform
    if system == "win32":
        _disable_windows(app_name)
    elif system == "linux":
        _remove_linux_autostart(app_name)
    elif system == "darwin":
        _remove_macos_launchd(app_name)


def is_autostart_enabled(app_name: str = "KeyboardCharacterReplacement") -> bool:
    """Checks if the program is in autostart."""
    system = sys.platform
    if system == "win32":
        return _is_enabled_windows(app_name)
    elif system == "linux":
        return _check_linux_autostart(app_name)
    elif system == "darwin":
        return _check_macos_launchd(app_name)
    return False


# ── Linux ───────────────────────────────────────────────────────


def _create_linux_autostart(app_name: str, exe_path: str) -> None:
    autostart_dir = os.path.expanduser("~/.config/autostart")
    os.makedirs(autostart_dir, exist_ok=True)
    desktop_file = os.path.join(autostart_dir, f"{app_name}.desktop")
    content = (
        "[Desktop Entry]\n"
        f"Name={app_name}\n"
        "Type=Application\n"
        f"Exec={exe_path}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    with open(desktop_file, "w", encoding="utf-8") as f:
        f.write(content)


def _remove_linux_autostart(app_name: str) -> None:
    desktop_file = os.path.expanduser(f"~/.config/autostart/{app_name}.desktop")
    if os.path.exists(desktop_file):
        os.remove(desktop_file)


def _check_linux_autostart(app_name: str) -> bool:
    return os.path.exists(os.path.expanduser(f"~/.config/autostart/{app_name}.desktop"))


# ── macOS ───────────────────────────────────────────────────────


def _create_macos_launchd(app_name: str, exe_path: str) -> None:
    launchd_dir = os.path.expanduser("~/Library/LaunchAgents")
    os.makedirs(launchd_dir, exist_ok=True)
    plist_file = os.path.join(launchd_dir, f"com.{app_name}.plist")
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>com.{app_name}</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"        <string>{exe_path}</string>\n"
        "    </array>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "    <key>KeepAlive</key>\n"
        "    <true/>\n"
        "</dict>\n"
        "</plist>\n"
    )
    with open(plist_file, "w", encoding="utf-8") as f:
        f.write(content)


def _remove_macos_launchd(app_name: str) -> None:
    plist_file = os.path.expanduser(f"~/Library/LaunchAgents/com.{app_name}.plist")
    if os.path.exists(plist_file):
        os.remove(plist_file)


def _check_macos_launchd(app_name: str) -> bool:
    return os.path.exists(
        os.path.expanduser(f"~/Library/LaunchAgents/com.{app_name}.plist")
    )