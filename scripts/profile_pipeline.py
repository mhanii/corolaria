import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from memory_profiler import profile
import psutil
import time
from main import main

@profile(precision=4, stream=open('profiling_results.txt', 'w+'))
def run_pipeline():
    """
    Runs the main pipeline and profiles its memory and CPU usage.
    """
    start_time = time.time()
    process = psutil.Process()

    # Initial CPU and memory usage
    initial_cpu = process.cpu_percent(interval=None)
    initial_mem = process.memory_info().rss / 1024 / 1024  # in MB

    # Run the main function
    main()

    # Final CPU and memory usage
    final_cpu = process.cpu_percent(interval=None)
    final_mem = process.memory_info().rss / 1024 / 1024  # in MB

    end_time = time.time()
    elapsed_time = end_time - start_time

    with open('profiling_results.txt', 'a') as f:
        f.write(f"\\n--- Performance Stats ---\\n")
        f.write(f"Execution Time: {elapsed_time:.2f} seconds\\n")
        f.write(f"Initial CPU Usage: {initial_cpu}%\\n")
        f.write(f"Final CPU Usage: {final_cpu}%\\n")
        f.write(f"Initial Memory Usage: {initial_mem:.2f} MB\\n")
        f.write(f"Final Memory Usage: {final_mem:.2f} MB\\n")

if __name__ == "__main__":
    run_pipeline()
