"""mlaude CLI skin/theme engine.

Skins customize the CLI's
visual appearance — colors, spinner, branding, tool display. User skins are
YAML files in ~/.mlaude/skins/. No code changes needed to add a new skin.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mlaude.settings import MLAUDE_HOME

logger = logging.getLogger(__name__)


@dataclass
class SkinConfig:
    """Complete skin configuration."""
    name: str
    description: str = ""
    colors: Dict[str, str] = field(default_factory=dict)
    spinner: Dict[str, Any] = field(default_factory=dict)
    branding: Dict[str, str] = field(default_factory=dict)
    tool_prefix: str = "┊"
    tool_emojis: Dict[str, str] = field(default_factory=dict)
    banner_logo: str = ""
    banner_hero: str = ""

    def get_color(self, key: str, fallback: str = "") -> str:
        return self.colors.get(key, fallback)

    def get_spinner_wings(self) -> List[Tuple[str, str]]:
        raw = self.spinner.get("wings", [])
        result = []
        for pair in raw:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                result.append((str(pair[0]), str(pair[1])))
        return result

    def get_branding(self, key: str, fallback: str = "") -> str:
        return self.branding.get(key, fallback)


# =============================================================================
# Built-in skins
# =============================================================================

_BUILTIN_SKINS: Dict[str, Dict[str, Any]] = {
    "default": {
        "name": "default",
        "description": "Classic mlaude — gold and kawaii",
        "colors": {
            "banner_border": "#CD7F32",
            "banner_title": "#FFD700",
            "banner_accent": "#FFBF00",
            "banner_dim": "#B8860B",
            "banner_text": "#FFF8DC",
            "ui_accent": "#FFBF00",
            "ui_label": "#DAA520",
            "ui_ok": "#4caf50",
            "ui_error": "#ef5350",
            "ui_warn": "#ffa726",
            "prompt": "#FFF8DC",
            "input_rule": "#CD7F32",
            "response_border": "#FFD700",
            "status_bar_bg": "#1a1a2e",
            "session_label": "#DAA520",
            "session_border": "#8B8682",
        },
        "spinner": {},
        "branding": {
            "agent_name": "mlaude",
            "welcome": "Welcome to mlaude! Type your message or /help for commands.",
            "goodbye": "Goodbye! 💀",
            "response_label": " 💀 mlaude ",
            "prompt_symbol": "❯ ",
            "help_header": "(^_^)? Available Commands",
        },
        "tool_prefix": "┊",
    },
    "ares": {
        "name": "ares",
        "description": "War-god theme — crimson and bronze",
        "colors": {
            "banner_border": "#9F1C1C",
            "banner_title": "#C7A96B",
            "banner_accent": "#DD4A3A",
            "banner_dim": "#6B1717",
            "banner_text": "#F1E6CF",
            "ui_accent": "#DD4A3A",
            "ui_label": "#C7A96B",
            "ui_ok": "#4caf50",
            "ui_error": "#ef5350",
            "ui_warn": "#ffa726",
            "prompt": "#F1E6CF",
            "input_rule": "#9F1C1C",
            "response_border": "#C7A96B",
            "status_bar_bg": "#2A1212",
            "session_label": "#C7A96B",
            "session_border": "#6E584B",
        },
        "spinner": {
            "waiting_faces": ["(⚔)", "(⛨)", "(▲)", "(<>)", "(/)"],
            "thinking_faces": ["(⚔)", "(⛨)", "(▲)", "(⌁)", "(<>)"],
            "thinking_verbs": [
                "forging", "marching", "sizing the field", "holding the line",
                "hammering plans", "tempering steel", "plotting impact", "raising the shield",
            ],
            "wings": [["⟪⚔", "⚔⟫"], ["⟪▲", "▲⟫"], ["⟪╸", "╺⟫"], ["⟪⛨", "⛨⟫"]],
        },
        "branding": {
            "agent_name": "Ares Agent",
            "welcome": "Welcome to Ares Agent! Type your message or /help for commands.",
            "goodbye": "Farewell, warrior! ⚔",
            "response_label": " ⚔ Ares ",
            "prompt_symbol": "⚔ ❯ ",
            "help_header": "(⚔) Available Commands",
        },
        "tool_prefix": "╎",
        "banner_hero": """[#9F1C1C]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣤⣤⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#9F1C1C]⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⣿⠟⠻⣿⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#C7A96B]⠀⠀⠀⠀⠀⠀⠀⣠⣾⡿⠋⠀⠀⠀⠙⢿⣷⣄⠀⠀⠀⠀⠀⠀⠀[/]
[#DD4A3A]⠀⠀⠀⠀⠀⠀⠀⣿⡇⠀⠀⚔⠀⠀⠀⢸⣿⠀⠀⠀[/]
[#6B1717]⠀⠀⠀⠀⠀⠀⠀⢿⣧⠀⠀⠀⠀⠀⠀⣼⡿⠀⠀⠀[/]
[#C7A96B]⠀⠀⠀⠀⠈⠻⣿⣷⣦⣤⣀⣀⣤⣤⣶⣿⠿⠋⠀⠀⠀⠀[/]
[dim #6B1717]⠀⠀⠀⠀⠀⠀⠀⠀war god online⠀⠀⠀⠀⠀⠀⠀⠀[/]""",
    },
    "mono": {
        "name": "mono",
        "description": "Monochrome — clean grayscale",
        "colors": {
            "banner_border": "#555555",
            "banner_title": "#e6edf3",
            "banner_accent": "#aaaaaa",
            "banner_dim": "#444444",
            "banner_text": "#c9d1d9",
            "ui_accent": "#aaaaaa",
            "ui_label": "#888888",
            "ui_ok": "#888888",
            "ui_error": "#cccccc",
            "ui_warn": "#999999",
            "prompt": "#c9d1d9",
            "input_rule": "#444444",
            "response_border": "#aaaaaa",
            "status_bar_bg": "#1F1F1F",
            "session_label": "#888888",
            "session_border": "#555555",
        },
        "spinner": {},
        "branding": {
            "agent_name": "mlaude",
            "welcome": "Welcome to mlaude! Type your message or /help for commands.",
            "goodbye": "Goodbye! 💀",
            "response_label": " 💀 mlaude ",
            "prompt_symbol": "❯ ",
            "help_header": "[?] Available Commands",
        },
        "tool_prefix": "┊",
    },
    "slate": {
        "name": "slate",
        "description": "Cool blue — developer-focused",
        "colors": {
            "banner_border": "#4169e1",
            "banner_title": "#7eb8f6",
            "banner_accent": "#8EA8FF",
            "banner_dim": "#4b5563",
            "banner_text": "#c9d1d9",
            "ui_accent": "#7eb8f6",
            "ui_label": "#8EA8FF",
            "ui_ok": "#63D0A6",
            "ui_error": "#F7A072",
            "ui_warn": "#e6a855",
            "prompt": "#c9d1d9",
            "input_rule": "#4169e1",
            "response_border": "#7eb8f6",
            "status_bar_bg": "#151C2F",
            "session_label": "#7eb8f6",
            "session_border": "#4b5563",
        },
        "spinner": {},
        "branding": {
            "agent_name": "mlaude",
            "welcome": "Welcome to mlaude! Type your message or /help for commands.",
            "goodbye": "Goodbye! 💀",
            "response_label": " 💀 mlaude ",
            "prompt_symbol": "❯ ",
            "help_header": "(^_^)? Available Commands",
        },
        "tool_prefix": "┊",
    },
    "poseidon": {
        "name": "poseidon",
        "description": "Ocean-god theme — deep blue and seafoam",
        "colors": {
            "banner_border": "#2A6FB9", "banner_title": "#A9DFFF",
            "banner_accent": "#5DB8F5", "banner_dim": "#153C73",
            "banner_text": "#EAF7FF", "ui_accent": "#5DB8F5",
            "prompt": "#EAF7FF", "input_rule": "#2A6FB9",
            "response_border": "#5DB8F5", "session_label": "#A9DFFF",
            "session_border": "#496884",
        },
        "spinner": {
            "waiting_faces": ["(≈)", "(Ψ)", "(∿)", "(◌)", "(◠)"],
            "thinking_faces": ["(Ψ)", "(∿)", "(≈)", "(⌁)", "(◌)"],
            "thinking_verbs": [
                "charting currents", "sounding the depth", "reading foam lines",
                "steering the trident", "tracking undertow", "plotting sea lanes",
            ],
            "wings": [["⟪≈", "≈⟫"], ["⟪Ψ", "Ψ⟫"], ["⟪∿", "∿⟫"]],
        },
        "branding": {
            "agent_name": "Poseidon Agent",
            "goodbye": "Fair winds! Ψ",
            "response_label": " Ψ Poseidon ",
            "prompt_symbol": "Ψ ❯ ",
            "help_header": "(Ψ) Available Commands",
        },
        "tool_prefix": "│",
    },
    "charizard": {
        "name": "charizard",
        "description": "Volcanic theme — burnt orange and ember",
        "colors": {
            "banner_border": "#C75B1D", "banner_title": "#FFD39A",
            "banner_accent": "#F29C38", "banner_dim": "#7A3511",
            "banner_text": "#FFF0D4", "ui_accent": "#F29C38",
            "prompt": "#FFF0D4", "input_rule": "#C75B1D",
            "response_border": "#F29C38", "session_label": "#FFD39A",
            "session_border": "#6C4724",
        },
        "spinner": {
            "waiting_faces": ["(✦)", "(▲)", "(◇)", "(<>)", "(🔥)"],
            "thinking_faces": ["(✦)", "(▲)", "(◇)", "(⌁)", "(🔥)"],
            "thinking_verbs": [
                "banking into the draft", "measuring burn", "reading the updraft",
                "tracking ember fall", "setting wing angle", "coiling for lift",
            ],
            "wings": [["⟪✦", "✦⟫"], ["⟪▲", "▲⟫"], ["⟪◌", "◌⟫"]],
        },
        "branding": {
            "agent_name": "Charizard Agent",
            "goodbye": "Flame out! ✦",
            "response_label": " ✦ Charizard ",
            "prompt_symbol": "✦ ❯ ",
            "help_header": "(✦) Available Commands",
        },
        "tool_prefix": "│",
    },
    "sisyphus": {
        "name": "sisyphus",
        "description": "Sisyphean theme — austere grayscale with persistence",
        "colors": {
            "banner_border": "#B7B7B7", "banner_title": "#F5F5F5",
            "banner_accent": "#E7E7E7", "banner_dim": "#4A4A4A",
            "banner_text": "#D3D3D3", "ui_accent": "#E7E7E7",
            "prompt": "#F5F5F5", "input_rule": "#656565",
            "response_border": "#B7B7B7", "session_label": "#919191",
            "session_border": "#656565",
        },
        "spinner": {
            "waiting_faces": ["(◉)", "(◌)", "(◬)", "(⬤)", "(::)"],
            "thinking_faces": ["(◉)", "(◬)", "(◌)", "(○)", "(●)"],
            "thinking_verbs": [
                "finding traction", "measuring the grade", "resetting the boulder",
                "counting the ascent", "testing leverage", "pushing uphill",
            ],
            "wings": [["⟪◉", "◉⟫"], ["⟪◬", "◬⟫"], ["⟪◌", "◌⟫"]],
        },
        "branding": {
            "agent_name": "Sisyphus Agent",
            "goodbye": "The boulder waits. ◉",
            "response_label": " ◉ Sisyphus ",
            "prompt_symbol": "◉ ❯ ",
            "help_header": "(◉) Available Commands",
        },
        "tool_prefix": "│",
    },
    "daylight": {
        "name": "daylight",
        "description": "Light theme — dark text and cool blue accents",
        "colors": {
            "banner_border": "#2563EB", "banner_title": "#0F172A",
            "banner_accent": "#1D4ED8", "banner_dim": "#475569",
            "banner_text": "#111827", "ui_accent": "#2563EB",
            "prompt": "#111827", "input_rule": "#93C5FD",
            "response_border": "#2563EB", "session_label": "#1D4ED8",
            "session_border": "#64748B",
        },
        "spinner": {},
        "branding": {
            "agent_name": "mlaude",
            "response_label": " 💀 mlaude ",
            "prompt_symbol": "❯ ",
            "help_header": "[?] Available Commands",
        },
        "tool_prefix": "│",
    },
    "warm-lightmode": {
        "name": "warm-lightmode",
        "description": "Warm light mode — brown/gold text for light terminal backgrounds",
        "colors": {
            "banner_border": "#8B6914", "banner_title": "#5C3D11",
            "banner_accent": "#8B4513", "banner_dim": "#8B7355",
            "banner_text": "#2C1810", "ui_accent": "#8B4513",
            "prompt": "#2C1810", "input_rule": "#8B6914",
            "response_border": "#8B6914", "session_label": "#5C3D11",
            "session_border": "#A0845C",
        },
        "spinner": {},
        "branding": {
            "agent_name": "mlaude",
            "response_label": " 💀 mlaude ",
            "prompt_symbol": "❯ ",
            "help_header": "(^_^)? Available Commands",
        },
        "tool_prefix": "┊",
    },
}


# =============================================================================
# Skin loading and management
# =============================================================================

_active_skin: Optional[SkinConfig] = None
_active_skin_name: str = "default"


def _skins_dir() -> Path:
    return MLAUDE_HOME / "skins"


def _load_skin_from_yaml(path: Path) -> Optional[Dict[str, Any]]:
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict) and "name" in data:
            return data
    except Exception as e:
        logger.debug("Failed to load skin from %s: %s", path, e)
    return None


def _build_skin_config(data: Dict[str, Any]) -> SkinConfig:
    default = _BUILTIN_SKINS["default"]
    colors = dict(default.get("colors", {}))
    colors.update(data.get("colors", {}))
    spinner = dict(default.get("spinner", {}))
    spinner.update(data.get("spinner", {}))
    branding = dict(default.get("branding", {}))
    branding.update(data.get("branding", {}))

    return SkinConfig(
        name=data.get("name", "unknown"),
        description=data.get("description", ""),
        colors=colors,
        spinner=spinner,
        branding=branding,
        tool_prefix=data.get("tool_prefix", default.get("tool_prefix", "┊")),
        tool_emojis=data.get("tool_emojis", {}),
        banner_logo=data.get("banner_logo", ""),
        banner_hero=data.get("banner_hero", ""),
    )


def list_skins() -> List[Dict[str, str]]:
    result = []
    for name, data in _BUILTIN_SKINS.items():
        result.append({
            "name": name,
            "description": data.get("description", ""),
            "source": "builtin",
        })
    skins_path = _skins_dir()
    if skins_path.is_dir():
        for f in sorted(skins_path.glob("*.yaml")):
            data = _load_skin_from_yaml(f)
            if data:
                skin_name = data.get("name", f.stem)
                if any(s["name"] == skin_name for s in result):
                    continue
                result.append({
                    "name": skin_name,
                    "description": data.get("description", ""),
                    "source": "user",
                })
    return result


def load_skin(name: str) -> SkinConfig:
    skins_path = _skins_dir()
    user_file = skins_path / f"{name}.yaml"
    if user_file.is_file():
        data = _load_skin_from_yaml(user_file)
        if data:
            return _build_skin_config(data)
    if name in _BUILTIN_SKINS:
        return _build_skin_config(_BUILTIN_SKINS[name])
    logger.warning("Skin '%s' not found, using default", name)
    return _build_skin_config(_BUILTIN_SKINS["default"])


def get_active_skin() -> SkinConfig:
    global _active_skin
    if _active_skin is None:
        _active_skin = load_skin(_active_skin_name)
    return _active_skin


def set_active_skin(name: str) -> SkinConfig:
    global _active_skin, _active_skin_name
    _active_skin_name = name
    _active_skin = load_skin(name)
    return _active_skin


def get_active_skin_name() -> str:
    return _active_skin_name


def init_skin_from_config(config: dict) -> None:
    display = config.get("display") or {}
    if not isinstance(display, dict):
        display = {}
    skin_name = display.get("skin", "default")
    if isinstance(skin_name, str) and skin_name.strip():
        set_active_skin(skin_name.strip())
    else:
        set_active_skin("default")


def get_active_prompt_symbol(fallback: str = "❯ ") -> str:
    try:
        return get_active_skin().get_branding("prompt_symbol", fallback)
    except Exception:
        return fallback


def get_active_help_header(fallback: str = "(^_^)? Available Commands") -> str:
    try:
        return get_active_skin().get_branding("help_header", fallback)
    except Exception:
        return fallback


def get_prompt_toolkit_style_overrides() -> Dict[str, str]:
    """Return prompt_toolkit style overrides derived from the active skin.

    These are layered on top of the CLI's base TUI style so /skin can refresh
    the live prompt_toolkit UI immediately without rebuilding the app.
    """
    try:
        skin = get_active_skin()
    except Exception:
        return {}

    prompt = skin.get_color("prompt", "#FFF8DC")
    input_rule = skin.get_color("input_rule", "#CD7F32")
    title = skin.get_color("banner_title", "#FFD700")
    text = skin.get_color("banner_text", prompt)
    dim = skin.get_color("banner_dim", "#555555")
    status_bg = skin.get_color("status_bar_bg", "#1a1a2e")
    accent = skin.get_color("ui_accent", "#FFBF00")

    return {
        "input-area": prompt,
        "placeholder": f"{dim} italic",
        "prompt": prompt,
        "prompt-working": f"{dim} italic",
        "hint": f"{dim} italic",
        "status-bar": f"bg:{status_bg} #C0C0C0",
        "status-bar-strong": f"bg:{status_bg} {title} bold",
        "status-bar-dim": f"bg:{status_bg} {dim}",
        "input-rule": input_rule,
        "completion-menu": f"bg:{status_bg} {text}",
        "completion-menu.completion": f"bg:{status_bg} {text}",
        "completion-menu.completion.current": f"bg:#333355 {title}",
        "completion-menu.meta.completion": f"bg:{status_bg} {dim}",
        "completion-menu.meta.completion.current": f"bg:#333355 {accent}",
    }
