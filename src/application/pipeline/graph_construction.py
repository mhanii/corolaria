# application/pipelines/graph_construction.py
from typing import List, Dict, Any, Optional
from src.domain.models.normativa import NormativaCons
from src.domain.repository.normativa_repository import NormativaRepository
from src.domain.repository.tree_repository import TreeRepository
from src.domain.repository.change_repository import ChangeRepository
from src.domain.services.change_handler import ChangeEvent
from src.infrastructure.graphdb.connection import Neo4jConnection
from src.infrastructure.graphdb.adapter import Neo4jAdapter
from .base import Step
from dotenv import load_dotenv
import os
from src.utils.logger import step_logger

# Import tracing (optional)
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("graph_construction")
except ImportError:
    _tracer = None


class GraphConstructionResult:
    """Result of graph construction with statistics."""
    
    def __init__(
        self, 
        doc_id: str,
        normativa_title: str,
        nodes_created: int = 0,
        relationships_created: int = 0,
        materias_count: int = 0
    ):
        self.doc_id = doc_id
        self.normativa_title = normativa_title
        self.nodes_created = nodes_created
        self.relationships_created = relationships_created
        self.materias_count = materias_count
    
    def __repr__(self):
        return (
            f"GraphConstructionResult(doc_id={self.doc_id!r}, "
            f"nodes={self.nodes_created}, rels={self.relationships_created})"
        )


class GraphConstruction(Step):
    def __init__(self, name: str, *args): 
        super().__init__(name)
        
        load_dotenv()

        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_user = os.getenv("NEO4J_USER")
        neo4j_password = os.getenv("NEO4J_PASSWORD")

        self.connection = Neo4jConnection(neo4j_uri, neo4j_user, neo4j_password)
        self.adapter = Neo4jAdapter(self.connection)
        
        # Initialize repositories
        self.normativa_repo = NormativaRepository(self.adapter)
        self.tree_repo = TreeRepository(self.adapter)
        self.change_repo = ChangeRepository(self.adapter)
    
    def process_normativa(self, normativa: NormativaCons, change_events: List[ChangeEvent]) -> GraphConstructionResult:
        """Process and persist a normativa document."""
        # Save main document structure - now returns detailed stats
        save_result = self.normativa_repo.save_normativa(normativa)
        
        # Log the statistics
        step_logger.info(
            f"[GraphConstruction] Saved '{save_result['normativa_title']}': "
            f"{save_result['nodes_created']} nodes, "
            f"{save_result['relationships_created']} relationships"
        )
        
        # Add tracing attributes if available
        if _tracer:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("graph.doc_id", save_result["doc_id"])
                current_span.set_attribute("graph.normativa_title", save_result["normativa_title"])
                current_span.set_attribute("graph.nodes_created", save_result["nodes_created"])
                current_span.set_attribute("graph.relationships_created", save_result["relationships_created"])
                current_span.set_attribute("graph.materias_count", save_result["materias_count"])
                current_span.set_attribute("graph.tree_nodes", save_result.get("tree_nodes", 0))
                current_span.set_attribute("graph.tree_relationships", save_result.get("tree_relationships", 0))
        
        return GraphConstructionResult(
            doc_id=save_result["doc_id"],
            normativa_title=save_result["normativa_title"],
            nodes_created=save_result["nodes_created"],
            relationships_created=save_result["relationships_created"],
            materias_count=save_result["materias_count"]
        )

    def process(self, data) -> Optional[GraphConstructionResult]:
        normativa, change_events = data

        if normativa:
            try:
                return self.process_normativa(normativa=normativa, change_events=change_events)
            except Exception as e:
                step_logger.warning(f"Error in GraphConstruction step: {e}")
                raise  # Re-raise to trigger rollback
        else:
            step_logger.warning("Normativa is empty")
            return None

    def close(self):
        self.connection.close()