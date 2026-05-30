"""Unified LLM client for Mnemosyne Forge.

Supports OpenAI-compatible APIs (OpenAI, DeepSeek, Kimi, etc.).
Reads provider config from config.yaml and API keys from environment.
v0.3: per-agent LLM routing — each agent can use a different provider/model.
"""

from __future__ import annotations

import json
import re

import httpx

from .config import get_config


def _resolve_agent_provider(agent: str | None = None) -> dict:
    """Resolve which LLM provider to use for a given agent.

    Checks config.yaml llm.agent_routes first, falls back to default_provider.
    """
    cfg = get_config()
    llm = cfg.get("llm", {})
    default = llm.get("default_provider", "deepseek")
    routes = llm.get("agent_routes", {})

    if agent and agent in routes and routes[agent] != "default":
        target = routes[agent]
    else:
        target = default

    providers = llm.get("providers", {})
    if target not in providers:
        target = default

    provider = providers[target].copy()
    import os
    env_var = provider.get("api_key_env", "")
    api_key = os.getenv(env_var, "")

    if not api_key:
        raise ValueError(f"API key not found for provider '{target}'. Set {env_var}")

    provider["api_key"] = api_key
    provider["provider_name"] = target
    provider["temperature"] = llm.get("temperature", 0.4)
    provider["max_tokens"] = llm.get("max_tokens", 1500)
    return provider


def _build_payload(messages: list[dict], system_prompt: str | None, cfg: dict) -> dict:
    payload_messages = []
    if system_prompt:
        payload_messages.append({"role": "system", "content": system_prompt})
    payload_messages.extend(messages)
    return {
        "model": cfg["model"],
        "messages": payload_messages,
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
    }


async def _call_api(payload: dict, cfg: dict) -> str:
    """Send a request to the LLM provider and return the response text."""
    base_url = cfg["base_url"].rstrip("/")
    api_key = cfg["api_key"]
    provider_type = cfg.get("provider_type", "openai_compatible")

    if provider_type != "openai_compatible":
        raise ValueError(f"Unsupported provider_type: {provider_type}")

    url = f"{base_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            if resp.status_code == 401:
                raise RuntimeError("API Key 无效或未配置，请检查 .env 文件中的 API Key")
            if resp.status_code == 403:
                raise RuntimeError("API 访问被拒绝，请检查 API Key 权限或账户余额")
            if resp.status_code == 429:
                raise RuntimeError("API 请求过于频繁，请稍后重试")
            if resp.status_code >= 500:
                raise RuntimeError(f"LLM 服务暂时不可用（{resp.status_code}），请稍后重试")
            raise RuntimeError(f"LLM API 返回错误 {resp.status_code}，请检查配置")
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def chat(
    messages: list[dict],
    system_prompt: str | None = None,
    agent: str | None = None,
) -> str:
    """Send a chat request and return the assistant's text response."""
    cfg = _resolve_agent_provider(agent)
    payload = _build_payload(messages, system_prompt, cfg)
    return await _call_api(payload, cfg)


def _extract_json_block(text: str) -> str:
    """Extract the first JSON object from text that may have markdown fences or extra content."""
    # Prefer fenced block
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()

    # Fallback: find first { ... } pair
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text.strip()


async def chat_json(
    messages: list[dict],
    system_prompt: str | None = None,
    max_retries: int = 2,
    agent: str | None = None,
) -> dict:
    """Send a chat request expecting a JSON response. Retries on parse failure."""
    last_error = ""
    for attempt in range(max_retries + 1):
        raw = await chat(messages, system_prompt, agent=agent)
        try:
            json_str = _extract_json_block(raw)
            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = str(e)
            if attempt < max_retries:
                messages.append({"role": "user", "content": f"Your last response was not valid JSON. Error: {e}. Please respond with ONLY a valid JSON object (no markdown fences, no extra text)."})
    raise ValueError(f"Failed to parse JSON after {max_retries} retries: {last_error}")
