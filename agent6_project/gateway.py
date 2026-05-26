"""
Thin async-compatible wrapper around LLM Gateway V3.
Loads .env from the project hierarchy so LLM_GATEWAY_V3_URL is available,
then delegates all calls to the gateway HTTP server (which holds the API keys).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# ── .env loading — search hierarchy: project / Resubmission-root / gateway-root
try:
    from dotenv import load_dotenv
    _ENV_CANDIDATES = [
        Path(__file__).parent / ".env",                                                     # agent6_project/.env
        Path(__file__).parent.parent / ".env",                                              # Resubmission/.env
        Path(__file__).parent.parent / "5e4a8833-292d-4ce5-be97-749c7656bdbf" / ".env",    # gateway's .env
    ]
    for _env_path in _ENV_CANDIDATES:
        if _env_path.exists():
            load_dotenv(_env_path, override=False)   # override=False: first found wins
            break
except ImportError:
    pass  # python-dotenv not installed — rely on environment variables already set

# ── sys.path: make gateway client importable ──────────────────────────────────
# IMPORTANT: append to END so the gateway's schemas.py does NOT shadow the
# project's schemas.py.  The project dir must stay first in sys.path.
_PROJECT_ROOT = Path(__file__).parent
_GATEWAY_ROOT = _PROJECT_ROOT.parent / "5e4a8833-292d-4ce5-be97-749c7656bdbf" / "llm_gatewayV3"

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))   # project first — resolves project schemas.py

if str(_GATEWAY_ROOT) not in sys.path:
    sys.path.append(str(_GATEWAY_ROOT))      # gateway last — resolves client.py without shadowing

from client import LLM  # noqa: E402

_DEFAULT_LLM: Optional[LLM] = None


def _llm() -> LLM:
    global _DEFAULT_LLM
    if _DEFAULT_LLM is None:
        _DEFAULT_LLM = LLM()
    return _DEFAULT_LLM


def chat(
    messages: list[dict],
    *,
    system: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 2048,
    temperature: float = 0.3,
    response_format: Optional[Any] = None,
    auto_route: Optional[str] = None,
) -> dict:
    """
    Call the LLM Gateway and return the raw response dict.

    The gateway handles provider failover — if a provider's quota is exhausted
    or returns an error, it automatically moves to the next available one.
    Use auto_route=<role> to let the gateway's router pick the best provider tier.
    Use provider=<name> to pin a specific provider (with no gateway-level fallback).
    """
    return _llm().chat(
        messages=messages,
        system=system,
        provider=provider,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format=response_format,
        auto_route=auto_route,
    )


_FALLBACK_PROVIDERS = ["gemini", "groq", "cerebras", "nvidia", "github", "openrouter"]


def chat_with_fallback(
    messages: list[dict],
    *,
    system: Optional[str] = None,
    max_tokens: int = 2048,
    temperature: float = 0.3,
    response_format: Optional[Any] = None,
) -> dict:
    """
    Try providers in explicit order until one succeeds.
    Use this when auto_route itself may be unavailable or unreliable.
    """
    last_exc: Exception | None = None
    for provider in _FALLBACK_PROVIDERS:
        try:
            return _llm().chat(
                messages=messages,
                system=system,
                provider=provider,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format=response_format,
            )
        except Exception as exc:
            last_exc = exc
            continue
    raise RuntimeError(f"All providers failed. Last error: {last_exc}")


def parse_json(resp: dict, fallback: dict | None = None) -> dict:
    """Extract parsed JSON from a gateway response with graceful fallback."""
    if resp.get("parsed"):
        return resp["parsed"]
    text = resp.get("text", "")
    try:
        clean = text.strip()
        if clean.startswith("```"):
            lines = clean.splitlines()
            clean = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(clean)
    except Exception:
        return fallback or {}
