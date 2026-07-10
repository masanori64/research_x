from __future__ import annotations

BANNED_HTML_TOKENS = (
    "<script",
    "fetch(",
    "xmlhttprequest",
    "localstorage",
    "sessionstorage",
    "javascript:",
    "http://",
    "https://",
)


def validate_safe_review_html(html_text: str) -> list[str]:
    lowered = html_text.casefold()
    return [
        f"rendered HTML contains banned token: {token}"
        for token in BANNED_HTML_TOKENS
        if token in lowered
    ]


def assert_safe_review_html(html_text: str) -> None:
    errors = validate_safe_review_html(html_text)
    if errors:
        raise ValueError("; ".join(errors))
