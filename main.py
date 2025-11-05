from time import perf_counter
from src.application.pipeline.doc2graph import Doc2Graph
from dataclasses import dataclass, asdict
import json
def main():
    law_id = "BOE-A-1995-25444"  # Example law ID
    pipeline = Doc2Graph(law_id)
    start = perf_counter()
    result = pipeline.run(None)
    end = perf_counter()
    elapsed_s = end - start
    # print(result)
    print(elapsed_s)

if __name__ == "__main__":
    main()
