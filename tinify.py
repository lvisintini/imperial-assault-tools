import os
import tinify
from tqdm import tqdm
tinify.key = "ztlmPV5XG4sib4jGK5LYWX7X25hVhKhS"

ASSETS_DIR = '/home/lvisintini/src/imperial-assault/raw-images/'


def get_file_paths(root):
    for dir_path, _, file_names in os.walk(root):
        for f in file_names:
            yield os.path.join(dir_path, f)


def main():
    for abs_path in tqdm(list(get_file_paths(ASSETS_DIR))):
        source = tinify.from_file(abs_path)
        source.to_file(abs_path)


if __name__ == '__main__':
    main()
