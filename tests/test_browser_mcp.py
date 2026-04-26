from __future__ import annotations

from mlaude.browser_mcp import (
    canonicalize_result_url,
    guardrail_violation,
    normalize_google_results,
    parse_action_json,
    page_document,
    redact_secrets,
)


def test_google_result_url_canonicalization() -> None:
    url = "https://www.google.com/url?q=https%3A%2F%2Fplaywright.dev%2Fmcp%2Finstallation&sa=U"
    assert canonicalize_result_url(url) == "https://playwright.dev/mcp/installation"


def test_google_result_normalization_filters_google_and_duplicates() -> None:
    rows = normalize_google_results(
        [
            {"title": "Docs", "url": "https://playwright.dev/mcp/", "snippet": "MCP docs"},
            {"title": "Google", "url": "https://www.google.com/preferences", "snippet": ""},
            {"title": "Docs duplicate", "url": "https://playwright.dev/mcp/", "snippet": ""},
            {"title": "", "url": "https://example.com", "snippet": ""},
        ]
    )
    assert rows == [
        {"title": "Docs", "url": "https://playwright.dev/mcp/", "snippet": "MCP docs"}
    ]


def test_mcp_page_document_shape_matches_source_document() -> None:
    document = page_document(
        url="https://example.com",
        title="Example",
        text="Example Domain",
        query="example",
        index=1,
    )
    assert document["source_kind"] == "web_page"
    assert document["file_id"] is None
    assert document["content"] == "Example Domain"
    assert document["extract_status"] == "complete"


def test_browser_guardrails_block_sensitive_actions_and_unrequested_typing() -> None:
    assert guardrail_violation(
        "Open checkout",
        "browser_click",
        {"element": "Submit payment"},
    )
    assert guardrail_violation(
        "Open the login page",
        "browser_type",
        {"text": "not-in-request"},
    )
    assert guardrail_violation(
        "Type hello into the search box",
        "browser_type",
        {"text": "hello"},
    ) is None


def test_secret_redaction_and_action_json_parsing() -> None:
    assert redact_secrets("Authorization: Bearer abc123") == "Authorization=[REDACTED]"
    action = parse_action_json('```json\n{"tool":"browser_snapshot","arguments":{}}\n```')
    assert action["tool"] == "browser_snapshot"
