import os

from assembly_line.manager import AssemblyLine

from imperial_assault_tools.sources import DataSet, SourceName, JSONCollectionSource, JSONNestedDictSource
from imperial_assault_tools.data_processing import tasks
from imperial_assault_tools.data_processing import base_task as base
from imperial_assault_tools.data_processing.contants import INITIAL_IDS

import cv2


class SOURCES(DataSet):
    source_class = JSONCollectionSource
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    path = 'raw-data'
    write_path = 'data'
    extension = 'json'

    FORM_CARDS = SourceName('form-cards')
    SOURCE = SourceName('sources')
    SOURCE_CONTENTS = SourceName('source-contents')
    SKIRMISH_MAP = SourceName('skirmish-maps')
    AGENDA = SourceName('agenda-cards')
    AGENDA_DECKS = SourceName('agenda-decks')
    COMMAND = SourceName('command-cards')
    CONDITION = SourceName('condition-cards')
    DEPLOYMENT = SourceName('deployment-cards')
    HERO = SourceName('heroes')
    HERO_CLASS = SourceName('hero-class-cards')
    IMPERIAL_CLASSES = SourceName('imperial-classes')
    IMPERIAL_CLASS_CARD = SourceName('imperial-class-cards')
    SUPPLY = SourceName('supply-cards')
    STORY_MISSION = SourceName('story-mission-cards')
    SIDE_MISSION = SourceName('side-mission-cards')
    REWARD = SourceName('reward-cards')
    COMPANION = SourceName('companion-cards')
    UPGRADE = SourceName('upgrade-cards')
    CARD = SourceName('card-backs')
    THREAT_MISSION = SourceName('threat-mission-cards')

    MEMORY = JSONNestedDictSource(
        root=os.path.abspath(os.path.join(os.path.dirname(__file__), '../../assets')),
        path='memory.json'
    )


class NormalizeImperialData(AssemblyLine):
    tasks = [
        base.FetchData(SOURCES),
        base.AddIds(source=SOURCES.COMMAND, initial=INITIAL_IDS),

        tasks.ImageIntegerDataCollector(field_name='cost', source=SOURCES.COMMAND, memory=SOURCES.MEMORY, image_attr='image_file'),
        tasks.ImageTextDataCollector(field_name='name', source=SOURCES.COMMAND, memory=SOURCES.MEMORY, image_attr='image_file'),
        tasks.ImageIntegerDataCollector(field_name='limit', source=SOURCES.COMMAND, memory=SOURCES.MEMORY, image_attr='image_file'),
        tasks.ImageChoiceDataCollector(field_name='template', source=SOURCES.COMMAND, choices=(('A', 'A'), ('B', 'B')), memory=SOURCES.MEMORY, image_attr='image_file'),

        base.SortDataByAttrs('name', 'cost', 'limit', source=SOURCES.COMMAND),
        base.SortDataKeys(source=SOURCES.COMMAND, preferred_order=['id', 'name', 'cost', 'limit']),

        tasks.SourceContentsManyToMany(SOURCES.COMMAND, SOURCES.SOURCE_CONTENTS),

        tasks.RenameImages(read_path='raw-images', write_path="images", source=SOURCES.COMMAND, file_attr='image_file', attrs_for_filename=['name', ]),

        base.RemoveField(field_name='hash', source=SOURCES.COMMAND),

        base.RemoveField(field_name='image', source=SOURCES.COMMAND),

        base.RenameField(field_name='image_file', source=SOURCES.COMMAND, new_name='image'),

        base.RemoveField(field_name='source', source=SOURCES.COMMAND),

        tasks.StandardImageDimension(path='images', min_width=424, min_height=657, sources=[SOURCES.COMMAND, ], image_attrs=['image', ]),

        tasks.OpenCVAlignImagesUsingCannyEdge(cv2.MOTION_AFFINE, 'assets/templates/command-cards/of-no-importance.png', image_attr='image', filter_function=lambda model: model['id'] != 198, source=SOURCES.COMMAND, read_path='images', radius=35),
        tasks.OpenCVAlignImages(cv2.MOTION_AFFINE, 'assets/templates/command-cards/of-no-importance.png', image_attr='image', filter_function=lambda model: model['id'] == 198, source=SOURCES.COMMAND, read_path='images', radius=35),

        base.RemoveField(field_name='template', source=SOURCES.COMMAND),

        tasks.CopyTask(SOURCES, read_path='images', write_path='high-res-images', image_attrs=['image', 'healthy', 'wounded']),

        tasks.StandardImageDimension(path='high-res-images', min_width=424, min_height=657, canvas_to_size=True, sources=[SOURCES.COMMAND], image_attrs=['image', ]),
        tasks.StandardImageDimension(path='images', canvas_to_size=True, min_height=454, min_width=293, sources=[SOURCES.COMMAND, ], image_attrs=['image', ]),

        base.SaveData(SOURCES),
        tasks.LogTask,
    ]


def main():
    import datetime
    NormalizeImperialData(
        timestamp=datetime.datetime.now(),
        root=SOURCES.root,
        dataset=SOURCES
    ).run()


if __name__ == '__main__':
    main()
