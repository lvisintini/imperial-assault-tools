import os
import struct
import imghdr
import re
import subprocess
import time
import uuid
from io import BytesIO
from collections import Counter, OrderedDict

import cv2
import numpy
from look_at.wmctrl import WmCtrl
from PIL import Image
from tqdm import tqdm

from normalize import base
from normalize.manager import Task
from normalize import contants


class ImageAppendChoiceDataCollector(base.ShowImageMixin, base.AppendChoiceDataCollector):
    pass


class ImageChoiceDataCollector(base.ShowImageMixin, base.ChoiceDataCollector):
    pass


class ImageIntegerDataCollector(base.ShowImageMixin, base.IntegerDataCollector):
    pass


class ImageTextDataCollector(base.ShowImageMixin, base.TextDataCollector):
    pass


class ImageBooleanChoiceDataCollector(base.ShowImageMixin, base.BooleanChoiceDataCollector):
    pass


class ForeignKeyBuilder(Task):
    source = None
    source_pk = 'id'
    fk_source = None
    fk_source_pk = 'id'
    fk_field_path = None
    id_name = 'source'
    fk_id_name = 'content'

    attrs_to_copy = []

    def __init__(self, source=None, source_pk=None, fk_source=None, fk_source_pk=None, fk_field_path=None, attrs_to_copy=None, id_name=None, fk_id_name=None):
        super(ForeignKeyBuilder, self).__init__()
        self.source = source or self.source
        self.source_pk = source_pk or self.source_pk
        self.fk_source = fk_source or self.fk_source
        self.fk_source_pk = fk_source_pk or self.fk_source_pk
        self.fk_field_path = fk_field_path or self.fk_field_path
        self.attrs_to_copy = attrs_to_copy or self.attrs_to_copy
        self.id_name = id_name or self.id_name
        self.fk_id_name = fk_id_name or self.fk_id_name

    def get_model_field(self, model, field_path):
        fk = model
        for path in field_path:
            fk = fk.get(path)
            if fk is None:
                break
        return fk

    def set_model_field(self, model, field_path, new_fk):
        current = model
        for path in field_path[:-1]:
            if path not in current:
                current[path] = {}
            current = current[path]
        current[field_path[-1]] = new_fk

    def process(self, data_helper):
        for fk_model in data_helper.data[self.fk_source]:
            fk = self.get_model_field(fk_model, self.fk_field_path)
            fks = [fk, ] if not isinstance(fk, list) else fk
            pk = fk_model[self.fk_source_pk]

            for fk in fks:
                data_helper.data[self.source].append(
                    OrderedDict([
                        (f'{self.id_name}_id', fk),
                        (f'{self.fk_id_name}_type', self.fk_source),
                        (f'{self.fk_id_name}_id', pk),
                    ] + [
                        (a, fk_model[a]) for a in self.attrs_to_copy
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


class ChooseOne(base.ChoiceDataCollector):
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
    root = None
    source = None
    file_attr = None
    attrs_for_path = []
    attrs_for_filename = []
    prefixes = []
    suffixes = []

    def __init__(self, root=None, source=None, file_attr=None, attrs_for_path=None, attrs_for_filename=None, prefixes=None, suffixes=None):
        super(RenameImages, self).__init__()
        self.root = root or self.root
        self.source = source or self.source
        self.file_attr = file_attr or self.file_attr
        self.attrs_for_path = attrs_for_path or self.attrs_for_path
        self.attrs_for_filename = attrs_for_filename or self.attrs_for_filename
        self.prefixes = prefixes or self.prefixes
        self.suffixes = suffixes or self.suffixes

    def process(self, data_helper):
        for model in data_helper.data[self.source]:
            path_to_file = model[self.file_attr]

            extension = path_to_file.split('.')[-1]

            new_path = os.path.join(
                self.root,
                self.slugify(self.source),
                *[self.slugify(str(model[a])) for a in self.attrs_for_path if model[a] is not None]
            )

            new_file_path = os.path.join(
                new_path,
                '-'.join(self.prefixes + self.get_additional_attrs(model) + self.suffixes) + f'.{extension}'
            )

            if not os.path.exists(new_path):
                os.makedirs(new_path)

            if os.path.exists(path_to_file):  # perhaps we have done this already.
                with open(path_to_file, 'rb') as origin:
                    file_obj = BytesIO(origin.read())

                with open(os.path.join(new_file_path), 'bw') as destination:
                    destination.write(file_obj.read())

            model[self.file_attr] = new_file_path.replace(
                self.root if self.root.endswith('/') else self.root + '/', '', 1
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


# RoundCorners -> https://raw.githubusercontent.com/firestrand/phatch/master/phatch/actions/round.py
# Images to PNG format
# Tinify

class ImagesToPNG(Task):
    @classmethod
    def process(self, data_helper):
        for source in data_helper.data:
            for model in data_helper.data[source]:
                if 'image_file' in model:
                    model['image_file'] = model['image_file'].replace('.jpg', '.png')
                if 'wounded_file' in model:
                    model['wounded_file'] = model['wounded_file'].replace('.jpg', '.png')
                if 'healthy_file' in model:
                    model['healthy_file'] = model['healthy_file'].replace('.jpg', '.png')
        return data_helper


class ClassHeroRenameImages(RenameImages):
    def process(self, data_helper):
        for model in data_helper.data[self.source]:
            path_to_file = model[self.file_attr]

            hero_name = next(m for m in data_helper.data['heroes'] if m['id'] == model['hero'])['name']

            extension = path_to_file.split('.')[-1]

            new_path = os.path.join(
                self.root,
                self.slugify(self.source),
                *[self.slugify(str(model[a])) for a in self.attrs_for_path if model[a] is not None]
            )

            new_file_path = os.path.join(
                new_path,
                '-'.join(self.prefixes + [self.slugify(hero_name), ] + [
                    self.slugify(str(model[a])) for a in self.attrs_for_filename if model[a] is not None
                ] + self.suffixes) + f'.{extension}'
            )

            if not os.path.exists(new_path):
                os.makedirs(new_path)

            if os.path.exists(path_to_file):  # perhaps we have done this already.
                with open(path_to_file, 'rb') as origin:
                    file_obj = BytesIO(origin.read())

                with open(os.path.join(new_file_path), 'bw') as destination:
                    destination.write(file_obj.read())

            model[self.file_attr] = new_file_path.replace(
                self.root if self.root.endswith('/') else self.root + '/', '', 1
            )

        return data_helper


class ImperialClassCardToClass(Task):
    @classmethod
    def process(self, data_helper):
        done = []
        id_inc = -1

        for card in data_helper.data[contants.SOURCES.IMPERIAL_CLASS_CARD]:
            if card['class'] not in done:
                id_inc += 1
                data_helper.data[contants.SOURCES.IMPERIAL_CLASSES].append(
                    OrderedDict([
                        ('id', id_inc),
                        ('name', card['class']),
                        ('source', card['source']),
                    ])
                )
                done.append(card['class'])

            card['class_id'] = next(
                iclass
                for iclass in data_helper.data[contants.SOURCES.IMPERIAL_CLASSES]
                if iclass['name'] == card['class']
            )['id']

        return data_helper


class AgendaCardToDeck(Task):
    @classmethod
    def process(cls, data_helper):
        done = []
        id_inc = -1

        for card in data_helper.data[contants.SOURCES.AGENDA]:
            if card['agenda'] not in done:
                id_inc += 1
                data_helper.data[contants.SOURCES.AGENDA_DECKS].append(
                    OrderedDict([
                        ('id', id_inc),
                        ('name', card['agenda']),
                        ('source', card['source']),
                    ])
                )
                done.append(card['agenda'])

            card['agenda_id'] = next(
                iclass
                for iclass in data_helper.data[contants.SOURCES.AGENDA_DECKS]
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
    root = '.'
    image_attrs = []

    def __init__(self, root=None, sources=None, image_attrs=None, min_width=None, min_height=None):
        super(StandardImageDimension, self).__init__()
        self.root = root or self.root
        self.sources = sources or self.sources
        self.image_attrs = image_attrs or self.image_attrs

        self.min_width = min_width
        self.min_height = min_height

    def get_dimensions_summary(self, data_helper):
        widths = []
        heights = []
        for source in self.sources:
            for model in data_helper.data[source]:
                for attr in self.image_attrs:
                    path = model.get(attr, None)
                    if path is None:
                        continue
                    width, height = self.get_image_size(os.path.join(self.root, path))
                    widths.append(width)
                    heights.append(height)
        summary = {}

        if widths and heights:
            summary['max_width'] = max(widths)
            summary['min_width'] = min(widths)
            summary['max_height'] = max(heights)
            summary['min_height'] = min(heights)

            self.log.info(f'Dimensions for sources={self.sources!r} and image_attrs={self.image_attrs!r}')
            self.log.info(f'Max width: {summary["max_width"]}')
            self.log.info(f'Min width: {summary["min_width"]}')
            self.log.info(f'Max height: {summary["max_height"]}')
            self.log.info(f'Min height: {summary["min_height"]}')

        return summary

    def pre_process(self, data_helper):
        summary = self.get_dimensions_summary(data_helper)

        if self.min_width is None:
            self.min_width = summary["min_width"]
        if self.min_height is None:
            self.min_height = summary["min_height"]
        return data_helper

    def post_process(self, data_helper):
        self.get_dimensions_summary(data_helper)
        return data_helper

    def process(self, data_helper):
        if self.min_width and self.min_height:

            for source in tqdm(self.sources):
                for model in tqdm(data_helper.data[source]):
                    for attr in self.image_attrs:
                        path = model.get(attr, None)
                        if path is not None:
                            im = Image.open(os.path.join(self.root, path))
                            im = im.convert("RGBA")
                            im.thumbnail((self.min_width, self.min_height), Image.ANTIALIAS)
                            im.save(os.path.join(self.root, path))
                            #old_width, old_height = im.size
                            #x1 = int(math.floor((self.min_width - old_width) / 2))
                            #y1 = int(math.floor((self.min_height - old_height) / 2))
                            #new_image = Image.new(im.mode, (self.min_width, self.min_height))
                            #new_image.paste(im, (x1, y1, x1 + old_width, y1 + old_height))
                            #new_image.save(os.path.join(self.root, path))
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


class OpenCVSTask(Task):
    source = None
    image_attr = None
    filter = None
    root = '.'
    destination_root = '.'
    filter_function = None

    def __init__(self, source=None, image_attr=None, filter_function=None, root=None, destination_root=None):
        super(OpenCVSTask, self).__init__()
        self.source = source or self.source
        self.image_attr = image_attr or self.image_attr
        self.filter_function = filter_function or self.filter_function
        self.root = root or self.root
        self.destination_root = destination_root or self.destination_root

    def get_read_path(self, image_path):
        abs_path = os.path.abspath(os.path.join(self.root, image_path))
        if not os.path.exists(abs_path):
            raise Exception(f'File path does not exists: {abs_path}')
        return abs_path

    def get_write_path(self, image_path, create_path=True):
        abs_path = os.path.abspath(os.path.join(self.destination_root, image_path))

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
        pass

    def process(self, data_helper):
        for model in tqdm([m for m in data_helper.data[self.source] if self.filter(m)], desc='Aligning images'):
            self.before_each(model, data_helper)
            self.log.info(repr(model))
            self.opencv_processing(model[self.image_attr])
        return data_helper

    def opencv_processing(self, model):
        raise NotImplementedError


class OpenCVAlignImages(OpenCVSTask):

    def __init__(self, reference_image_path, **kwargs):
        super().__init__(**kwargs)
        self.uuid = str(uuid.uuid4())
        self.reference_image_path = reference_image_path

        self.reference_image = cv2.imread(self.get_read_path(reference_image_path), cv2.IMREAD_UNCHANGED)
        self.reference_image_gray = cv2.cvtColor(self.reference_image, cv2.COLOR_RGBA2GRAY)
        self.reference_image_shape = self.reference_image.shape

    def get_write_path(self, image_path, create_path=True):
        abs_path = super().get_write_path(image_path, create_path=False)

        directory, filename = os.path.split(abs_path)

        result_destination_path = os.path.join(directory, self.uuid, 'aligned')
        original_destination_path = os.path.join(directory, self.uuid, 'not-aligned')

        if create_path:
            if not os.path.exists(result_destination_path):
                os.makedirs(result_destination_path)

            if not os.path.exists(original_destination_path):
                os.makedirs(original_destination_path)

        return os.path.join(result_destination_path, filename), os.path.join(original_destination_path, filename)

    def opencv_processing(self, image_path):
        # https://www.learnopencv.com/image-alignment-ecc-in-opencv-c-python/
        abs_path = self.get_read_path(image_path)

        if self.reference_image_path == image_path:
            result_destination_path, original_destination_path = self.get_write_path(image_path)

            im = cv2.imread(abs_path, cv2.IMREAD_UNCHANGED)

            cv2.imwrite(result_destination_path, im, [cv2.IMWRITE_PNG_COMPRESSION, 0])
            cv2.imwrite(original_destination_path, im, [cv2.IMWRITE_PNG_COMPRESSION, 0])
            return

        # Read the images to be aligned
        img = cv2.imread(os.path.abspath(os.path.join(self.root, image_path)), cv2.IMREAD_UNCHANGED)

        # Convert images to grayscale
        img_gray = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)

        # Define the motion model
        warp_mode = cv2.MOTION_AFFINE

        # Define 2x3 or 3x3 matrices and initialize the matrix to identity
        if warp_mode == cv2.MOTION_HOMOGRAPHY:
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
        (cc, warp_matrix) = cv2.findTransformECC(self.reference_image_gray, img_gray, warp_matrix, warp_mode, criteria)

        if warp_mode == cv2.MOTION_HOMOGRAPHY:
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

        result_destination_path, original_destination_path = self.get_write_path(image_path)

        cv2.imwrite(result_destination_path, aligned_img, [cv2.IMWRITE_PNG_COMPRESSION, 0])
        cv2.imwrite(original_destination_path, img, [cv2.IMWRITE_PNG_COMPRESSION, 0])
