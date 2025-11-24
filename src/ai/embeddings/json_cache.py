import json
import os
from typing import List, Optional, Dict
from src.domain.interfaces.embedding_cache import EmbeddingCache
from src.utils.logger import step_logger

class JSONFileCache(EmbeddingCache):
    """
    File-based cache implementation using JSON.
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.cache: Dict[str, List[float]] = {}
        self._load()

    def _load(self):
        """Load cache from file if it exists."""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                step_logger.info(f"Loaded embedding cache from {self.file_path} ({len(self.cache)} entries)")
            except Exception as e:
                step_logger.warning(f"Failed to load cache from {self.file_path}: {e}")
                self.cache = {}
        else:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            self.cache = {}

    def get(self, key: str) -> Optional[List[float]]:
        return self.cache.get(key)

    def set(self, key: str, embedding: List[float]):
        self.cache[key] = embedding

    def save(self):
        """Save cache to file."""
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f)
            step_logger.info(f"Saved embedding cache to {self.file_path}")
        except Exception as e:
            step_logger.error(f"Failed to save cache to {self.file_path}: {e}")
