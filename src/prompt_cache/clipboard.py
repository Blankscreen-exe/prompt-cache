"""OS clipboard access.

A thin wrapper over `pyperclip`, which already handles the Windows clipboard API,
Wayland (`wl-copy`/`wl-paste`), X11 (`xclip`/`xsel`), Klipper and WSL. This module adds
only what pyperclip does not: an actionable error message, BOM removal, and a guarantee
that a clipboard failure never propagates into the UI as a crash.
"""

from __future__ import annotations

import pyperclip

BOM = "﻿"

INSTALL_HINT = (
    "No clipboard tool found. On Linux install one of: wl-clipboard (Wayland), xclip or xsel (X11)."
)


class ClipboardUnavailable(RuntimeError):
    """No working clipboard backend, with a message worth showing the user."""


def _strip_bom(text: str) -> str:
    """Remove a leading byte-order mark.

    Text that has been through a PowerShell pipe can arrive with one, and it would
    otherwise end up silently pasted into the user's prompt.
    """
    return text[1:] if text.startswith(BOM) else text


def read_text() -> str:
    """The clipboard's text content, or raise `ClipboardUnavailable`."""
    try:
        return _strip_bom(pyperclip.paste() or "")
    except pyperclip.PyperclipException as exc:
        raise ClipboardUnavailable(INSTALL_HINT) from exc


def write_text(text: str) -> None:
    """Put `text` on the clipboard, or raise `ClipboardUnavailable`."""
    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException as exc:
        raise ClipboardUnavailable(INSTALL_HINT) from exc


def read_text_or_empty() -> str:
    """`read_text`, but an unavailable clipboard yields "" instead of raising.

    For pre-filling a field, where a missing clipboard should leave the field blank
    rather than interrupt the user.
    """
    try:
        return read_text()
    except ClipboardUnavailable:
        return ""


def is_available() -> bool:
    """Whether a clipboard backend exists. Never raises."""
    try:
        pyperclip.paste()
    except pyperclip.PyperclipException:
        return False
    except Exception:  # a broken backend must not crash a status check
        return False
    return True
