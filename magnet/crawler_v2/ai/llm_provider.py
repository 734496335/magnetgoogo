"""LLM provider resolution for offline selector synthesis.

Reads `magnet/.env` (or process env) and picks the first provider with an
API key, in the order best-suited for CN-network + low budget:

  Xiaomi MiMo → DeepSeek → ARK/Volces → OpenAI → Gemini

All providers are surfaced through `LLMChoice` in a unified shape so the
caller (selector_synth) does not branch on vendor.
"""

import os
from dataclasses import dataclass
from typing import Optional


def _load_env_files():
    """Load env vars from magnet/.env if present (does NOT override existing)."""
    here = os.path.dirname(os.path.abspath(__file__))
    # magnet/.env relative to crawler_v2/ai/llm_provider.py
    candidates = [
        os.path.join(here, "..", "..", ".env"),       # magnet/.env
        os.path.join(here, "..", "..", "..", ".env"), # project root .env
    ]
    for env_path in candidates:
        env_path = os.path.abspath(env_path)
        if not os.path.exists(env_path):
            continue
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    if k and v and k not in os.environ:
                        os.environ[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass


_load_env_files()


@dataclass
class LLMChoice:
    """Resolved LLM provider config, vendor-neutral shape."""
    provider: str                   # litellm-style "<vendor>/<model>"
    api_token: str
    base_url: Optional[str] = None
    label: str = ""                 # human-readable for logging
    note: str = ""                  # extra hints
    # Reasoning models (MiMo, DeepSeek-R1, o-series) consume max_tokens with
    # their chain-of-thought before emitting `content`. Set generously.
    max_tokens: int = 4000
    is_reasoning: bool = False


def resolve_llm_choice() -> Optional[LLMChoice]:
    """Pick the first LLM provider with a key set. Returns None if none."""
    if os.environ.get("MIMO_API_KEY"):
        model = os.environ.get("MIMO_MODEL", "mimo-v2.5")
        return LLMChoice(
            provider=f"openai/{model}",
            api_token=os.environ["MIMO_API_KEY"],
            base_url=os.environ.get("MIMO_API_BASE", "https://token-plan-cn.xiaomimimo.com/v1"),
            label="Xiaomi MiMo",
            note="China-direct, reasoning model",
            max_tokens=int(os.environ.get("MIMO_MAX_TOKENS", "4000")),
            is_reasoning=True,
        )
    if os.environ.get("DEEPSEEK_API_KEY"):
        return LLMChoice(
            provider=os.environ.get("DEEPSEEK_MODEL", "deepseek/deepseek-chat"),
            api_token=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"),
            label="DeepSeek",
            note="cheap, China-direct",
        )
    if os.environ.get("VOLCES_API_KEY") or os.environ.get("ARK_API_KEY"):
        return LLMChoice(
            provider="openai/" + os.environ.get("VOLCES_MODEL", "doubao-seed-1-6-250615"),
            api_token=os.environ.get("VOLCES_API_KEY") or os.environ["ARK_API_KEY"],
            base_url=os.environ.get("VOLCES_API_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            label="Volces/ARK (DouBao)",
            note="China-direct, charged per token",
        )
    if os.environ.get("OPENAI_API_KEY"):
        return LLMChoice(
            provider=os.environ.get("OPENAI_MODEL", "openai/gpt-4o-mini"),
            api_token=os.environ["OPENAI_API_KEY"],
            base_url=os.environ.get("OPENAI_API_BASE"),
            label="OpenAI",
            note="needs proxy in CN",
        )
    if os.environ.get("GEMINI_API_KEY"):
        return LLMChoice(
            provider=os.environ.get("GEMINI_MODEL", "gemini/gemini-2.0-flash"),
            api_token=os.environ["GEMINI_API_KEY"],
            label="Gemini",
            note="needs proxy in CN",
        )
    return None
