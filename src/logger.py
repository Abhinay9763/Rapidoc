import logging
import os
import sys

def setup_logger():
    # Create logger
    logger = logging.getLogger("rapidoc")
    logger.setLevel(logging.DEBUG)

    # Prevent adding handlers multiple times
    if logger.handlers:
        return logger

    # Create formatters
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler
    log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'rapidoc.log')
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger

log = setup_logger()
