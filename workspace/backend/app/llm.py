"""Minimal one-shot LLM helper.

Reuses the next-speaker router's provider/key/model configuration so the timeline
can distill a discussion into a decision milestone without a second LLM setup.
Provider-agnostic (anthropic | openai); key from ROUTER_LLM_API_KEY, else
ANTHROPIC_API_KEY; model defaults to Haiku.
"""
from app.config import config

_client = None
_provider = None


def _api_key() -> str:
    return config.ROUTER_LLM_API_KEY or config.ANTHROPIC_API_KEY


def available() -> bool:
    return bool(_api_key())


def _model() -> str:
    if config.ROUTER_LLM_MODEL:
        return config.ROUTER_LLM_MODEL
    if config.ROUTER_LLM_PROVIDER == "openai":
        return "gpt-4o-mini"
    return "claude-haiku-4-5-20251001"


def _get_client():
    global _client, _provider
    provider = config.ROUTER_LLM_PROVIDER
    if _client is not None and _provider == provider:
        return _client, provider
    key = _api_key()
    if provider == "openai":
        from openai import OpenAI
        kwargs = {"api_key": key}
        if config.ROUTER_LLM_BASE_URL:
            kwargs["base_url"] = config.ROUTER_LLM_BASE_URL
        _client = OpenAI(**kwargs)
    else:
        import anthropic
        _client = anthropic.Anthropic(api_key=key)
    _provider = provider
    return _client, provider


def complete(prompt: str, max_tokens: int = 800) -> str:
    """Run a single-prompt completion and return the text. Raises on no key."""
    if not available():
        raise RuntimeError("No LLM API key configured (ROUTER_LLM_API_KEY / ANTHROPIC_API_KEY)")
    client, provider = _get_client()
    model = _model()
    if provider == "openai":
        r = client.chat.completions.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return (r.choices[0].message.content or "").strip()
    r = client.messages.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.content[0].text.strip()
