from __future__ import annotations

import json

from mlaude.tools import browser_tool


class FakeHandle:
    def __init__(self, role: str, text: str, attrs: dict[str, str] | None = None):
        self.role = role
        self.text = text
        self.attrs = attrs or {}
        self.clicked: list[str] = []
        self.filled: list[str] = []
        self.pressed: list[str] = []

    def is_visible(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return True

    def inner_text(self, timeout: int = 0) -> str:
        return self.text

    def get_attribute(self, name: str) -> str | None:
        return self.attrs.get(name)

    def evaluate(self, script: str) -> str:
        del script
        return self.role

    def click(self, button: str = "left") -> None:
        self.clicked.append(button)

    def fill(self, text: str) -> None:
        self.filled.append(text)

    def press(self, key: str) -> None:
        self.pressed.append(key)


class FakeLocator:
    def inner_text(self, timeout: int = 0) -> str:
        del timeout
        return "Visible page text"


class FakeMouse:
    def __init__(self) -> None:
        self.moves: list[tuple[int, int]] = []

    def wheel(self, x: int, y: int) -> None:
        self.moves.append((x, y))


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.com"
        self._handles = [
            FakeHandle("button", "Submit", {"aria-label": "Submit"}),
            FakeHandle("textbox", "", {"name": "email"}),
        ]
        self.mouse = FakeMouse()

    def query_selector_all(self, selector: str):
        del selector
        return self._handles

    def locator(self, selector: str) -> FakeLocator:
        del selector
        return FakeLocator()

    def title(self) -> str:
        return "Example"

    def screenshot(self, path: str, full_page: bool = True) -> None:
        del full_page
        with open(path, "wb") as handle:
            handle.write(b"fake")


class FakeState:
    def __init__(self) -> None:
        self.page = FakePage()
        self.context = self
        self.last_elements: dict[str, FakeHandle] = {}

    def new_page(self) -> FakePage:
        self.page = FakePage()
        return self.page


def test_browser_snapshot_click_type_and_scroll(monkeypatch) -> None:
    state = FakeState()
    monkeypatch.setattr(browser_tool._BROWSER_MANAGER, "get_state", lambda session_id: state)

    snapshot = json.loads(browser_tool._browser_snapshot(task_id="session-1"))
    assert snapshot["title"] == "Example"
    assert snapshot["elements"][0]["element_id"] == "e1"

    click = json.loads(browser_tool._browser_click("e1", task_id="session-1"))
    assert click["clicked"] == "e1"
    assert state.last_elements["e1"].clicked == ["left"]

    typed = json.loads(browser_tool._browser_type("e2", "hi", submit=True, task_id="session-1"))
    assert typed["submitted"] is True
    assert state.last_elements["e2"].filled == ["hi"]
    assert state.last_elements["e2"].pressed == ["Enter"]

    scrolled = json.loads(browser_tool._browser_scroll("down", 300, task_id="session-1"))
    assert scrolled["amount"] == 300
    assert state.page.mouse.moves == [(0, 300)]


def test_browser_rejects_non_http_urls() -> None:
    result = json.loads(browser_tool._browser_navigate("file:///tmp/x", task_id="session-1"))
    assert "error" in result
