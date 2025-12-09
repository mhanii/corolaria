"""
Prompt Builder Service.
Builds prompts with injected RAG context from external YAML configuration.
"""
import os
from typing import List, Optional, Dict, Any
from pathlib import Path
import yaml

from src.utils.logger import step_logger


class PromptBuilder:
    """
    Builds prompts for LLM with RAG context injection.
    Loads templates from external YAML configuration.
    """
    
    DEFAULT_PROMPTS = {
        "system_prompt": (
            "You are a legal assistant answering questions based solely on provided context.\n"
            "Always cite sources using [cite:ID]article text[/cite] format. Be concise and accurate.\n"
            "If the context doesn't contain relevant information, say so clearly."
        ),
        "context_template": "[Fuente: {cite_key}] {normativa_title} - {article_path}\n{article_text}",
        "citation_instruction": "Cite sources inline using [cite:ID]descriptive text[/cite] format where ID matches the source identifiers above."
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize PromptBuilder with optional config path.
        
        Args:
            config_path: Path to prompts.yaml file. If None, uses default location.
        """
        self.prompts = self.DEFAULT_PROMPTS.copy()
        
        # Try to load from config file
        if config_path is None:
            # Default config location
            project_root = Path(__file__).parent.parent.parent.parent
            config_path = project_root / "config" / "prompts.yaml"
        else:
            config_path = Path(config_path)
        
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded = yaml.safe_load(f)
                    if loaded:
                        self.prompts.update(loaded)
                step_logger.info(f"[PromptBuilder] Loaded prompts from {config_path}")
            except Exception as e:
                step_logger.warning(f"[PromptBuilder] Failed to load prompts config: {e}, using defaults")
        else:
            step_logger.info("[PromptBuilder] Using default prompts (no config file found)")
    
    def build_system_prompt(self) -> str:
        """
        Get the system prompt.
        
        Returns:
            System prompt string
        """
        return self.prompts.get("system_prompt", self.DEFAULT_PROMPTS["system_prompt"])
    
    def build_context(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Build context string from RAG retrieved chunks.
        
        Args:
            chunks: List of article result dicts with keys:
                    - article_text
                    - normativa_title
                    - article_path (or context_path_text)
                    - article_number
                    
        Returns:
            Formatted context string with indexed sources
        """
        if not chunks:
            return ""
        
        template = self.prompts.get("context_template", self.DEFAULT_PROMPTS["context_template"])
        citation_instruction = self.prompts.get("citation_instruction", self.DEFAULT_PROMPTS["citation_instruction"])
        
        context_parts = []
        
        for i, chunk in enumerate(chunks, start=1):
            # Get article path - prefer pre-computed path, fall back to context_path_text
            article_path = chunk.get("article_path") or chunk.get("metadata", {}).get("context_path_text", "")
            
            # Format context entry
            entry = template.format(
                index=i,
                normativa_title=chunk.get("normativa_title", "Unknown"),
                article_path=article_path or chunk.get("article_number", ""),
                article_text=chunk.get("article_text", "")
            )
            context_parts.append(entry)
        
        context = "\n\n".join(context_parts)
        
        # Add citation instruction
        if citation_instruction:
            context = f"{context}\n\n{citation_instruction}"
        
        step_logger.info(f"[PromptBuilder] Built context with {len(chunks)} sources ({len(context)} chars)")
        
        return context
    
    def build_user_message(self, query: str) -> str:
        """
        Build user message (simple passthrough for now).
        
        Args:
            query: User's question
            
        Returns:
            Formatted user message
        """
        return query
    
    def get_few_shot_example(self) -> Optional[Dict[str, str]]:
        """
        Get few-shot example if configured.
        
        Returns:
            Dict with 'user' and 'assistant' keys, or None
        """
        return self.prompts.get("few_shot_example")
