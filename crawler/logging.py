import copy

import scrapy.utils.log
from colorlog import ColoredFormatter

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

_get_handler = copy.copy(scrapy.utils.log._get_handler)


def _get_handler_custom(*args, **kwargs):
    handler = _get_handler(*args, **kwargs)
    handler.setFormatter(color_formatter)
    return handler


def monkey_patch():
    scrapy.utils.log._get_handler = _get_handler_custom
