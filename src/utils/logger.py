import logging
import os

def setup_loggers():
    # Create output directory if it doesn't exist
    os.makedirs("output", exist_ok=True)

    # Configure the step logger
    step_logger = logging.getLogger("step_logger")
    step_logger.setLevel(logging.INFO)
    step_handler = logging.FileHandler("output/events.log")
    step_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    step_handler.setFormatter(step_formatter)
    step_logger.addHandler(step_handler)

    # Configure the normal printing logger
    output_logger = logging.getLogger("output_logger")
    output_logger.setLevel(logging.INFO)
    output_handler = logging.FileHandler("output/user_output.log")
    output_formatter = logging.Formatter('%(message)s')
    output_handler.setFormatter(output_formatter)
    output_logger.addHandler(output_handler)
