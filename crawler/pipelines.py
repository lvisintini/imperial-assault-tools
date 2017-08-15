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

    @staticmethod
    def sources_rename(item, attr):
        item[attr] = 'Imperial Assault' if item[attr] == 'Core Box' else item[attr]
        item[attr] = item[attr].replace('Box', '').strip()
        item[attr] = "Jabba's Realm" if item[attr] == 'Jabbas-Realm' else item[attr]
        item[attr] = "Stormtroopers" if item[attr] == 'Stormtrooper' else item[attr]
        return item

    def process_item(self, item, spider):
        if item.__class__ == items.SourceItem:
            item = self.sources_rename(item, 'name')

        if item.__class__ != items.SourceItem and 'source' in item.fields:
            item = self.sources_rename(item, 'source')

        if item.__class__ == items.CardBackItem:
            item['deck'] = item['deck'][0:-1] if item['deck'].endswith('s') else item['deck']
            item['deck'] = item['deck'].replace('Heroe', 'Hero')
            item['deck'] = item['deck'].replace(' Deck', '')
            item['deck'] = item['deck'].replace(' Card', '')
            item['deck'] = "Agenda" if item['deck'] == "Agenda Set" else item['deck']
            if item['variant'] is not None:
                item = self.sources_rename(item, 'variant')

        if item.__class__ == items.AgendaCardItem:
            item['name'] = "Lord Vader's Command" if item['name'] == 'Lord Vaders Command' else item['name']
            item['agenda'] = "!!!!!!Stormtroopers" if item['agenda'] == '!!!!!!Stormtrooper' else item['agenda']

        if item.__class__ == items.CompanionItem:
            item['name'] = "Salacious B. Crumb" if item['name'] == "Salacious B Crumb" else item['name']
            item['name'] = "Pit Droid Companion" if item['name'] == "Pit Droid companion" else item['name']

        if item.__class__ == items.ConditionItem:
            item['name'] = item['name'].replace(' Condition', '')
        return item


class FilterValidCardBacksPipeline(object):
    variant_required = [
        'Condition',
        'Imperial Class',
        'Rebel Hero',
        'Rebel Upgrade',
        'Deployment',
        'Story Mission',
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


class RemoveBacksPipeline(object):
    classes = [
        items.CommandCardItem,
        items.RewardItem,
        items.CompanionItem,
        items.ConditionItem,
        items.AgendaCardItem,
        items.SupplyCardItem,
        items.StoryMissionCardItem,
        items.UpgradeItem,
        items.ThreatMissionCardItem,
        items.SideMissionCardItem,
    ]

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        if item.__class__ in self.classes:
            if item['name'].lower() == 'back':
                raise DropItem()
        return item


class ProcessAgendasPipeline(object):
    pack_agendas = {
        'General Weiss': "The General's Scheme",
        'IG88': 'Droid Uprising',
        'Royal Guard Champion': 'Crimson Empire',
        'Boba Fett': 'Soldiers for Hire',
        'Kayn Somos': 'Stormtrooper support',
        'Hired Guns': 'Nefarious Dealings',
        'Stormtroopers': "Vader's Fist",
        'Bantha Rider': 'Tusken Treachery',
        'General Sorin': 'Bombardment',
        'Dengar': 'Punishing Tactics',
        'Agent Blaise': 'Imperial Intelligence',
        'Bossk': 'Base Instincts',
        'ISB Infiltrators': 'Infiltration',
        'Greedo': 'Contract Gunmen',
        'The Grand Inquisitor': 'Inquisition',
        'Captain Terro': 'Wasteland Patrol',
        'Jabba the Hutt': "Jabba's Empire",
        'BT-1 and 0-0-0': 'Devious Droids',
        'Jawa Scavenger': 'Desert Scavengers',
    }

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        if item.__class__ == items.AgendaCardItem:
            if item['agenda'].startswith('!!!!!!'):
                item['agenda'] = self.pack_agendas[item['agenda'].replace('!!!!!!', '')]
        return item


class ProcessSideMissionsPipeline(object):
    grey_agendas = {
        'Paying Debts',
        'Imperial Entanglements',
        'Celebration',
    }

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        if item.__class__ == items.SideMissionCardItem:
            if item['color'] is None:
                item['color'] = 'Grey' if item['name'] in self.grey_agendas else 'Green'
        return item


class AddSourceIdsPipeline(object):
    def __init__(self):
        self.inc_id = -1
        self.ids = {}

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        if item.__class__ == items.SourceItem:
            self.inc_id += 1
            item['id'] = self.inc_id
            self.ids[item['name']] = self.inc_id
        elif 'source' in item.fields:
            item['source'] = self.ids[item['source']]
        return item


class ImageProcessingPipeline(object):
    image_attrs = [
        'image',
        'healthy',
        'wounded',
    ]

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        for attr in self.image_attrs:
            if attr in item:
                item[attr] = 'http://cards.boardwars.eu' + item[attr]
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
        items.StoryMissionCardItem: 'story-mission-cards.json',
        items.SideMissionCardItem: 'side-mission-cards.json',
        items.RewardItem: 'rewards-cards.json',
        items.CompanionItem: 'companion-cards.json',
        items.UpgradeItem: 'upgrade-cards.json',
        items.CardBackItem: 'card-backs.json',
        items.ThreatMissionCardItem: 'threat-mission-cards.json'
    }

    def __init__(self):
        self.data = defaultdict(list)

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        self.data[items.CardBackItem] = sorted(self.data[items.CardBackItem], key=lambda i: (i['deck'], i['variant']))
        self.data[items.AgendaCardItem] = sorted(self.data[items.AgendaCardItem], key=lambda i: (i['source'], i['agenda'], i['name']))

        for cls, f in self.file_names.items():
            with open(f'./data/{f}', 'w') as file_object:
                json.dump(self.data[cls], file_object, indent=2)

    def process_item(self, item, spider):
        self.data[item.__class__].append(dict(item))
        return item

