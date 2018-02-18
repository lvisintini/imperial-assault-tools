import logging
import os

import tinify
from tqdm import tqdm
from colorlog import ColoredFormatter

tinify.key = "api-key-here"

ASSETS_DIR = '/home/lvisintini/src/imperial-assault-tools/final'


class TqdmHandler(logging.StreamHandler):
    def __init__(self):
        logging.StreamHandler.__init__(self)

    def emit(self, record):
        msg = self.format(record)
        tqdm.write(msg)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

ch = TqdmHandler()
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


def get_file_paths(root):
    for dir_path, _, file_names in os.walk(root):
        for f in file_names:
            yield os.path.join(dir_path, f)


def main():
    errors = []
    for abs_path in tqdm(list(get_file_paths(ASSETS_DIR))):
        logger.debug(abs_path.replace(ASSETS_DIR, './'))
        try:
            source = tinify.from_file(abs_path)
            source.to_file(abs_path)
        except Exception:
            logger.exception(f"Failed {abs_path.replace(ASSETS_DIR, './')}")
            errors.append(abs_path.replace(ASSETS_DIR, './'))
    for e in errors:
        print(e)


if __name__ == '__main__':
    main()
