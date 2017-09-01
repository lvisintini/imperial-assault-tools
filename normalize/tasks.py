import time
from look_at.wmctrl import WmCtrl
import subprocess
from normalize.base import IntegerDataCollector, ChoiceDataCollector, TextDataCollector, AppendChoiceDataCollector


class ShowImageMixin(object):

    def __init__(self, *args, **kwargs):
        super(ShowImageMixin, self).__init__(*args, **kwargs)
        self.viewers = []
        self.active_window = WmCtrl().get_active_window()
        # This is because this lib is not python3 ready ...
        self.active_window.id = self.active_window.id.decode('utf-8')

    def before_each(self, model):
        self.viewers.append(subprocess.Popen(['eog', '--single-window', model['image_file']]))
        time.sleep(0.25)
        self.active_window.activate()

    def process(self, *args, **kwargs):
        res = super(ShowImageMixin, self).process(*args, **kwargs)
        for p in self.viewers:
            p.terminate()
            p.kill()
        return res


class ImageAppendChoiceDataCollector(ShowImageMixin, AppendChoiceDataCollector):
    pass


class ImageChoiceDataCollector(ShowImageMixin, ChoiceDataCollector):
    pass


class ImageIntegerDataCollector(ShowImageMixin, IntegerDataCollector):
    pass


class ImageTextDataCollector(ShowImageMixin, TextDataCollector):
    pass
