"""
Coloraria Configuration Loader.

Centralized configuration loading from config/config.yaml and config/prompts.yaml.
Provides cached singleton access to prevent repeated file I/O.
"""
import os
from pathlib import Path
from functools import lru_cache
from typing import Any, Dict, Optional
import yaml

from src.utils.logger import step_logger


def _get_project_root() -> Path:
    """Get project root directory."""
    # Navigate up from src/config/loader.py to project root
    return Path(__file__).parent.parent.parent


@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """
    Load configuration from config/config.yaml (cached singleton).
    
    Returns:
        Dict containing all configuration values
    """
    config_path = _get_project_root() / "config" / "config.yaml"
    
    if not config_path.exists():
        step_logger.warning(f"[Config] Config file not found at {config_path}, using defaults")
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        step_logger.info(f"[Config] Loaded configuration from {config_path}")
        return config
    except Exception as e:
        step_logger.error(f"[Config] Failed to load config: {e}")
        return {}


@lru_cache(maxsize=1)
def load_prompts() -> Dict[str, Any]:
    """
    Load prompts from config/prompts.yaml (cached singleton).
    
    Returns:
        Dict containing all prompt values
    """
    prompts_path = _get_project_root() / "config" / "prompts.yaml"
    
    if not prompts_path.exists():
        step_logger.warning(f"[Config] Prompts file not found at {prompts_path}, using defaults")
        return {}
    
    try:
        with open(prompts_path, 'r', encoding='utf-8') as f:
            prompts = yaml.safe_load(f) or {}
        step_logger.info(f"[Config] Loaded prompts from {prompts_path}")
        return prompts
    except Exception as e:
        step_logger.error(f"[Config] Failed to load prompts: {e}")
        return {}


def get_config_value(path: str, default: Any = None) -> Any:
    """
    Get a configuration value by dot-separated path.
    
    Args:
        path: Dot-separated path like "llm.model" or "agent.max_iterations"
        default: Default value if path not found
        
    Returns:
        Configuration value or default
    """
    config = load_config()
    keys = path.split(".")
    
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value if value is not None else default


def get_prompt(name: str, default: str = "") -> str:
    """
    Get a prompt by name.
    
    Args:
        name: Prompt name (e.g., "system_prompt", "agent_system_prompt")
        default: Default value if not found
        
    Returns:
        Prompt string or default
    """
    prompts = load_prompts()
    return prompts.get(name, default)


# Convenience functions for common config access
def get_llm_config() -> Dict[str, Any]:
    """Get LLM configuration section."""
    config = load_config()
    return config.get("llm", {})


def get_agent_config() -> Dict[str, Any]:
    """Get agent configuration section."""
    config = load_config()
    return config.get("agent", {})


def get_retrieval_config() -> Dict[str, Any]:
    """Get retrieval configuration section."""
    config = load_config()
    return config.get("retrieval", {})

def get_benchmark_config() -> Dict[str, Any]:
    """
    Get benchmark configuration.
    
    Returns:
        Dict with benchmark settings (model, temperature, etc.)
    """
    return get_config_value("benchmark", {})
