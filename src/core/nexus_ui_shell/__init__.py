"""
Nexus UI Shell — Feature 6: Frontend UX Utilities
Codename: ESPERANTO — Feature 6A-6E

Provides:
- Keyboard shortcut registry with conflict detection
- Command palette configuration
- Toast notification system (server-side event payloads)
- Error boundary definitions for frontend consumption
- Theme configuration management
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ── Keyboard Shortcuts ───────────────────────────────────────

@dataclass
class KeyboardShortcut:
    """A registered keyboard shortcut."""
    key: str                    # "k", "n", "/"
    modifiers: list[str]        # ["ctrl"], ["ctrl","shift"], ["meta"]
    action: str                 # "search", "new_notebook", "focus_chat"
    label: str                  # Human-readable label
    category: str = "general"   # "general", "navigation", "editing", "chat"
    when: str = "always"        # "always", "notebook_open", "chat_focused"
    platform_override: Optional[dict[str, str]] = None  # {"mac": "meta", "win": "ctrl"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "modifiers": self.modifiers,
            "action": self.action,
            "label": self.label,
            "category": self.category,
            "when": self.when,
            "display": "+".join(self.modifiers + [self.key.upper()]),
        }


# Default keyboard shortcuts
DEFAULT_SHORTCUTS: list[KeyboardShortcut] = [
    # Navigation
    KeyboardShortcut("k", ["ctrl"], "search", "Search notebooks", "navigation"),
    KeyboardShortcut("n", ["ctrl"], "new_notebook", "New notebook", "navigation"),
    KeyboardShortcut("b", ["ctrl"], "toggle_sidebar", "Toggle sidebar", "navigation"),
    KeyboardShortcut("1", ["ctrl"], "tab_sources", "Sources tab", "navigation"),
    KeyboardShortcut("2", ["ctrl"], "tab_chat", "Chat tab", "navigation"),
    KeyboardShortcut("3", ["ctrl"], "tab_studio", "Studio tab", "navigation"),
    KeyboardShortcut("4", ["ctrl"], "tab_notes", "Notes tab", "navigation"),

    # Chat
    KeyboardShortcut("/", [], "focus_chat", "Focus chat input", "chat", "notebook_open"),
    KeyboardShortcut("Enter", ["shift"], "send_message", "Send message", "chat", "chat_focused"),
    KeyboardShortcut("l", ["ctrl"], "clear_chat", "New chat session", "chat", "chat_focused"),

    # Editing
    KeyboardShortcut("s", ["ctrl"], "save", "Save", "editing"),
    KeyboardShortcut("z", ["ctrl"], "undo", "Undo", "editing"),
    KeyboardShortcut("z", ["ctrl", "shift"], "redo", "Redo", "editing"),

    # Studio
    KeyboardShortcut("g", ["ctrl", "shift"], "generate_artifact", "Generate artifact", "studio", "notebook_open"),
    KeyboardShortcut("e", ["ctrl", "shift"], "export", "Export", "studio", "notebook_open"),

    # General
    KeyboardShortcut("p", ["ctrl", "shift"], "command_palette", "Command palette", "general"),
    KeyboardShortcut(",", ["ctrl"], "open_settings", "Settings", "general"),
    KeyboardShortcut("?", ["ctrl", "shift"], "show_shortcuts", "Show all shortcuts", "general"),
]


# ── Command Palette ──────────────────────────────────────────

@dataclass
class CommandPaletteItem:
    """An item in the command palette."""
    id: str
    label: str
    description: str = ""
    icon: str = ""
    shortcut: str = ""
    category: str = "general"
    action: str = ""
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "shortcut": self.shortcut,
            "category": self.category,
            "keywords": self.keywords,
        }


DEFAULT_COMMANDS: list[CommandPaletteItem] = [
    CommandPaletteItem("new_notebook", "New Notebook", "Create a new notebook", "📓", "Ctrl+N", "Create"),
    CommandPaletteItem("new_source_text", "Add Text Source", "Paste text as a source", "📝", "", "Create"),
    CommandPaletteItem("new_source_url", "Add URL Source", "Import from URL", "🔗", "", "Create"),
    CommandPaletteItem("new_source_upload", "Upload File", "Upload PDF/DOCX", "📤", "", "Create"),
    CommandPaletteItem("generate_summary", "Generate Summary", "Create a summary artifact", "📄", "", "Studio"),
    CommandPaletteItem("generate_podcast", "Generate Podcast", "Create podcast audio", "🎙️", "", "Studio"),
    CommandPaletteItem("generate_quiz", "Generate Quiz", "Create a quiz", "❓", "", "Studio"),
    CommandPaletteItem("generate_flashcards", "Generate Flashcards", "Create FSRS flashcards", "🃏", "", "Studio"),
    CommandPaletteItem("export_pdf", "Export as PDF", "Export current artifact as PDF", "📄", "Ctrl+Shift+E", "Export"),
    CommandPaletteItem("export_docx", "Export as DOCX", "Export as Word document", "📝", "", "Export"),
    CommandPaletteItem("export_epub", "Export as EPUB", "Export for e-readers", "📖", "", "Export"),
    CommandPaletteItem("toggle_dark_mode", "Toggle Dark Mode", "Switch theme", "🌙", "", "Settings"),
    CommandPaletteItem("open_settings", "Settings", "Open application settings", "⚙️", "Ctrl+,", "Settings"),
    CommandPaletteItem("show_shortcuts", "Keyboard Shortcuts", "View all shortcuts", "⌨️", "Ctrl+Shift+?", "Help"),
]


# ── Toast Notification ───────────────────────────────────────

@dataclass
class ToastPayload:
    """Server-side toast notification payload for frontend consumption."""
    type: str               # "success", "error", "warning", "info", "loading"
    title: str
    description: str = ""
    duration_ms: int = 5000
    action_label: Optional[str] = None
    action_url: Optional[str] = None
    dismissable: bool = True
    icon: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "duration_ms": self.duration_ms,
            "action_label": self.action_label,
            "action_url": self.action_url,
            "dismissable": self.dismissable,
            "icon": self.icon,
        }


class Toast:
    """Factory for common toast payloads."""

    @staticmethod
    def success(title: str, description: str = "") -> ToastPayload:
        return ToastPayload("success", title, description, icon="✅")

    @staticmethod
    def error(title: str, description: str = "") -> ToastPayload:
        return ToastPayload("error", title, description, duration_ms=8000, icon="❌")

    @staticmethod
    def warning(title: str, description: str = "") -> ToastPayload:
        return ToastPayload("warning", title, description, icon="⚠️")

    @staticmethod
    def info(title: str, description: str = "") -> ToastPayload:
        return ToastPayload("info", title, description, icon="ℹ️")

    @staticmethod
    def loading(title: str, description: str = "") -> ToastPayload:
        return ToastPayload("loading", title, description, duration_ms=0, dismissable=False, icon="⏳")


# ── Error Boundary Definitions ───────────────────────────────

ERROR_BOUNDARIES: dict[str, dict[str, Any]] = {
    "chat": {
        "fallback_message": "Chat is temporarily unavailable. Please try again.",
        "retry_enabled": True,
        "report_enabled": True,
    },
    "sources": {
        "fallback_message": "Unable to load sources. Some may still be processing.",
        "retry_enabled": True,
        "report_enabled": True,
    },
    "studio": {
        "fallback_message": "Generation encountered an error. Your data is safe.",
        "retry_enabled": True,
        "report_enabled": True,
    },
    "notes": {
        "fallback_message": "Notes are temporarily unavailable.",
        "retry_enabled": True,
        "report_enabled": False,
    },
    "sidebar": {
        "fallback_message": "Navigation error. Try refreshing.",
        "retry_enabled": True,
        "report_enabled": False,
    },
}


# ── Theme Configuration ─────────────────────────────────────

THEMES = {
    "dark": {
        "name": "Dark",
        "class": "dark",
        "colors": {
            "primary": "245 58% 61%",
            "background": "240 10% 3.9%",
            "foreground": "0 0% 98%",
        },
    },
    "light": {
        "name": "Light",
        "class": "",
        "colors": {
            "primary": "245 58% 51%",
            "background": "0 0% 100%",
            "foreground": "240 10% 3.9%",
        },
    },
    "midnight": {
        "name": "Midnight Blue",
        "class": "dark",
        "colors": {
            "primary": "220 70% 55%",
            "background": "220 20% 5%",
            "foreground": "0 0% 95%",
        },
    },
}


# ── Shell Configuration API ──────────────────────────────────

def get_shell_config() -> dict[str, Any]:
    """Get complete UI shell configuration for the frontend."""
    return {
        "shortcuts": [s.to_dict() for s in DEFAULT_SHORTCUTS],
        "commands": [c.to_dict() for c in DEFAULT_COMMANDS],
        "error_boundaries": ERROR_BOUNDARIES,
        "themes": THEMES,
    }


class UIShell:
    """Facade for UI shell utilities: shortcuts, commands, toasts, and themes."""

    @staticmethod
    def config() -> dict[str, Any]:
        """Return complete shell configuration."""
        return get_shell_config()

    @staticmethod
    def toast_success(title: str, description: str = "") -> ToastPayload:
        return Toast.success(title, description)

    @staticmethod
    def toast_error(title: str, description: str = "") -> ToastPayload:
        return Toast.error(title, description)

    @staticmethod
    def toast_warning(title: str, description: str = "") -> ToastPayload:
        return Toast.warning(title, description)

    @staticmethod
    def toast_info(title: str, description: str = "") -> ToastPayload:
        return Toast.info(title, description)
