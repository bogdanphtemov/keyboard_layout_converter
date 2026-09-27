"""
Factory for creating a platform-dependent backend.
Automatically detects the OS and returns the appropriate instance.

Supports custom backend registration for testing (register_backend).
"""

import logging
import sys
from typing import Callable, Optional

from src.backends.base import PlatformBackend

logger = logging.getLogger(__name__)

__all__ = ["create_backend", "register_backend", "reset_registry"]

# Registry for custom backends (testing / plugins)
_REGISTRY: dict[str, Callable[[], PlatformBackend]] = {}


def register_backend(
    platform: str, factory: Callable[[], PlatformBackend]
) -> None:
    """Register a custom backend factory for a platform.

    Useful for testing with mock backends and future plugins.
    Overrides the default backend for the given platform name.
    """
    _REGISTRY[platform] = factory
    logger.debug("Registered backend for platform: %s", platform)


def reset_registry() -> None:
    """Clear the registry. Useful in tests for isolation."""
    _REGISTRY.clear()


def _default_windows() -> PlatformBackend:
    from src.backends.windows import WindowsBackend
    return WindowsBackend()


def _default_linux() -> PlatformBackend:
    from src.backends.linux import LinuxBackend
    return LinuxBackend()


def _default_macos() -> PlatformBackend:
    from src.backends.macos import MacBackend
    return MacBackend()


_DEFAULTS: dict[str, Callable[[], PlatformBackend]] = {
    "win32": _default_windows,
    "cygwin": _default_windows,
    "linux": _default_linux,
    "linux2": _default_linux,
    "darwin": _default_macos,
}


def create_backend(force: Optional[str] = None) -> PlatformBackend:
    """Create a backend for the current platform.

    Args:
        force: If set, forces a specific platform (e.g. 'win32', 'linux').
               Useful for testing. If None, auto-detects.

    Returns:
        A PlatformBackend instance.

    Raises:
        RuntimeError: If the platform is not supported.
    """
    system = force or sys.platform
    logger.debug("Creating backend for platform: %s", system)

    factory = _REGISTRY.get(system) or _DEFAULTS.get(system)
    if factory is None:
        raise RuntimeError(
            f"Unsupported platform: {system!r}. "
            f"Supported: {sorted(_DEFAULTS)}. "
            f"Use register_backend() to add a custom one."
        )

    backend = factory()
    logger.info("Loaded backend: %s", backend.__class__.__name__)
    return backend