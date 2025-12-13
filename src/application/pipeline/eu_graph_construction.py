# application/pipelines/eu_graph_construction.py
"""
EU Graph Construction pipeline step.

Persists EUNormativa documents to Neo4j graph database.
Uses unified Normativa labels with source differentiation.
"""
from typing import List, Optional
from dataclasses import dataclass

from src.domain.models.eu_normativa import EUNormativa
from src.domain.repository.eu_normativa_repository import EUNormativaRepository
from src.infrastructure.graphdb.connection import Neo4jConnection
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from src.application.pipeline.base import Step
from dotenv import load_dotenv
import os
from src.utils.logger import step_logger

# Import tracing (optional)
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("eu_graph_construction")
except ImportError:
    _tracer = None


@dataclass
class EUGraphConstructionResult:
    """Result of EU graph construction with statistics."""
    
    doc_id: str
    normativa_title: str
    nodes_created: int = 0
    relationships_created: int = 0
    eurovoc_count: int = 0
    
    def __repr__(self):
        return (
            f"EUGraphConstructionResult(doc_id={self.doc_id!r}, "
            f"nodes={self.nodes_created}, rels={self.relationships_created})"
        )


class EUGraphConstruction(Step):
    """
    Pipeline step that persists EUNormativa to Neo4j.
    
    Uses unified Normativa label with source="EUR-Lex" property.
    """
    
    def __init__(self, name: str, adapter: Neo4jAdapter = None, *args):
        super().__init__(name)
        
        self._owns_connection = False
        
        if adapter is not None:
            # Use shared adapter
            self.adapter = adapter
            self.connection = None
        else:
            # Create own connection
            load_dotenv()
            neo4j_uri = os.getenv("NEO4J_URI")
            neo4j_user = os.getenv("NEO4J_USER")
            neo4j_password = os.getenv("NEO4J_PASSWORD")
            self.connection = Neo4jConnection(neo4j_uri, neo4j_user, neo4j_password)
            self.adapter = Neo4jAdapter(self.connection)
            self._owns_connection = True
        
        # Initialize repository
        self.normativa_repo = EUNormativaRepository(self.adapter)
    
    def process_normativa(self, normativa: EUNormativa) -> EUGraphConstructionResult:
        """Process and persist an EU normativa document."""
        
        # Save document structure
        save_result = self.normativa_repo.save_normativa(normativa)
        
        step_logger.info(
            f"[EUGraphConstruction] Saved '{save_result['normativa_title'][:50]}...': "
            f"{save_result['nodes_created']} nodes, "
            f"{save_result['relationships_created']} relationships"
        )
        
        # Add tracing attributes if available
        if _tracer:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("eu_graph.doc_id", save_result["doc_id"])
                current_span.set_attribute("eu_graph.normativa_title", save_result["normativa_title"])
                current_span.set_attribute("eu_graph.nodes_created", save_result["nodes_created"])
                current_span.set_attribute("eu_graph.relationships_created", save_result["relationships_created"])
                current_span.set_attribute("eu_graph.eurovoc_count", save_result.get("eurovoc_count", 0))
        
        return EUGraphConstructionResult(
            doc_id=save_result["doc_id"],
            normativa_title=save_result["normativa_title"],
            nodes_created=save_result["nodes_created"],
            relationships_created=save_result["relationships_created"],
            eurovoc_count=save_result.get("eurovoc_count", 0)
        )
    
    def process(self, data) -> Optional[EUGraphConstructionResult]:
        """
        Process pipeline data.
        
        Expects:
            Tuple of (EUNormativa, change_events) or just EUNormativa
        """
        # Handle both tuple and direct normativa input
        if isinstance(data, tuple):
            normativa = data[0]
        else:
            normativa = data
        
        if normativa and isinstance(normativa, EUNormativa):
            try:
                return self.process_normativa(normativa)
            except Exception as e:
                step_logger.warning(f"Error in EUGraphConstruction step: {e}")
                raise
        else:
            step_logger.warning(f"Expected EUNormativa, got {type(normativa)}")
            return None
    
    def close(self):
        """Clean up resources."""
        if self._owns_connection and self.connection:
            self.connection.close()
