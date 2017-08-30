import time
from look_at.wmctrl import WmCtrl
import subprocess
from normalize.base import IntegerDataCollector, ChoiceDataCollector, TextDataCollector
from normalize.contants import SOURCES, FACTIONS


class ShowImageMixin(object):

    def __init__(self, *args, **kwargs):
        super(ShowImageMixin, self).__init__(*args, **kwargs)
        self.viewers = []
        self.active_window = WmCtrl().get_active_window()
        # This is because this lib is not python3 ready ...
        self.active_window.id = self.active_window.id.decode('utf-8')

    def before_each(self, model):
        print('Model -> {name!r}'.format(**model))
        self.viewers.append(subprocess.Popen(['eog', '--single-window', model['image_file']]))
        time.sleep(0.25)
        self.active_window.activate()

    def process(self, *args, **kwargs):
        res = super(ShowImageMixin, self).process(*args, **kwargs)
        for p in self.viewers:
            p.terminate()
            p.kill()
        return res


class ImageChoiceDataCollector(ShowImageMixin, ChoiceDataCollector):
    pass


class ImageIntegerDataCollector(ShowImageMixin, IntegerDataCollector):
    pass


class ImageTextDataCollector(ShowImageMixin, TextDataCollector):
    pass


class DeploymentCardFactionDataCollector(ShowImageMixin, ChoiceDataCollector):
    choices = FACTIONS.as_choices
    source = SOURCES.DEPLOYMENT
    pk = 'id'
    field_name = 'faction'


class DeploymentCardDataCollector(ShowImageMixin, ChoiceDataCollector):
    choices = FACTIONS.as_choices
    source = SOURCES.DEPLOYMENT
    pk = 'id'
    field_name = 'deployment_cost'

