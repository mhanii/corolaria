
class Step:
    def __init__(self, name: str):
        self.name = name

    def process(self, data):
        raise NotImplementedError("Each step must implement the process method.")
    

class Pipeline:
    def __init__(self, steps):
        self.steps = steps
        self.results = {}

    def run(self, initial_input=None):
        data = initial_input
        for step in self.steps:
            # Pass the results dict to each step for custom input mapping
            data = step.process(data)
            self.results[step.name] = data
        return data

    def get_result(self, step_name):
        return self.results.get(step_name)