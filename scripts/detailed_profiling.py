import sys
import os
import time
import psutil
from functools import wraps
import cProfile
import pstats

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.pipeline.doc2graph import Doc2Graph
from src.application.pipeline.base import Step

def create_profiling_wrapper(step_instance, original_method):
    """
    Creates a profiling wrapper for a specific method of a specific instance.
    """
    @wraps(original_method)
    def wrapper(*args, **kwargs):
        step_name = step_instance.name

        with open('detailed_profiling_results.txt', 'a') as f:
            f.write(f"--- Profiling Step: {step_name} ---\n")

            # Profiling setup
            process = psutil.Process()
            start_time = time.time()

            # Initial CPU and memory usage
            initial_cpu = process.cpu_percent(interval=None)
            initial_mem = process.memory_info().rss / 1024 / 1024  # in MB
            f.write(f"Initial Memory Usage: {initial_mem:.2f} MB\n")
            f.write(f"Initial CPU Usage: {initial_cpu}%\n")

            # Execute the original method
            result = original_method(*args, **kwargs)

            # Final CPU and memory usage
            final_cpu = process.cpu_percent(interval=None)
            final_mem = process.memory_info().rss / 1024 / 1024  # in MB
            end_time = time.time()
            elapsed_time = end_time - start_time

            f.write(f"Final Memory Usage: {final_mem:.2f} MB\n")
            f.write(f"Final CPU Usage: {final_cpu}%\n")
            f.write(f"Execution Time: {elapsed_time:.4f} seconds\n\n")

        return result
    return wrapper

def run_profiling():
    """
    Applies the profiling wrapper to each step in the pipeline and runs it.
    """
    # Clean up previous results
    if os.path.exists('detailed_profiling_results.txt'):
        os.remove('detailed_profiling_results.txt')
    if os.path.exists('cprofile_stats.txt'):
        os.remove('cprofile_stats.txt')

    law_id = "BOE-A-1995-25444"  # Example law ID
    pipeline = Doc2Graph(law_id)

    # Monkey-patch the 'process' method of each step
    for step in pipeline.steps:
        step.process = create_profiling_wrapper(step, step.process)

    # Run the pipeline
    pipeline.run(None)

def main():
    """
    Main function to run the profiling.
    """
    profiler = cProfile.Profile()
    profiler.enable()

    run_profiling()

    profiler.disable()

    with open('cprofile_stats.txt', 'w') as f:
        stats = pstats.Stats(profiler, stream=f)
        stats.sort_stats('cumulative')
        stats.print_stats()

if __name__ == "__main__":
    main()
