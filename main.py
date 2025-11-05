from src.pipeline.doc2graph import Doc2Graph
from dataclasses import dataclass, asdict
import json
import logging
from src.utils.logger import setup_loggers
from src.pipeline.data_processor import DataProcessor

output_logger = logging.getLogger("output_logger")

def main():
    setup_loggers()
    law_id = "BOE-A-1978-31229"  # Example law ID
    pipeline = Doc2Graph(law_id)
    result = pipeline.run(None)  # Initial data is None

    # Find the DataProcessor step to access the content_tree
    for step in pipeline.steps:
        if isinstance(step, DataProcessor):
            step.print_summary(verbose=True)
            break

    # print(json.dumps(asdict(result)))  
    # print(result)

if __name__ == "__main__":
    main()
