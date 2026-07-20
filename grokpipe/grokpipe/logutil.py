"""Log ra màn hình + file run.log."""
from __future__ import annotations

import logging


def setup_logger(log_path: str) -> logging.Logger:
    logger = logging.getLogger("grokpipe")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s",
                            datefmt="%H:%M:%S")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s"))
    logger.addHandler(fh)

    return logger
