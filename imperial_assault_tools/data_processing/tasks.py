import imghdr
import math
import os
import re
import struct
import subprocess
import time
import uuid

from assembly_line.task import Task

from collections import Counter, OrderedDict, defaultdict
from itertools import chain
from difflib import SequenceMatcher

import cv2
import numpy
from look_at.wmctrl import WmCtrl
from PIL import Image
from tqdm import tqdm
from imperial_assault_tools.data_processing import base_task
from imperial_assault_tools.data_processing.mixins import ShowImageMixin, RoundCornersMixin

from imperial_assault_tools.data_processing import contants


class ImageAppendChoiceDataCollector(ShowImageMixin, base_task.AppendChoiceDataCollector):
    pass


class ImageChoiceDataCollector(ShowImageMixin, base_task.ChoiceDataCollector):
    pass


class ImageIntegerDataCollector(ShowImageMixin, base_task.IntegerDataCollector):
    pass


class ImageTextDataCollector(ShowImageMixin, base_task.TextDataCollector):
    pass


class ImageBooleanChoiceDataCollector(ShowImageMixin, base_task.BooleanChoiceDataCollector):
    pass


class SourceContentsManyToMany(Task):
    def __init__(self, source, source_contents):
        super(SourceContentsManyToMany, self).__init__()
        self.source = source
        self.source_contents = source_contents

    def process(self, data_helper):
        for model in self.source.data:
            fks = model.get('source', [])
            fks = [fks, ] if not isinstance(fks, list) else fks
            pk = model['id']

            for fk in fks:
                self.source_contents.data.append(
                    OrderedDict([
                        (f'source_id', fk),
                        (f'content_type', self.source.source_name),
                        (f'content_id', pk),
                    ])
                )
        return data_helper


class DeDupLog(Task):
    source = None

    def __init__(self, source=None):
        super(DeDupLog, self).__init__()
        self.source = source or self.source

    def process(self, data_helper):
        hashes = []
        for model in data_helper.data[self.source]:
            hashes.append(model['hash'])

        duplicate_hashes = [h for h, c in Counter(hashes).items() if c > 1]

        for dh in duplicate_hashes:
            self.log.warning(dh)
        return data_helper


class LogTask(Task):
    source = None

    def __init__(self):
        super(LogTask, self).__init__()

    @classmethod
    def setup(cls, data_helper):
        data_helper.processed_images = []
        return data_helper

    @classmethod
    def process(cls, data_helper):
        for source in data_helper.dataset.as_list:
            if source.source_name == 'memory':
                continue
            for model in source.data:
                for image_attr in ['image', 'healthy', 'wounded']:
                    path = model.get(image_attr)
                    if path and path not in data_helper.processed_images:
                        cls.log.warning(path)
        return data_helper


class DeDupMerge(Task):
    source = None

    def __init__(self, source=None):
        super(DeDupMerge, self).__init__()
        self.source = source or self.source

    def process(self, data_helper):
        hashes = []
        for model in data_helper.data[self.source]:
            hashes.append(model['hash'])

        duplicate_hashes = [h for h, c in Counter(hashes).items() if c > 1]

        for dh in duplicate_hashes:
            sources = []
            images = []
            for model in [m for m in data_helper.data[self.source] if m['hash'] == dh]:
                if model['source'] not in sources:
                    sources.append(model['source'])
                if model['image_file'] not in images:
                    images.append(model['image_file'])

            for model in [m for m in data_helper.data[self.source] if m['hash'] == dh]:
                model['source'] = sources
                model['image_file'] = images

        for model in [m for m in data_helper.data[self.source] if m['hash'] not in duplicate_hashes]:
            model['source'] = [model['source'], ]
            model['image_file'] = [model['image_file'], ]

        new_collection = []
        deduped = []

        for model in data_helper.data[self.source]:
            if model['hash'] in duplicate_hashes:
                if model['hash'] not in deduped:
                    deduped.append(model['hash'])
                    new_collection.append(model)
            else:
                new_collection.append(model)

        data_helper.data[self.source] = new_collection

        return data_helper


class ChooseOne(base_task.ChoiceDataCollector):
    amend_data = True
    use_memory = True
    null_input = None
    skip_input = ''

    def __init__(self, *args, **kwargs):
        super(ChooseOne, self).__init__(*args, **kwargs)
        self.viewers = []
        self.active_window = WmCtrl().get_active_window()
        # This is because this lib is not python3 ready ...
        self.active_window.id = self.active_window.id.decode('utf-8')

    def pre_process_existing_value_to_prefill_input(self, value):
        return ''

    def before_each(self, model, data_helper):
        self.choices = [(x, x) for x in model[self.field_name]]

        if len(model[self.field_name]) > 1 and isinstance(model[self.field_name], list):
            for image in model[self.field_name]:
                self.viewers.append(subprocess.Popen(['eog', image]))
            time.sleep(0.25)
            self.active_window.activate()

    def after_each(self, model, data_helper):
        for p in self.viewers:
            p.terminate()
            p.kill()
        self.viewers = []

    def handle_input_loop(self, model):
        existing_data = self.field_name in model
        new_data = model.get(self.field_name, None)

        if isinstance(new_data, list):
            if len(new_data) == 1:
                new_data = self.clean_input('0')
                return True, new_data
        else:
            return False, None

        first = True

        while first or not self.validate_input(new_data):
            if not first:
                print('No. That value is not right!. Try again...')
            else:
                first = False

            new_data = self.prompt_user(model, new_data, existing_data)

            if self.skip_input is not None and new_data == self.skip_input:
                return False, None

            new_data = self.clean_input(new_data)

        else:
            return True, new_data


class RenameImages(Task):
    source = None
    file_attr = None
    attrs_for_path = []
    attrs_for_filename = []
    prefixes = []
    suffixes = []

    def __init__(self, read_path='.', write_path=None, source=None, file_attr=None, attrs_for_path=None, attrs_for_filename=None, prefixes=None, suffixes=None):
        super(RenameImages, self).__init__()
        self.read_path = read_path
        self.write_path = write_path or read_path
        self.source = source or self.source
        self.file_attr = file_attr or self.file_attr
        self.attrs_for_path = attrs_for_path or self.attrs_for_path
        self.attrs_for_filename = attrs_for_filename or self.attrs_for_filename
        self.prefixes = prefixes or self.prefixes
        self.suffixes = suffixes or self.suffixes

    def process(self, data_helper):
        for model in self.source.data:
            path_to_file = model[self.file_attr]

            read_root = os.path.join(data_helper.root, self.read_path)
            write_root = os.path.join(data_helper.root, self.write_path)

            new_path = os.path.join(
                write_root,
                self.slugify(self.source.source_name),
                *[self.slugify(str(model[a])) for a in self.attrs_for_path if model[a] is not None]
            )

            new_file_path = os.path.join(
                new_path,
                '-'.join(self.prefixes + self.get_additional_attrs(model) + self.suffixes) + '.png'
            )

            if not os.path.exists(new_path):
                os.makedirs(new_path)

            img = Image.open(os.path.join(read_root, path_to_file))
            img = img.convert("RGBA")
            img.save(new_file_path, "PNG", quality=100, optimize=True)

            model[self.file_attr] = new_file_path.replace(
                write_root if write_root.endswith('/') else write_root + '/', '', 1
            )

        return data_helper

    def slugify(self, string):
        value = re.sub('[^\w\s-]', '', string).strip().lower()
        return re.sub('[-\s]+', '-', value)

    def get_additional_attrs(self, model):
        words = []
        for a in self.attrs_for_filename:
            if a not in model:
                continue
            elif model[a] is None:
                continue
            elif model[a] is False:
                continue
            elif model[a] is True:
                if a == 'elite' and not model['unique']:
                    words.append(a)
            elif isinstance(model[a], str):
                words.append(model[a])
            elif isinstance(model[a], int):
                words.append(str(model[a]))
            elif a == 'modes':
                if set(model[a]) == set(contants.GAME_MODES.as_list):
                    continue
                words.extend(model[a])

        return [self.slugify(w) for w in words]


class ClassHeroRenameImages(RenameImages):
    def process(self, data_helper):
        for model in self.source.data:
            path_to_file = model[self.file_attr]

            hero_name = next(m for m in data_helper.data['heroes'] if m['id'] == model['hero'])['name']

            image_root = os.path.join(data_helper.root, self.path)

            new_path = os.path.join(
                image_root,
                self.slugify(self.source.source_name),
                *[self.slugify(str(model[a])) for a in self.attrs_for_path if model[a] is not None]
            )

            new_file_path = os.path.join(
                new_path,
                '-'.join(self.prefixes + [self.slugify(hero_name), ] + [
                    self.slugify(str(model[a])) for a in self.attrs_for_filename if model[a] is not None
                ] + self.suffixes) + '.png'
            )

            if not os.path.exists(new_path):
                os.makedirs(new_path)

            img = Image.open(path_to_file)
            img = img.convert("RGBA")
            img.save(new_file_path, "PNG", quality=100, optimize=True)

            model[self.file_attr] = new_file_path.replace(
                image_root if image_root.endswith('/') else image_root + '/', '', 1
            )

        return data_helper


class ImperialClassCardToClass(Task):
    def __init__(self, initial=None, card_source=None, class_source=None):
        super(ImperialClassCardToClass, self).__init__()
        self.initial = initial or {}
        self.class_source = class_source
        self.card_source = card_source

    def process(self, data_helper):
        done = []
        id_inc = self.initial["imperial-classes"]

        for card in self.card_source.data:
            if card['class'] not in done:
                id_inc += 1
                self.class_source.data.append(
                    OrderedDict([
                        ('id', id_inc),
                        ('name', card['class']),
                        ('source', card['source']),
                    ])
                )
                done.append(card['class'])

            card['class_id'] = next(
                iclass
                for iclass in self.class_source.data
                if iclass['name'] == card['class']
            )['id']

        return data_helper


class AgendaCardToDeck(Task):
    def __init__(self, initial=None, agenda_source=None, deck_source=None):
        super(AgendaCardToDeck, self).__init__()
        self.initial = initial or {}
        self.agenda_source = agenda_source
        self.deck_source = deck_source

    def process(self, data_helper):
        done = []
        id_inc = self.initial["agenda-decks"]

        for card in self.agenda_source.data:
            if card['agenda'] not in done:
                id_inc += 1
                self.deck_source.data.append(
                    OrderedDict([
                        ('id', id_inc),
                        ('name', card['agenda']),
                        ('source', card['source']),
                    ])
                )
                done.append(card['agenda'])

            card['agenda_id'] = next(
                iclass
                for iclass in self.deck_source.data
                if iclass['name'] == card['agenda']
            )['id']

        return data_helper


class CollectSources(ImageChoiceDataCollector):
    field_name = 'source'

    def pre_process(self, data_helper):
        self.choices = [(x['id'], x['name']) for x in data_helper.data[contants.SOURCES.SOURCE]]
        return data_helper


class StandardImageDimension(Task):
    sources = None
    path = '.'
    image_attrs = []
    filter_function = None
    canvas_to_size = False

    def __init__(self, path=None, sources=None, image_attrs=None, min_width=None, min_height=None, filter_function=None, canvas_to_size=False):
        super(StandardImageDimension, self).__init__()
        self.path = path or self.path
        self.sources = sources or self.sources
        self.image_attrs = image_attrs or self.image_attrs

        self.min_width = min_width
        self.min_height = min_height
        self.filter_function = filter_function or self.filter_function
        self.canvas_to_size = canvas_to_size or self.canvas_to_size

    def get_dimensions_summary(self, data_helper, log_results=True):
        widths = []
        heights = []
        for source in self.sources:
            for model in [m for m in source.data if self.filter(m)]:
                for attr in self.image_attrs:
                    path = model.get(attr, None)
                    if path is None:
                        continue
                    width, height = self.get_image_size(os.path.join(data_helper.root, self.path, path))
                    widths.append(width)
                    heights.append(height)
        summary = {}

        if widths and heights:
            summary['max_width'] = max(widths)
            summary['min_width'] = min(widths)
            summary['max_height'] = max(heights)
            summary['min_height'] = min(heights)
            if log_results:
                self.log.info(f'Dimensions for sources={self.sources!r} and image_attrs={self.image_attrs!r}')
                self.log.info(f'Max width: {summary["max_width"]}')
                self.log.info(f'Min width: {summary["min_width"]}')
                self.log.info(f'Max height: {summary["max_height"]}')
                self.log.info(f'Min height: {summary["min_height"]}')

        return summary

    def pre_process(self, data_helper):
        summary = self.get_dimensions_summary(data_helper, log_results=False)

        if self.min_width is None and summary:
            self.min_width = summary["min_width"]
        if self.min_height is None and summary:
            self.min_height = summary["min_height"]
        return data_helper

    def post_process(self, data_helper):
        self.get_dimensions_summary(data_helper, log_results=True)
        return data_helper

    def filter(self, model):
        if self.filter_function is None:
            return True
        return self.filter_function(model)

    def process(self, data_helper):
        if self.min_width and self.min_height:

            for source in tqdm(self.sources):
                for model in tqdm([m for m in source.data if self.filter(m)]):
                    for attr in self.image_attrs:
                        path = model.get(attr, None)
                        if path is not None:
                            read_path = os.path.join(data_helper.root, self.path, path)
                            write_path = read_path
                            im = Image.open(read_path)
                            im = im.convert("RGBA")
                            im.thumbnail((self.min_width, self.min_height), Image.ANTIALIAS)
                            im.save(write_path)
                            if self.canvas_to_size:
                                old_width, old_height = im.size
                                x1 = int(math.floor((self.min_width - old_width) / 2))
                                y1 = int(math.floor((self.min_height - old_height) / 2))
                                new_image = Image.new(im.mode, (self.min_width, self.min_height))
                                new_image.paste(im, (x1, y1, x1 + old_width, y1 + old_height))
                                new_image.save(write_path)
                            else:
                                im.save(write_path)
        else:
            self.log.error('No dimensions found for images')
        return data_helper

    @staticmethod
    def get_image_size(fname):
        # https://stackoverflow.com/questions/8032642/how-to-obtain-image-size-using-standard-python-class-without-using-external-lib/20380514#20380514
        with open(fname, 'rb') as fhandle:
            head = fhandle.read(24)
            if len(head) != 24:
                return
            if imghdr.what(fname) == 'png':
                check = struct.unpack('>i', head[4:8])[0]
                if check != 0x0d0a1a0a:
                    return
                width, height = struct.unpack('>ii', head[16:24])
            elif imghdr.what(fname) == 'gif':
                width, height = struct.unpack('<HH', head[6:10])
            elif imghdr.what(fname) == 'jpeg':
                try:
                    fhandle.seek(0) # Read 0xff next
                    size = 2
                    ftype = 0
                    while not 0xc0 <= ftype <= 0xcf:
                        fhandle.seek(size, 1)
                        byte = fhandle.read(1)
                        while ord(byte) == 0xff:
                            byte = fhandle.read(1)
                        ftype = ord(byte)
                        size = struct.unpack('>H', fhandle.read(2))[0] - 2
                    # We are at a SOFn block
                    fhandle.seek(1, 1)  # Skip `precision' byte.
                    height, width = struct.unpack('>HH', fhandle.read(4))
                except Exception:  #IGNORE:W0703
                    return
            else:
                return
            return width, height


class RoundCornersTask(RoundCornersMixin, Task):
    source = None
    image_attr = None

    def __init__(self, source=None, image_attr=None, filter_function=None, read_path='.', write_path=None, **kwargs):
        super().__init__(**kwargs)
        self.source = source or self.source
        self.image_attr = image_attr or self.image_attr
        self.filter_function = filter_function or self.filter_function
        self.read_path = read_path
        self.write_path = write_path or self.read_path

    def filter(self, model):
        if self.image_attr not in model:
            return False

        if self.filter_function is None:
            return True

        return self.filter_function(model)

    def process(self, data_helper):
        for model in tqdm([m for m in self.source.data if self.filter(m)], desc='Rounding Corner'):
            image_path = model.get(self.image_attr, None)
            if image_path is not None and self.radius and self.opacity:
                im = Image.open(self.get_read_path(data_helper.root, image_path))
                im = im.convert("RGBA")
                if self.radius and self.opacity:
                    self.round_image(im, radius=self.radius, opacity=self.opacity)
                im.save(self.get_write_path(data_helper.root, image_path))

            data_helper.processed_images.append(model[self.image_attr])

        return data_helper

    def get_read_path(self, root, image_path):
        abs_path = os.path.abspath(os.path.join(root, self.read_path, image_path))
        if not os.path.exists(abs_path):
            raise Exception(f'File path does not exists: {abs_path}')
        return abs_path

    def get_write_path(self, root, image_path, create_path=True):
        abs_path = os.path.abspath(os.path.join(root, self.write_path, image_path))

        directory, filename = os.path.split(abs_path)

        if create_path:
            if not os.path.exists(directory):
                os.makedirs(directory)

        return abs_path


class OpenCVSTask(Task):
    source = None
    image_attr = None
    filter_function = None

    def __init__(self, source=None, image_attr=None, filter_function=None, read_path='.', write_path=None):
        super(OpenCVSTask, self).__init__()
        self.source = source or self.source
        self.image_attr = image_attr or self.image_attr
        self.filter_function = filter_function or self.filter_function
        self.read_path = read_path
        self.write_path = write_path or self.read_path

    def get_read_path(self, root, image_path):
        abs_path = os.path.abspath(os.path.join(root, self.read_path, image_path))
        if not os.path.exists(abs_path):
            raise Exception(f'File path does not exists: {abs_path}')
        return abs_path

    def get_write_path(self, root, image_path, create_path=True):
        abs_path = os.path.abspath(os.path.join(root, self.write_path, image_path))

        if not os.path.exists(os.path.split(abs_path)[0]) and create_path:
            os.makedirs(os.path.split(abs_path)[0])

        return abs_path

    def filter(self, model):
        if self.image_attr not in model:
            return False

        if self.filter_function is None:
            return True

        return self.filter_function(model)

    def before_each(self, model, data_helper):
        return data_helper

    def after_each(self, model, data_helper):
        data_helper.processed_images.append(model[self.image_attr])
        return data_helper

    def process(self, data_helper):
        for model in tqdm([m for m in self.source.data if self.filter(m)], desc='OpenCV process'):

            data_helper = self.before_each(model, data_helper)
            self.log.info(repr(model))
            self.opencv_processing(data_helper.root, model[self.image_attr])
            data_helper = self.after_each(model, data_helper)
        return data_helper

    def opencv_processing(self, root, image_path):
        raise NotImplementedError


class CopyTask(Task):
    image_attrs = []
    filter_function = None

    def __init__(self, dataset, image_attrs=None, filter_function=None, read_path='.', write_path=None):
        super(CopyTask, self).__init__()
        self.dataset = dataset
        self.image_attrs = image_attrs or self.image_attrs
        self.filter_function = filter_function or self.filter_function
        self.read_path = read_path
        self.write_path = write_path or self.read_path

    def get_read_path(self, root, image_path):
        abs_path = os.path.abspath(os.path.join(root, self.read_path, image_path))
        if not os.path.exists(abs_path):
            raise Exception(f'File path does not exists: {abs_path}')
        return abs_path

    def get_write_path(self, root, image_path, create_path=True):
        abs_path = os.path.abspath(os.path.join(root, self.write_path, image_path))

        if not os.path.exists(os.path.split(abs_path)[0]) and create_path:
            os.makedirs(os.path.split(abs_path)[0])

        return abs_path

    def filter(self, model, image_attr):
        if image_attr not in model:
            return False

        if self.filter_function is None:
            return True

        return self.filter_function(model)

    def process(self, data_helper):
        for source in self.dataset.as_list:
            for image_attr in self.image_attrs:
                for model in [m for m in source.data if self.filter(m, image_attr)]:
                    im = Image.open(self.get_read_path(data_helper.root, model[image_attr]))
                    im.save(self.get_write_path(data_helper.root, model[image_attr]))
        return data_helper


class OpenCVContours(OpenCVSTask):
    def opencv_processing(self, root, image_path):
        # http://opencv-python-tutroals.readthedocs.io/en/latest/py_tutorials/py_imgproc/py_contours/py_contours_begin/py_contours_begin.html?highlight=canny
        img = cv2.imread(self.get_read_path(root, image_path), cv2.IMREAD_UNCHANGED)
        gray = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)

        # liked this 2
        # blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        # edges = cv2.Canny(blurred, 100, 150)

        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = self.auto_canny(blurred)

        image, contours, hierarchy = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        cv2.drawContours(img, contours, -1, (0, 0, 0, 255), 1)

        cv2.imwrite(self.get_write_path(root, image_path), image, [cv2.IMWRITE_PNG_COMPRESSION, 0])

    def auto_canny(self, image, sigma=0.33):
        # https://www.pyimagesearch.com/2015/04/06/zero-parameter-automatic-canny-edge-detection-with-python-and-opencv/
        # compute the median of the single channel pixel intensities
        v = numpy.median(image)

        # apply automatic Canny edge detection using the computed median
        lower = int(max(0, (1.0 - sigma) * v))
        upper = int(min(255, (1.0 + sigma) * v))
        edged = cv2.Canny(image, lower, upper)

        # return the edged image
        return edged


class OpenCVAlignImages(RoundCornersMixin, OpenCVSTask):

    def __init__(self, motion_type,  reference_image_path, **kwargs):
        super().__init__(**kwargs)

        # defines the motion type
        self.motion_type = motion_type

        self.reference_image_path = reference_image_path

        self.reference_image = None
        self.reference_image_gray = None
        self.reference_image_shape = None

    def pre_process(self, data_helper):
        self.reference_image = cv2.imread(os.path.join(data_helper.root, self.reference_image_path), cv2.IMREAD_UNCHANGED)
        self.reference_image_gray = cv2.cvtColor(self.reference_image, cv2.COLOR_RGBA2GRAY)
        self.reference_image_shape = self.reference_image.shape
        return data_helper

    def after_each(self, model, data_helper):
        super().after_each(model, data_helper)
        image_path = model.get(self.image_attr, None)
        if image_path is not None and self.radius and self.opacity:
            im = Image.open(self.get_write_path(data_helper.root, image_path))
            im = im.convert("RGBA")
            if self.radius and self.opacity:
                self.round_image(im, radius=self.radius, opacity=self.opacity)
            im.save(self.get_write_path(data_helper.root, image_path))

        return data_helper

    def opencv_processing(self, root, image_path):
        # https://www.learnopencv.com/image-alignment-ecc-in-opencv-c-python/
        if self.reference_image_path == image_path:
            im = cv2.imread(self.get_read_path(root, image_path), cv2.IMREAD_UNCHANGED)
            cv2.imwrite(self.get_write_path(root, image_path), im, [cv2.IMWRITE_PNG_COMPRESSION, 0])
            return

        # Read the images to be aligned
        img = cv2.imread(self.get_read_path(root, image_path), cv2.IMREAD_UNCHANGED)

        # Convert images to grayscale
        img_gray = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)

        # Define 2x3 or 3x3 matrices and initialize the matrix to identity
        if self.motion_type == cv2.MOTION_HOMOGRAPHY:
            warp_matrix = numpy.eye(3, 3, dtype=numpy.float32)
        else:
            warp_matrix = numpy.eye(2, 3, dtype=numpy.float32)

        # Specify the number of iterations.
        number_of_iterations = 5000

        # Specify the threshold of the increment
        # in the correlation coefficient between two iterations
        termination_eps = 1e-10

        # Define termination criteria
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, number_of_iterations, termination_eps)

        # Run the ECC algorithm. The results are stored in warp_matrix.
        (cc, warp_matrix) = cv2.findTransformECC(
            self.reference_image_gray, img_gray, warp_matrix, self.motion_type, criteria
        )

        if self.motion_type == cv2.MOTION_HOMOGRAPHY:
            # Use warpPerspective for Homography
            aligned_img = cv2.warpPerspective(
                img, warp_matrix, (self.reference_image_shape[1], self.reference_image_shape[0]),
                flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                borderMode=cv2.BORDER_CONSTANT, borderValue=[255, 255, 255, 0]
            )
        else:
            # Use warpAffine for Translation, Euclidean and Affine
            aligned_img = cv2.warpAffine(
                img, warp_matrix, (self.reference_image_shape[1], self.reference_image_shape[0]),
                flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                borderMode=cv2.BORDER_CONSTANT, borderValue=[255, 255, 255, 0]
            )

        cv2.imwrite(self.get_write_path(root, image_path), aligned_img, [cv2.IMWRITE_PNG_COMPRESSION, 0])


class OpenCVAlignImagesUsingCannyEdge(RoundCornersMixin, OpenCVSTask):

    def __init__(self, motion_type,  reference_image_path, **kwargs):
        self.sub_dir = kwargs.pop('sub_dir', str(uuid.uuid4()))

        super().__init__(**kwargs)
        self.timestamp = None

        # defines the motion type
        self.motion_type = motion_type

        self.reference_image_path = reference_image_path
        self.reference_image = None
        self.reference_image_gray = None
        self.reference_image_shape = None

    def after_each(self, model, data_helper):
        super().after_each(model, data_helper)
        image_path = model.get(self.image_attr, None)
        if image_path is not None and self.radius and self.opacity:
            im = Image.open(self.get_write_path(data_helper.root, image_path))
            im = im.convert("RGBA")
            if self.radius and self.opacity:
                self.round_image(im, radius=self.radius, opacity=self.opacity)
            im.save(self.get_write_path(data_helper.root, image_path))
        return data_helper

    def pre_process(self, data_helper):
        self.reference_image = cv2.imread(os.path.join(data_helper.root, self.reference_image_path), cv2.IMREAD_UNCHANGED)

        processed_image = cv2.cvtColor(self.reference_image, cv2.COLOR_RGBA2GRAY)
        processed_image = cv2.GaussianBlur(processed_image, (5, 5), 0)
        edges = self.auto_canny(processed_image)
        processed_image, contours, hierarchy = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        self.reference_image_gray = processed_image
        self.reference_image_shape = processed_image.shape
        return data_helper

    def opencv_processing(self, root, image_path):
        # https://www.learnopencv.com/image-alignment-ecc-in-opencv-c-python/

        if self.reference_image_path == image_path:
            im = cv2.imread(self.get_read_path(root, image_path), cv2.IMREAD_UNCHANGED)
            cv2.imwrite(self.get_write_path(root, image_path), im, [cv2.IMWRITE_PNG_COMPRESSION, 0])
            return

        # Read the images to be aligned
        img = cv2.imread(self.get_read_path(root, image_path), cv2.IMREAD_UNCHANGED)

        # Convert images to grayscale
        img_gray = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
        blurred = cv2.GaussianBlur(img_gray, (5, 5), 0)
        edges = self.auto_canny(blurred)

        processed_image, contours, hierarchy = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        # Define 2x3 or 3x3 matrices and initialize the matrix to identity
        if self.motion_type == cv2.MOTION_HOMOGRAPHY:
            warp_matrix = numpy.eye(3, 3, dtype=numpy.float32)
        else:
            warp_matrix = numpy.eye(2, 3, dtype=numpy.float32)

        # Specify the number of iterations.
        number_of_iterations = 5000

        # Specify the threshold of the increment
        # in the correlation coefficient between two iterations
        termination_eps = 1e-10

        # Define termination criteria
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, number_of_iterations, termination_eps)

        # Run the ECC algorithm. The results are stored in warp_matrix.
        (cc, warp_matrix) = cv2.findTransformECC(
            self.reference_image_gray, processed_image, warp_matrix, self.motion_type, criteria
        )

        if self.motion_type == cv2.MOTION_HOMOGRAPHY:
            # Use warpPerspective for Homography
            aligned_img = cv2.warpPerspective(
                img, warp_matrix, (self.reference_image_shape[1], self.reference_image_shape[0]),
                flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                borderMode=cv2.BORDER_CONSTANT, borderValue=[255, 255, 255, 0]
            )
        else:
            # Use warpAffine for Translation, Euclidean and Affine
            aligned_img = cv2.warpAffine(
                img, warp_matrix, (self.reference_image_shape[1], self.reference_image_shape[0]),
                flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                borderMode=cv2.BORDER_CONSTANT, borderValue=[255, 255, 255, 0]
            )

        cv2.imwrite(self.get_write_path(root, image_path), aligned_img, [cv2.IMWRITE_PNG_COMPRESSION, 0])

    def auto_canny(self, image, sigma=0.33):
        # https://www.pyimagesearch.com/2015/04/06/zero-parameter-automatic-canny-edge-detection-with-python-and-opencv/
        # compute the median of the single channel pixel intensities
        v = numpy.median(image)

        # apply automatic Canny edge detection using the computed median
        lower = int(max(0, (1.0 - sigma) * v))
        upper = int(min(255, (1.0 + sigma) * v))
        edged = cv2.Canny(image, lower, upper)

        # return the edged image
        return edged


class AddCanonicalNames(Task):
    def __init__(self, sources, *strategies):
        self.sources = sources
        self.strategies = strategies
        print(self.strategies)
        super(AddCanonicalNames, self).__init__()

    def process(self, data_helper):

        generated_canonical = []
        canonical_dedup = defaultdict(list)

        for model in chain(*[s.data for s in self.sources]):
            canonical_dedup[''].append(model)
            model['canonical'] = ''

        for strategy_id in range(len(self.strategies)):
            strategy = self.strategies[strategy_id]
            new_canonical_dedup = defaultdict(list)

            for candidate in canonical_dedup.keys():
                if len(canonical_dedup[candidate]) > 1:
                    for model in canonical_dedup[candidate]:
                        new_canonical_dedup[self.make_canonical_name(model, *strategy)].append(model)
                else:
                    canonical_dedup[candidate][0]['canonical'] = candidate
                    generated_canonical.append((candidate, strategy_id))

            canonical_dedup = new_canonical_dedup

        for candidate in canonical_dedup.keys():
            if len(canonical_dedup[candidate]) > 1:
                for model in canonical_dedup[candidate]:
                    self.log.error(model)
            else:
                canonical_dedup[candidate][0]['canonical'] = candidate
                generated_canonical.append((candidate, len(self.strategies) - 1))

        data_helper.generated_canonical = [gc[0] for gc in generated_canonical]

        for model in chain(*[s.data for s in self.sources]):
            canonical = model.get('canonical')
            if not canonical:
                self.log.warning(model)

        for canonical, level in generated_canonical:
            if level > 2:
                self.log.info(canonical)

        return data_helper

    def make_canonical_name(self, model, *attrs_for_name):
        words = []
        for attr in attrs_for_name:
            if attr not in model:
                continue
            elif model[attr] is None:
                continue
            elif model[attr] is False:
                continue
            elif model[attr] is True:
                if attr == 'elite':
                    if not model.get('unique'):
                        words.append(attr)
                else:
                    words.append(attr)
            elif isinstance(model[attr], str):
                words.append(model[attr])
            elif isinstance(model[attr], int):
                words.append(str(model[attr]))
            elif attr == 'modes':
                if set(model[attr]) == set(contants.GAME_MODES.as_list):
                    continue
                words.extend(model[attr])

        canonical = re.sub(r'[\W_]+', '', ''.join(words)).strip().lower()

        return canonical


class IASkirmishCanonicalCheck(Task):

    def __init__(self, dataset):
        self.dataset = dataset
        super(IASkirmishCanonicalCheck, self).__init__()

    def process(self, data_helper):

        ia_canonical = [
            (m.get('card') or m.get('deployment'))['iaspecName']
            for m in chain(*[s.data for s in self.dataset.as_list])
        ]

        not_found = [iac for iac in ia_canonical if iac not in data_helper.generated_canonical]

        print('iaspec | proposed')
        print('------ | --------')

        for nf in not_found:
            candidates = [
                c for c in data_helper.generated_canonical
                if SequenceMatcher(None, nf, c).ratio() > 0.80 or nf in c
            ]
            print(f"{nf} | {', '.join(candidates) or 'None'}")

        return data_helper
