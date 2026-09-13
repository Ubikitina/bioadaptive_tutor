import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """
    Crea un logger estructurado con formato consistente para todos los servicios.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(name)-18s | %(levelname)-7s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        logger.propagate = False

    return logger
