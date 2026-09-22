"""Errors ``estimate`` raises for ids it doesn't know. Each suggests close
matches and says where to add the missing record."""

from __future__ import annotations

from urllib.parse import urlencode

REPO_URL = "https://github.com/GooeyAI/ecocost"


class UnknownModelError(LookupError):
    """The model is not in the knowledge base, so no estimate is made: a
    guessed model size would dominate the result."""

    def __init__(self, model: str, suggestions: list[str]):
        self.model = model
        self.suggestions = suggestions
        self.contribute_url = f"{REPO_URL}/blob/main/CONTRIBUTING.md#adding-a-model"
        self.request_url = _issue_url(f"Add model: {model}")
        super().__init__(
            _message(
                f"ecocost has no data for model {model!r}.",
                suggestions,
                "  Another id for a known model? Add it to that model's `aliases`.",
                f"  A new model? Add it: {self.contribute_url}",
                f"  Or request it: {self.request_url}",
            )
        )


class UnknownProviderError(LookupError):
    """``provider`` is not a known id. Pass ``None`` when the provider is
    genuinely unknown: that falls back to wide defaults and says so, where a
    mistyped id would silently estimate the wrong site."""

    def __init__(self, provider: str, suggestions: list[str]):
        self.provider = provider
        self.suggestions = suggestions
        self.contribute_url = f"{REPO_URL}/blob/main/CONTRIBUTING.md#adding-a-provider"
        self.request_url = _issue_url(f"Add provider: {provider}")
        super().__init__(
            _message(
                f"ecocost has no provider {provider!r}.",
                suggestions,
                "  Don't know who serves the request? Pass provider=None.",
                f"  A new provider? Add it: {self.contribute_url}",
                f"  Or request it: {self.request_url}",
            )
        )


def _message(headline: str, suggestions: list[str], *hints: str) -> str:
    lines = [headline]
    if suggestions:
        lines.append(f"  Did you mean {', '.join(map(repr, suggestions))}?")
    return "\n".join([*lines, *hints])


def _issue_url(title: str) -> str:
    return f"{REPO_URL}/issues/new?" + urlencode({"title": title})
