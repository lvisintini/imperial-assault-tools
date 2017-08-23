import subprocess
from normalize.base import ChoiceDataCollector
from normalize.contants import SOURCES, FACTIONS


class ShowImageMixin(object):

    def __init__(self, *args, **kwargs):
        super(ShowImageMixin, self).__init__(*args, **kwargs)
        self.viewer = None

    def before_each(self, model):
        print('Model -> {name!r}'.format(**model))
        self.viewer = subprocess.Popen(['eog', '--single-window', model['image_file']])

    def process(self, *args, **kwargs):
        res = super(ShowImageMixin, self).process(*args, **kwargs)
        if self.viewer:
            self.viewer.terminate()
            self.viewer.kill()
        return res


class DeploymentCardFactionDataCollector(ShowImageMixin, ChoiceDataCollector):
    choices = FACTIONS.as_choices
    source = SOURCES.DEPLOYMENT
    pk = 'id'
    field_name = 'faction'
