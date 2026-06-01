"""Configuration loader for Mnemosyne Forge.

Reads config.yaml and loads environment variables from .env (via python-dotenv).
"""

from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .env_utils import read_env

_project_root = Path(__file__).resolve().parent.parent
_config_path = _project_root / "config.yaml"

# Load .env once at module level
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

_config_cache: dict[str, Any] | None = None


def _load_raw_config() -> dict[str, Any]:
    """Load and parse config.yaml."""
    if not _config_path.exists():
        raise FileNotFoundError(f"config.yaml not found at {_config_path}")
    with open(_config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_config() -> dict[str, Any]:
    """Return the parsed configuration, caching on first call."""
    global _config_cache
    if _config_cache is None:
        _config_cache = _load_raw_config()
    return _config_cache


def get_llm_config() -> dict[str, Any]:
    """Return the active LLM provider configuration.

    Reads llm.default_provider and looks up the matching provider entry.
    Plugs in the actual API key from the environment variable.
    """
    cfg = get_config()
    llm = cfg.get("llm", {})
    default = llm.get("default_provider", "deepseek")
    providers = llm.get("providers", {})

    if default not in providers:
        raise ValueError(
            f"Default LLM provider '{default}' not found in config.yaml providers. "
            f"Available: {list(providers.keys())}"
        )

    provider = providers[default].copy()
    env_var = provider.get("api_key_env", "")
    api_key = read_env(env_var)

    if not api_key:
        raise ValueError(
            f"API key not found. Set the {env_var} environment variable "
            f"in a .env file or your shell."
        )

    provider["api_key"] = api_key
    provider["provider_name"] = default
    provider["temperature"] = llm.get("temperature", 0.7)
    provider["max_tokens"] = llm.get("max_tokens", 1500)
    return provider


def get_app_config() -> dict[str, Any]:
    """Return app-level configuration."""
    cfg = get_config()
    app = cfg.get("app", {})
    return {
        "name": app.get("name", "Mnemosyne Forge"),
        "host": app.get("host", "127.0.0.1"),
        "port": app.get("port", 8010),
        "database_path": app.get("database_path", "data/forge.db"),
        "export_dir": app.get("export_dir", "exports"),
    }


def get_project_root() -> Path:
    """Return the project root directory."""
    return _project_root
