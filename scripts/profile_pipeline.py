import cProfile
import pstats
import os
import sys
import logging
from memory_profiler import profile
import psutil

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import main

output_logger = logging.getLogger("output_logger")

# Create a file stream for the memory profiler
log_file = open("output/memory_profile.log", "w+")

@profile(stream=log_file)
def main_profile():
    main()

def profile_pipeline():
    # Create output directory if it doesn't exist
    os.makedirs("output", exist_ok=True)

    # --- Time Profiling ---
    profiler = cProfile.Profile()
    profiler.enable()

    # --- CPU Profiling (Initial) ---
    cpu_before = psutil.cpu_percent(interval=None)

    main_profile()

    # --- CPU Profiling (Final) ---
    cpu_after = psutil.cpu_percent(interval=None)

    profiler.disable()

    # --- Save All Stats to a File ---
    stats_file = "output/profile_stats.txt"
    with open(stats_file, "w") as f:
        # Time stats
        f.write("--- Execution Time (cProfile) ---\n")
        ps = pstats.Stats(profiler, stream=f)
        ps.sort_stats("cumulative")
        ps.print_stats()

        # CPU stats
        f.write("\n\n--- CPU Usage (psutil) ---\n")
        f.write(f"CPU Usage Before: {cpu_before}%\n")
        f.write(f"CPU Usage After: {cpu_after}%\n")

        # Memory stats
        f.write("\n\n--- Memory Usage (memory-profiler) ---\n")
        log_file.seek(0)
        f.write(log_file.read())

    log_file.close()

    # Clean up the separate memory log file
    os.remove("output/memory_profile.log")

    output_logger.info(f"Profiling stats saved to {stats_file}")

if __name__ == "__main__":
    profile_pipeline()
