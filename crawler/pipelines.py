# -*- coding: utf-8 -*-

import json
from collections import defaultdict
from crawler import items


class JsonWriterPipeline(object):
    file_names = {
        items.SourceItem: 'sources.json',
        items.SkirmishMapItem: 'skirmish-maps.json',
        items.AgendaCardItem: 'agenda-cards.json',
        items.CommandCardItem: 'command-cards.json',
        items.ConditionItem: 'condition-cards.json',
        items.DeploymentCardItem: 'deployment-cards.json',
        items.HeroItem: 'heroes.json',
        items.HeroClassCardItem: 'hero-class-cards.json',
        items.ImperialClassCardItem: 'imperial-class-cards.json',
        items.SupplyCardItem: 'supply-cards.json',
        items.StoryMissionCardItem: 'story-missions-cards.json',
        items.SideMissionCardItem: 'side-missions-cards.json',
        items.RewardItem: 'rewards-cards.json',
        items.Companion: 'companion-cards.json',
        items.UpgradeItem: 'upgrade-cards.json',
        items.CardBackItem: 'card-backs.json',
    }

    def __init__(self, *args, **kwargs):
        self.data = defaultdict(list)
        super().__init__(*args, **kwargs)

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        for cls, f in self.file_names.items():
            with open(f'./data/{f}', 'w') as file_object:
                json.dump(self.data[cls], file_object, indent=2)

    def process_item(self, item, spider):
        self.data[item.__class__].append(dict(item))

