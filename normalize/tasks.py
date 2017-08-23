import json
from io import BytesIO
from collections import OrderedDict
from normalize.manager import Task
from normalize.base import ChoiceDataCollector
from normalize.contants import SOURCES, FACTIONS
from PIL import Image


class ShowImageMixin:
    def print_model(self, model):
        Image.open(model['image_file']).show()
        print('Model -> {name!r}'.format(**model))


class DeploymentCardFaction(ShowImageMixin, ChoiceDataCollector):
    choices = FACTIONS.as_choices
    source = SOURCES.DEPLOYMENT
    pk = 'id'
    field_name = 'faction'
