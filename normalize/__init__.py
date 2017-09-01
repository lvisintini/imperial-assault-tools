import logging
from colorlog import ColoredFormatter

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

color_formatter = ColoredFormatter(
    datefmt='%y-%m-%d %H;%M:%S',
    log_colors={
        'DEBUG': 'blue',
        'INFO': 'cyan',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }
)
ch.setFormatter(color_formatter)

logger.addHandler(ch)
