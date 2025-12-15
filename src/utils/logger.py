import logging
import os
import sys
from datetime import datetime

# Global loggers
step_logger = logging.getLogger('step_logger')
output_logger = logging.getLogger('output_logger')

def setup_loggers():
    """
    Configure the logging system for the ingestion pipeline.
    
    Sets up:
    1. Root logger: Captures all standard logging (INFO+) to console and events.log
    2. Error logging: Captures all ERROR+ logs to ingestion_errors.log
    3. Output logger: specialized logger for data dumps, isolated from root.
    """
    # Ensure output directory exists
    os.makedirs('output', exist_ok=True)
    
    # 1. Configure Root Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Clear existing handlers to avoid duplicates on reload
    if root_logger.handlers:
        root_logger.handlers.clear()

    # Formatter
    standard_formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(name)s - %(message)s')
    
    # Handlers for Root
    
    # A. Console Handler (INFO+)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(standard_formatter)
    root_logger.addHandler(console_handler)
    
    # B. Events File Handler (INFO+) - Detailed log of everything
    events_handler = logging.FileHandler('output/events.log', mode='a', encoding='utf-8')
    events_handler.setLevel(logging.INFO)
    events_handler.setFormatter(standard_formatter)
    root_logger.addHandler(events_handler)
    
    # C. Errors File Handler (ERROR+) - Separate error log
    errors_handler = logging.FileHandler('output/ingestion_errors.log', mode='a', encoding='utf-8')
    errors_handler.setLevel(logging.ERROR)
    errors_handler.setFormatter(standard_formatter)
    root_logger.addHandler(errors_handler)

    # 2. Configure Step Logger (Pipeline specific events)
    # It propagates to root (events.log), but we ALSO want a dedicated "ingestion.log"
    step_logger.setLevel(logging.INFO)
    
    # Dedicated ingestion log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ingestion_handler = logging.FileHandler(f'output/ingestion_{timestamp}.log', mode='w', encoding='utf-8')
    ingestion_handler.setLevel(logging.INFO)
    ingestion_handler.setFormatter(standard_formatter)
    step_logger.addHandler(ingestion_handler)

    # 3. Configure Output Logger (Data dumps)
    # User requested to silence this (no more output_xxx.log files with tree dumps).
    # We set it to WARNING so INFO logs (dumps) are ignored and no file is created.
    output_logger.setLevel(logging.WARNING)
    output_logger.propagate = False
    
    # Clear existing handlers
    if output_logger.handlers:
        output_logger.handlers.clear()
        
    # SILENCED: No file handler attached.
    # current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    # output_filename = f'output/output_{current_time}.log'
    # output_handler = logging.FileHandler(output_filename, mode='w', encoding='utf-8')
    # ...

    return step_logger, output_logger

# Helper to re-initialize if needed (e.g. from main)
def get_loggers():
    if not logging.getLogger().handlers:
        return setup_loggers()
    return step_logger, output_logger

# Initialize on import
step_logger, output_logger = setup_loggers()
