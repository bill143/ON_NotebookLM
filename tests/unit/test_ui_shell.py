"""Unit tests for nexus_ui_shell configuration and payloads."""

from __future__ import annotations

from src.core.nexus_ui_shell import (
    DEFAULT_COMMANDS,
    DEFAULT_SHORTCUTS,
    ERROR_BOUNDARIES,
    THEMES,
    CommandPaletteItem,
    KeyboardShortcut,
    Toast,
    UIShell,
    get_shell_config,
)


def test_keyboard_shortcut_to_dict() -> None:
    ks = KeyboardShortcut("x", ["ctrl"], "action", "Label", "general")
    d = ks.to_dict()
    assert d["key"] == "x"
    assert d["modifiers"] == ["ctrl"]
    assert d["display"] == "ctrl+X"


def test_command_palette_item_to_dict() -> None:
    item = CommandPaletteItem("id1", "L", description="D", keywords=["a", "b"])
    d = item.to_dict()
    assert d["id"] == "id1"
    assert d["keywords"] == ["a", "b"]


def test_toast_payload_to_dict_all_fields() -> None:
    from src.core.nexus_ui_shell import ToastPayload

    p = ToastPayload(
        type="info",
        title="T",
        description="D",
        duration_ms=1000,
        action_label="Go",
        action_url="/x",
        dismissable=False,
        icon="i",
    )
    d = p.to_dict()
    assert d["action_label"] == "Go"
    assert d["dismissable"] is False


def test_toast_factories() -> None:
    assert Toast.success("t").type == "success"
    assert Toast.error("e").duration_ms == 8000
    assert Toast.warning("w").type == "warning"
    assert Toast.info("i").type == "info"
    loading = Toast.loading("l")
    assert loading.dismissable is False
    assert loading.duration_ms == 0


def test_get_shell_config_shape() -> None:
    cfg = get_shell_config()
    assert "shortcuts" in cfg
    assert "commands" in cfg
    assert "error_boundaries" in cfg
    assert "themes" in cfg
    assert len(cfg["shortcuts"]) == len(DEFAULT_SHORTCUTS)
    assert len(cfg["commands"]) == len(DEFAULT_COMMANDS)
    assert cfg["error_boundaries"] == ERROR_BOUNDARIES
    assert cfg["themes"] == THEMES


def test_ui_shell_facade() -> None:
    assert UIShell.get_config() == get_shell_config()
