"""
Dictionary Preloader for Concurrent Ingestion.

Pre-loads all shared/dictionary nodes (Materia, Departamento, Rango) 
BEFORE concurrent document processing to prevent deadlocks.

Why this is needed:
- Materia, Departamento, Rango nodes are shared across all documents
- Concurrent writes to the same node cause Neo4j deadlocks
- By pre-creating these nodes, document workers only create relationships
"""
from typing import Optional, Dict, Any
from src.domain.value_objects.materias_model import Materias
from src.domain.value_objects.departamentos_model import Departamentos
from src.domain.value_objects.rangos_model import Rangos
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.utils.logger import step_logger


class DictionaryPreloader:
    """
    Pre-loads Materia, Departamento, Rango nodes sequentially.
    This prevents deadlocks during concurrent document ingestion.
    """
    
    def __init__(self, adapter: Neo4jAdapter):
        self.adapter = adapter
        
    def preload_all(self) -> Dict[str, int]:
        """
        Pre-create all dictionary nodes from value objects.
        
        Returns:
            Dict with counts: {"materias": N, "departamentos": N, "rangos": N}
        """
        stats = {
            "materias": 0,
            "departamentos": 0,
            "rangos": 0
        }
        
        step_logger.info("[DictionaryPreloader] Starting dictionary preload...")
        
        # Load all Materias
        stats["materias"] = self._preload_model(Materias, "Materia")
        step_logger.info(f"[DictionaryPreloader] Preloaded {stats['materias']} Materia nodes")
        
        # Load all Departamentos
        stats["departamentos"] = self._preload_model(Departamentos, "Departamento")
        step_logger.info(f"[DictionaryPreloader] Preloaded {stats['departamentos']} Departamento nodes")
        
        # Load all Rangos
        stats["rangos"] = self._preload_model(Rangos, "Rango")
        step_logger.info(f"[DictionaryPreloader] Preloaded {stats['rangos']} Rango nodes")
        
        total = sum(stats.values())
        step_logger.info(f"[DictionaryPreloader] Complete. Total: {total} dictionary nodes")
        
        return stats
    
    def _preload_model(self, model_class, label: str) -> int:
        """
        Extract all constants from a BaseModel class and create nodes.
        
        Args:
            model_class: Class like Materias, Departamentos, Rangos
            label: Neo4j node label (e.g., "Materia")
            
        Returns:
            Number of nodes created
        """
        count = 0
        nodes_data = []
        
        # Extract all class constants (NAME = code pattern)
        for name, code in model_class.__dict__.items():
            # Skip private/magic attributes and methods
            if name.startswith('_') or callable(code) or not isinstance(code, int):
                continue
                
            # Convert UPPER_SNAKE_CASE to readable name
            readable_name = name.replace('_', ' ').title()
            
            nodes_data.append({
                "labels": [label],
                "props": {
                    "id": code,
                    "name": readable_name
                }
            })
            count += 1
        
        # Batch insert all nodes
        if nodes_data:
            self.adapter.batch_merge_nodes(nodes_data)
        
        return count


def preload_dictionaries(adapter: Neo4jAdapter) -> Dict[str, int]:
    """Convenience function to preload all dictionaries."""
    preloader = DictionaryPreloader(adapter)
    return preloader.preload_all()
