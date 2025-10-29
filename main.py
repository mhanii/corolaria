from src.pipeline.doc2graph import Doc2Graph
from dataclasses import dataclass, asdict
import json
def main():
    law_id = "BOE-A-1995-25444"  # Example law ID
    pipeline = Doc2Graph(law_id)
    result = pipeline.run(None)  # Initial data is None
    # print(json.dumps(asdict(result)))  
    # print(result)

if __name__ == "__main__":
    main()
