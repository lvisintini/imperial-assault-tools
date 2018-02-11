import os
from PIL import Image
from tqdm import tqdm


ASSETS_DIR = '/home/lvisintini/src/imperial-assault/templates/deployment-cards'
MIN_WIDTH = 476
MIN_HEIGHT = 740


def get_file_paths(root):
    for dir_path, _, file_names in os.walk(root):
        for f in file_names:
            yield os.path.join(dir_path, f)


def main():
    for abs_path in tqdm(list(get_file_paths(ASSETS_DIR))):
        img = Image.open(abs_path)
        img.thumbnail((MIN_WIDTH, MIN_HEIGHT), Image.ANTIALIAS)
        img.save(abs_path)


if __name__ == '__main__':
    main()
