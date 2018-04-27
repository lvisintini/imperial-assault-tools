import os

from assembly_line.manager import AssemblyLine

from imperial_assault_tools.sources import DataSet, SourceName, JSONCollectionSource, JSONNestedDictSource
from imperial_assault_tools.data_processing import tasks
from imperial_assault_tools.data_processing import base_task as base

import cv2


IASPEC_MAPPING = {
    "lukeskywalkerjedi": "lukeskywalkerjediknight",
    "lukeskywalker": "lukeskywalkerherooftherebellion",
    "leiaorgana": "leiaorganaskirmish",
    "obiwankenobi": "obiwankenobiskirmish",
    "r2d2": "r2d2skirmish",
    "furyofkashyyk": "furyofkashyyyk",
    "atst": "eliteatst",
    "sc2mrepulsortank": "elitesc2mrepulsortank",
    "atdp": "eliteatdp",
    "agentblaise": "agentblaiseskirmish",
    "dewbackrider": "elitedewbackrider",
    "riottrooper": "riottrooperskirmish",
    "crosstraining": "elitecrosstraining",
    "temporaryallianceempire": "temporaryallianceimperial",
    "rancor": "eliterancorskirmish",
    "bantharider": "elitebantharider",
    "bossk": "bosskmercenary",
    "jabbathehutt": "jabbathehuttskirmish",
    "elitejawascavenger": "elitejawascavengerskirmish",
    "tempoaryalliancescum": "temporaryalliancemercenary",
    "feedingfrenzy": "elitefeedingfrenzy",
    "sarlacsweep": "sarlaccsweep",
}


class SOURCES(DataSet):
    source_class = JSONCollectionSource
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../imperial-assault-data/'))
    path = 'data'
    write_path = 'data'
    extension = 'json'

    COMMAND = SourceName('command-cards')
    DEPLOYMENT = SourceName('deployment-cards')
    COMPANION = SourceName('companion-cards')

    MEMORY = JSONNestedDictSource(
        root=os.path.abspath(os.path.join(os.path.dirname(__file__), '../../assets')),
        path='memory.json'
    )
    MEMORY1 = JSONNestedDictSource(
        root=os.path.abspath(os.path.join(os.path.dirname(__file__), '../../assets')),
        path='memory1.json'
    )


class NormalizeImperialData(AssemblyLine):
    tasks = [
        base.FetchData(SOURCES),
        tasks.AddBetterImages(SOURCES, IASPEC_MAPPING),
        tasks.ChooseOne(field_name='image', source=SOURCES.DEPLOYMENT, read_path='images/large', memory=SOURCES.MEMORY),
        tasks.ChooseOne(field_name='image', source=SOURCES.COMMAND, read_path='images/large', memory=SOURCES.MEMORY),
        tasks.ChooseOne(field_name='image', source=SOURCES.COMPANION, read_path='images/large', memory=SOURCES.MEMORY),
        tasks.RenameImages(read_path='images/large', write_path="images/large", source=SOURCES.DEPLOYMENT, file_attr='image', attrs_for_filename=['name', 'description', 'elite', 'modes']),
        tasks.RenameImages(read_path='images/large', write_path="images/large", source=SOURCES.COMMAND, file_attr='image', attrs_for_filename=['name', ]),
        tasks.RenameImages(read_path='images/large', write_path="images/large", source=SOURCES.COMPANION, file_attr='image', attrs_for_filename=['name', ]),

        base.SaveData(SOURCES),

        tasks.StandardImageDimension(path='images/large', min_width=476, min_height=740, sources=[SOURCES.DEPLOYMENT, ], image_attrs=['image', ]),
        tasks.StandardImageDimension(path='images/large', min_width=424, min_height=657, sources=[SOURCES.COMMAND, ], image_attrs=['image', ]),

        tasks.OpenCVAlignImagesUsingCannyEdge(cv2.MOTION_AFFINE, '../imperial-assault-tools/assets/templates/command-cards/of-no-importance.png', image_attr='image', filter_function=lambda model: model['id'] in [9, 44, 55, 69, 119, 129, 144, 156], source=SOURCES.COMMAND, read_path='images/large'),
        tasks.OpenCVAlignImages(cv2.MOTION_AFFINE, '../imperial-assault-tools/assets/templates/deployment-cards/last-resort-skirmish.png', image_attr='image', filter_function=lambda model: model['id'] in [63, 82], source=SOURCES.DEPLOYMENT, read_path='images/large'),

        tasks.CopyTask(SOURCES, read_path='images/large', write_path='images/small', image_attrs=['image'], filter_function=lambda m: m['id'] in [63, 82] and 'limit' not in m),
        tasks.CopyTask(SOURCES, read_path='images/large', write_path='images/small', image_attrs=['image'], filter_function=lambda m: m['id'] in [9, 44, 55, 69, 119, 129, 144, 156] and 'limit' in m),

        tasks.StandardImageDimension(path='images/large', min_width=476, min_height=740, canvas_to_size=True, sources=[SOURCES.DEPLOYMENT, ], image_attrs=['image', ]),
        tasks.StandardImageDimension(path='images/large', min_width=424, min_height=657, canvas_to_size=True, sources=[SOURCES.COMMAND, ], image_attrs=['image', ]),

        tasks.TinyImages(SOURCES, read_path='images/large', write_path='images/large', image_attrs=['image'], filter_function=lambda m: m['id'] in [63, 82] and 'limit' not in m),
        tasks.TinyImages(SOURCES, read_path='images/large', write_path='images/large', image_attrs=['image'], filter_function=lambda m: m['id'] in [9, 44, 55, 69, 119, 129, 144, 156] and 'limit' in m),


        tasks.StandardImageDimension(path='images/small', min_width=301, min_height=470, canvas_to_size=True, sources=[SOURCES.DEPLOYMENT, ], image_attrs=['image', ]),
        tasks.StandardImageDimension(path='images/small', min_width=293, min_height=454, canvas_to_size=True, sources=[SOURCES.COMMAND, ], image_attrs=['image', ]),

        tasks.TinyImages(SOURCES, read_path='images/small', write_path='images/small', image_attrs=['image'], filter_function=lambda m: m['id'] in [63, 82] and 'limit' not in m),
        tasks.TinyImages(SOURCES, read_path='images/small', write_path='images/small', image_attrs=['image'], filter_function=lambda m: m['id'] in [9, 44, 55, 69, 119, 129, 144, 156] and 'limit' in m),
    ]


def main():
    import datetime
    NormalizeImperialData(
        timestamp=datetime.datetime.now(),
        root=os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../imperial-assault-data')),
        dataset=SOURCES
    ).run()


if __name__ == '__main__':
    main()
