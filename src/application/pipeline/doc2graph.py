from .base import Step, Pipeline
from .data_ingestion import DataRetriever
from .data_processing import DataProcessor
from .graph_construction import GraphConstruction
class Doc2Graph(Pipeline):
    def __init__(self, law_id: str):
        steps = [
            DataRetriever(name="data_retriever", search_criteria=law_id),
            DataProcessor(name="data_processor"),
            GraphConstruction(name="graph_contructrion")
            # Additional steps can be added here
        ]
        super().__init__(steps)




