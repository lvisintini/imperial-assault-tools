import os
from PIL import Image
from tqdm import tqdm
from normalize.tasks import RoundCornersMixin


ASSETS_DIR = '/home/lvisintini/src/imperial-assault-tools/missing_round_corners'
MIN_WIDTH = 657
MIN_HEIGHT = 424


class RoundCornersAll(RoundCornersMixin):
    pass


def get_file_paths(root):
    for dir_path, _, file_names in os.walk(root):
        for f in file_names:
            yield os.path.join(dir_path, f)


def main():
    helper = RoundCornersAll()
    for abs_path in tqdm(list(get_file_paths(ASSETS_DIR))):
        img = Image.open(abs_path)
        img = helper.round_image(img, radius=35)
        img.save(abs_path)


if __name__ == '__main__':
    main()
