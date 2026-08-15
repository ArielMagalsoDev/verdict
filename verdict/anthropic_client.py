"""Lazy Anthropic client + a shared forced-tool-call helper. Every real model
call in this project pins temperature 0 and the same model id — mirrors
lib/anthropic.ts in the original Next.js app. Module-load-time construction
would break `import verdict.main` with no .env present, so the client is
built on first use, not at import time."""

from anthropic import Anthropic

from .config import settings

TEMPERATURE = 0

_client: Anthropic | None = None


def get_anthropic() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings().anthropic_api_key)
    return _client


def llm_enabled() -> bool:
    return bool(settings().anthropic_api_key)


def tool_call(system: str, user: str, tool: dict, max_tokens: int = 1024) -> dict | None:
    """Force a single tool call and return its parsed input dict, or None if
    the model returned no tool_use block."""
    response = get_anthropic().messages.create(
        model=settings().anthropic_model,
        temperature=TEMPERATURE,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    return None
