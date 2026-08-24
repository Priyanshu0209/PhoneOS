import logging
import sys
from pathlib import Path

def setup_logger(name: str, log_file: str = None, level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a logger with standard formatting for SwarmOS.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate logs if setup_logger is called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler
    if log_file:
        from logging.handlers import RotatingFileHandler
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Max size 5MB, keep 3 backups
        fh = RotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=3)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger
