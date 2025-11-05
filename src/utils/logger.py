import logging

def setup_loggers():
    # Create step_logger
    step_logger = logging.getLogger('step_logger')
    step_logger.setLevel(logging.INFO)
    step_handler = logging.FileHandler('events.log')
    step_formatter = logging.Formatter('%(asctime)s - %(message)s')
    step_handler.setFormatter(step_formatter)
    step_logger.addHandler(step_handler)

    # Create output_logger
    output_logger = logging.getLogger('output_logger')
    output_logger.setLevel(logging.INFO)
    output_handler = logging.FileHandler('output.log')
    output_formatter = logging.Formatter('%(message)s')
    output_handler.setFormatter(output_formatter)
    output_logger.addHandler(output_handler)

    return step_logger, output_logger

step_logger, output_logger = setup_loggers()
