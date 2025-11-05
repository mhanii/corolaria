from pipeline import Step
from utils.http_client import BOEHTTPClient
class DataFinder(Step):
    def __init__(self, name: str, search_criteria: str = "default"): # For now you must specify the id.
        super().__init__(name)
        self.search_criteria = search_criteria
        self.client = BOEHTTPClient()
        
    
    def process(self, data):
        return self.client.get_law_by_id(self.search_criteria)