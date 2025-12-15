"""
Coloraria Configuration Module.

Provides centralized access to configuration and prompts.
"""
from src.config.loader import (
    load_config,
    load_prompts,
    get_config_value,
    get_prompt,
    get_llm_config,
    get_agent_config,
    get_retrieval_config,
    get_benchmark_config
)

__all__ = [
    "load_config",
    "load_prompts",
    "get_config_value",
    "get_prompt",
    "get_llm_config",
    "get_agent_config",
    "get_retrieval_config",
    "get_benchmark_config"
]
