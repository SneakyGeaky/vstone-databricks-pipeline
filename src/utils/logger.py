import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Return a named logger that writes to stdout (shown in the Jobs run output).

    Safe to call repeatedly: notebook cells get re-run, and adding a handler
    every time would print each line twice, then three times. The handler is
    only attached the first time; later calls just update the level.

    A named logger is used instead of logging.basicConfig() because Databricks
    has already configured the root logger, which makes basicConfig a silent no-op.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    logger.propagate = False  # don't also emit through the root logger (avoids duplicates)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)

    return logger