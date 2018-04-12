import os
import time

import numpy
import subprocess
from PIL import Image, ImageDraw
from look_at.wmctrl import WmCtrl


class ShowImageMixin:
    def __init__(self, *args, **kwargs):
        self.image_attr = kwargs.pop('image_attr')
        super().__init__(*args, **kwargs)
        self.viewers = []
        self.active_window = WmCtrl().get_active_window()
        # This is because this lib is not python3 ready ...
        self.active_window.id = self.active_window.id.decode('utf-8')

    def show_image(self, image_path):
        if image_path:
            self.viewers.append(subprocess.Popen(['eog', '--single-window', image_path]))
            time.sleep(0.25)
            self.active_window.activate()
        else:
            self.close_viewers()

    def close_viewers(self):
        for p in self.viewers:
            p.terminate()
            p.kill()
        self.viewers = []

    def before_each(self, model, data_helper):
        if hasattr(self, 'image_attr') and self.image_attr in model:
            self.show_image(os.path.join(data_helper.root, 'raw-images', model[self.image_attr]))
        if hasattr(self, 'before_each'):
            data_helper = super().before_each(model, data_helper)
        return data_helper

    def process(self, *args, **kwargs):
        res = super().process(*args, **kwargs)
        self.close_viewers()
        return res


class RoundCornersMixin:
    # RoundCorners -> https://raw.githubusercontent.com/firestrand/phatch/master/phatch/actions/round.py
    # tasks.RoundCorners(100, 255, root='./images', sources=[SOURCES.DEPLOYMENT, ], image_attrs=['image', ]),
    CROSS = 'Cross'
    ROUNDED = 'Rounded'
    SQUARE = 'Square'

    CORNERS = [ROUNDED, SQUARE, CROSS]
    CROSS_POS = (CROSS, CROSS, CROSS, CROSS)
    ROUNDED_POS = (ROUNDED, ROUNDED, ROUNDED, ROUNDED)

    def __init__(self, *args, **kwargs):
        self.radius = kwargs.pop('radius', None)
        self.opacity = kwargs.pop('opacity', 255)
        super(RoundCornersMixin, self).__init__(*args, **kwargs)

    def round_image(self, image, round_all=True, rounding_type=ROUNDED, radius=100, opacity=255, pos=ROUNDED_POS):
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        if round_all:
            pos = 4 * (rounding_type, )

        mask = self.create_rounded_rectangle(image.size, radius, opacity, pos)

        alpha_array = numpy.asarray(self.get_alpha(image))
        mask_array = numpy.asarray(mask)

        width, height = image.size
        new_alpha_array = numpy.zeros(shape=(height, width), dtype=numpy.uint8)

        for x in range(len(alpha_array)):
            for y in range(len(alpha_array[0])):
                new_alpha_array[x, y] = min(alpha_array[x, y], mask_array[x, y])

        # self.get_alpha(image).show('current_alpha')
        # mask.show('rounded_alpha')
        # Image.fromarray(new_alpha_array, 'L').show('New')

        image.putalpha(Image.fromarray(new_alpha_array, 'L'))
        return image

    def create_rounded_rectangle(self, size=(600, 400), radius=100, opacity=255, pos=ROUNDED_POS):
        # rounded_rectangle
        im_x, im_y = size

        cross = Image.new('L', size, 0)
        draw = ImageDraw.Draw(cross)
        draw.rectangle((radius, 0, im_x - radius, im_y), fill=opacity)
        draw.rectangle((0, radius, im_x, im_y - radius), fill=opacity)

        if pos == self.CROSS_POS:
            return cross

        corner = self.create_corner(radius, opacity)
        # rounded rectangle
        rectangle = Image.new('L', (radius, radius), 255)
        rounded_rectangle = cross.copy()
        for index, angle in enumerate(pos):
            if angle == self.CROSS:
                continue
            if angle == self.ROUNDED:
                element = corner
            else:
                element = rectangle
            if index % 2:
                x = im_x - radius
                element = element.transpose(Image.FLIP_LEFT_RIGHT)
            else:
                x = 0
            if index < 2:
                y = 0
            else:
                y = im_y - radius
                element = element.transpose(Image.FLIP_TOP_BOTTOM)
            rounded_rectangle.paste(element, (x, y))
        return rounded_rectangle

    @staticmethod
    def create_corner(radius=100, opacity=255, factor=2):
        corner = Image.new('L', (factor * radius, factor * radius), 0)
        draw = ImageDraw.Draw(corner)
        draw.pieslice((0, 0, 2 * factor * radius, 2 * factor * radius), 180, 270, fill=opacity)
        corner = corner.resize((radius, radius), Image.ANTIALIAS)
        return corner

    @staticmethod
    def remove_alpha(image):
        """Returns a copy of the image after removing the alpha band or
        transparency

        :param image: input image
        :type image: PIL image object
        :returns: the input image after removing the alpha band or transparency
        :rtype: PIL image object
        """
        if image.mode == 'RGBA':
            return image.convert('RGB')
        if image.mode == 'LA':
            return image.convert('L')
        if image.mode == 'P' and 'transparency' in image.info:
            img = image.convert('RGB')
            del img.info['transparency']
            return img
        return image

    @staticmethod
    def has_alpha(image):
        """Checks if the image has an alpha band.
        i.e. the image mode is either RGBA or LA.
        The transparency in the P mode doesn't count as an alpha band

        :param image: the image to check
        :type image: PIL image object
        :returns: True or False
        :rtype: boolean
        """
        return image.mode.endswith('A')

    def get_alpha(self, image):
        """Gets the image alpha band. Can handles P mode images with transpareny.
        Returns a band with all values set to 255 if no alpha band exists.

        :param image: input image
        :type image: PIL image object
        :returns: alpha as a band
        :rtype: single band image object
        """
        if self.has_alpha(image):
            return image.split()[-1]
        if image.mode == 'P' and 'transparency' in image.info:
            return image.convert('RGBA').split()[-1]
        # No alpha layer, create one.
        return Image.new('L', image.size, 255)
