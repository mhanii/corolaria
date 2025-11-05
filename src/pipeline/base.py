
class Step:
    def __init__(self, name: str):
        self.name = name

    def process(self, data):
        raise NotImplementedError("Each step must implement the process method.")
    

import logging

step_logger = logging.getLogger("step_logger")

class Pipeline:
    def __init__(self, steps):
        self.steps = steps
        self.results = {}

    def run(self, initial_input=None):
        data = initial_input
        step_logger.info(f"Pipeline started.")
        for step in self.steps:
            step_logger.info(f"Step '{step.name}' started.")
            # Pass the results dict to each step for custom input mapping
            data = step.process(data)
            self.results[step.name] = data
            step_logger.info(f"Step '{step.name}' finished.")
        step_logger.info(f"Pipeline finished.")
        return data

    def get_result(self, step_name):
        return self.results.get(step_name)