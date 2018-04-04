import os
from tqdm import tqdm
from normalize.tasks import OpenCVAlignImages
from normalize.contants import SOURCES
import cv2

ASSETS_DIR = '/home/lvisintini/src/imperial-assault-tools/conditions'
MIN_HEIGHT = 476
MIN_WIDTH = 740


def get_file_paths(root):
    for dir_path, _, file_names in os.walk(root):
        for f in file_names:
            yield os.path.join(dir_path, f)


def main():
    task = OpenCVAlignImages(cv2.MOTION_AFFINE, '../templates/card-backs/condition-focused.png', image_attr='image', source=SOURCES.CARD, root=ASSETS_DIR)
    task.pre_process(None)

    for abs_path in tqdm(list(get_file_paths(ASSETS_DIR))):
        task.opencv_processing(abs_path)


if __name__ == '__main__':
    main()
