import os
import hashlib


ASSETS_DIR = '/home/lvisintini/raw-images-jpg'


def get_file_paths(root):
    for dir_path, _, file_names in os.walk(root):
        for f in file_names:
            yield os.path.join(dir_path, f)


def main():
    for abs_path in get_file_paths(ASSETS_DIR):
        with open(abs_path, 'rb') as image_file:
            data = image_file.read()
        sha512 = hashlib.sha512(data)
        print(sha512.hexdigest())


if __name__ == '__main__':
    main()
