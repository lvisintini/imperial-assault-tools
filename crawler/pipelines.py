# -*- coding: utf-8 -*-

import json
from collections import defaultdict

from scrapy.exceptions import DropItem

from crawler import items


class FixTyposAndNormalizeTextPipeline(object):
    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        if item.__class__ == items.SourceItem:
            item['name'] = 'Imperial Assault' if item['name'] == 'Core Box' else item['name']
            item['name'] = item['name'].replace('Box', '').strip()
            item['name'] = "Jabba's Realm" if item['name'] == 'Jabbas-Realm' else item['name']

        elif item.__class__ == items.CardBackItem:
            item['deck'] = item['deck'][0:-1] if item['deck'].endswith('s') else item['deck']
            item['deck'] = item['deck'].replace('Heroe', 'Hero')
            item['deck'] = item['deck'].replace(' Deck', '')
            item['deck'] = item['deck'].replace(' Card', '')

        elif item.__class__ == items.AgendaCardItem:
            item['name'] = "Lord Vader's Command" if item['name'] == 'Lord Vaders Command' else item['name']

        return item


class FilterValidCardBacksPipeline(object):
    variant_required = [
        'Condition',
        'Imperial Class Deck',
        'Rebel Hero',
        'Rebel Upgrade',
        'Deployment Card',
        'Reward Card',

    ]

    def __init__(self):
        self.dedup_list = []

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        if item.__class__ == items.CardBackItem:
            if item['deck'] in self.variant_required and item.get('variant', None) is None:
                raise DropItem()

            dedup_tuple = (item['deck'],  item.get('variant', None))

            if dedup_tuple not in self.dedup_list:
                self.dedup_list.append(dedup_tuple)
            else:
                raise DropItem()

        return item


class FilterValidAgendasPipeline(object):
    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        if item.__class__ == items.AgendaCardItem:
            if item['name'].lower() == 'back':
                raise DropItem()
        return item


class AddSourceIdsPipeline(object):
    def __init__(self):
        self.inc_id = -1

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        if item.__class__ == items.SourceItem:
            self.inc_id += 1
            item['id'] = self.inc_id
        elif 'source' in item.fields:
            item['source'] = self.inc_id
        return item


class AddSourceImagesPipeline(object):
    images = {
        'Imperial Assault': '/cache/Core-Box/ia_core_box_275_thumb_ffflogog_whatermark_cc.png',
        "Jabba's Realm": '/cache/Expansion-Boxes/Jabbas-Realm/Jabbas%20Realm_275_thumb_ffflogog_whatermark_cc.png',
        'Twin Shadows': '/cache/Expansion-Boxes/Twin-Shadows/Twin%20Shadows_275_thumb_ffflogog_whatermark_cc.png',
        'Return to Hoth': '/cache/Expansion-Boxes/Return-to-Hoth/Return%20to%20Hoth_275_thumb_ffflogog_whatermark_cc.png',
        'The Bespin Gambit': '/cache/Expansion-Boxes/The-Bespin-Gambit/The%20Bespin%20Gambit_275_thumb_ffflogog_whatermark_cc.png',
    }

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        if item.__class__ == items.SourceItem and 'image' not in item:
            item['image'] = self.images[item['name']]
        return item


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

    def __init__(self):
        self.data = defaultdict(list)

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        for cls, f in self.file_names.items():
            with open(f'./data/{f}', 'w') as file_object:
                json.dump(self.data[cls], file_object, indent=2)

    def process_item(self, item, spider):
        self.data[item.__class__].append(dict(item))
        return item

