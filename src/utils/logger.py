import logging
from datetime import datetime

def setup_loggers():
    # Create step_logger
    step_logger = logging.getLogger('step_logger')
    step_logger.setLevel(logging.INFO)
    
    # File Handler
    step_handler = logging.FileHandler('output/events.log')
    step_formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')
    step_handler.setFormatter(step_formatter)
    step_logger.addHandler(step_handler)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(step_formatter)
    step_logger.addHandler(console_handler)

    current_time = datetime.now()
    # Create output_logger
    output_logger = logging.getLogger('output_logger')
    output_logger.setLevel(logging.INFO)
    output_handler = logging.FileHandler(f'output/output_{current_time}.log')
    output_formatter = logging.Formatter('%(message)s')
    output_handler.setFormatter(output_formatter)
    output_logger.addHandler(output_handler)

    return step_logger, output_logger

step_logger, output_logger = setup_loggers()
