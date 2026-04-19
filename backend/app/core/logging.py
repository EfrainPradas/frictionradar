import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


logger = logging.getLogger("friction_radar")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def setup_batch_logging(log_file: Path, level: int = logging.INFO) -> logging.Logger:
    """Configure a batch-specific logger that writes to both stdout and a file.

    Returns the configured logger. The file handler uses rotation (5MB, 3 backups).
    """
    batch_logger = logging.getLogger("batch_runner")
    batch_logger.setLevel(level)
    batch_logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    batch_logger.addHandler(stdout_handler)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        str(log_file), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    batch_logger.addHandler(file_handler)

    return batch_logger
