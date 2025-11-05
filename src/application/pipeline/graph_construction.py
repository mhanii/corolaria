# application/pipelines/graph_construction.py
from typing import List
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

    def process_normativa(self, normativa: NormativaCons, change_events:List[ChangeEvent]):
        """Process and persist a normativa document"""
        # Save main document structure
        doc_id = self.normativa_repo.save_normativa(normativa)


        # Save change events
        # for change_event in change_events:
        #     self.change_repo.save_change_event(change_event)

        return doc_id


    def process(self, data):
        normativa, change_events = data

        # print(normativa)
        if normativa:
            try:
                return self.process_normativa(normativa=normativa,change_events=change_events)
            except Exception as e:
                step_logger.warning(f"Error in GraphConstruction step: {e}")
                return None
        else:
            step_logger.warning("Normativa is empty")
            return None

    def close(self):
        self.connection.close()