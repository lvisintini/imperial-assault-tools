# -*- coding: utf-8 -*-
import scrapy


class SourceItem(scrapy.Item):
    id = scrapy.Field(serializer=int)
    name = scrapy.Field()
    image = scrapy.Field()
    type = scrapy.Field()
    wave = scrapy.Field(serializer=int)


class SkirmishMapItem(scrapy.Item):
    name = scrapy.Field()
    image = scrapy.Field()


class AgendaCardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field()
    agenda = scrapy.Field()
    image = scrapy.Field()


class CommandCardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field()
    image = scrapy.Field()


class ConditionItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field()
    type = scrapy.Field()
    image = scrapy.Field()


class DeploymentCardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field()
    faction = scrapy.Field()
    image = scrapy.Field()
    alternate_images = scrapy.Field()


class HeroItem(scrapy.Item):
    id = scrapy.Field(serializer=int)
    name = scrapy.Field()
    source = scrapy.Field()
    healthy = scrapy.Field()
    wounded = scrapy.Field()


class HeroClassCardItem(scrapy.Item):
    name = scrapy.Field()
    hero = scrapy.Field()
    image = scrapy.Field()


class ImperialClassCardItem(scrapy.Item):
    name = scrapy.Field()
    imperial_class_deck = scrapy.Field()
    source = scrapy.Field()
    image = scrapy.Field()


class SupplyCardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field()
    image = scrapy.Field()


class StoryMissionCardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field()
    image = scrapy.Field()


class SideMissionCardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field()
    color = scrapy.Field()
    image = scrapy.Field()


class RewardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field()
    image = scrapy.Field()


class Companion(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field()
    image = scrapy.Field()


class UpgradeItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field()
    tier = scrapy.Field(serializer=int)
    image = scrapy.Field()


class CardBackItem(scrapy.Item):
    deck = scrapy.Field()
    variant = scrapy.Field()
    image = scrapy.Field()
