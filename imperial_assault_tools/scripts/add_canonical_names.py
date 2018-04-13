import os

from assembly_line.manager import AssemblyLine

from imperial_assault_tools.sources import DataSet, SourceName, JSONCollectionSource, JSONNestedDictSource
from imperial_assault_tools.data_processing import tasks
from imperial_assault_tools.data_processing import base_task as base
from imperial_assault_tools.data_processing.contants import INITIAL_IDS

import cv2


class SOURCES(DataSet):
    source_class = JSONCollectionSource
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../imperial-assault-data/'))
    path = 'data'
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


class IASKIRMISH(DataSet):
    source_class = JSONCollectionSource
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../iaskirmish-data/'))
    path = '.'
    write_path = '.'
    extension = 'json'

    DEPLOYMENTS = SourceName('deployments')
    COMMAND = SourceName('commandcards')


class NormalizeImperialData(AssemblyLine):
    tasks = [
        base.FetchData(SOURCES),
        base.FetchData(IASKIRMISH),
        tasks.AddCanonicalNames(
            [SOURCES.DEPLOYMENT, SOURCES.COMMAND, SOURCES.COMPANION],
            ('name', ),
            ('elite', 'name'),
            ('elite', 'name', 'modes'),  # Riot troopers
            ('name', 'affiliation'),  # Boosk
            ('name', 'description'),  # Heroes like Luke Skywalker, temporary alliance
        ),
        tasks.IASkirmishCanonicalCheck(IASKIRMISH),
        base.SaveData(SOURCES),
    ]


def main():
    import datetime
    NormalizeImperialData(
        timestamp=datetime.datetime.now(),
        root=os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')),
        dataset=SOURCES
    ).run()


if __name__ == '__main__':
    main()
