# -*- coding: utf-8 -*-
import scrapy


class DefaultDataItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field()
    image = scrapy.Field()


class SourceItem(scrapy.Item):
    id = scrapy.Field(serializer=int)
    name = scrapy.Field()
    image = scrapy.Field()
    type = scrapy.Field()
    wave = scrapy.Field(serializer=int)


class SkirmishMapItem(scrapy.Item):
    name = scrapy.Field()
    image = scrapy.Field()


class AgendaCardItem(DefaultDataItem):
    agenda = scrapy.Field()


class CommandCardItem(DefaultDataItem):
    pass


class ConditionItem(scrapy.Item):
    name = scrapy.Field()
    image = scrapy.Field()


class DeploymentCardItem(DefaultDataItem):
    faction = scrapy.Field()
    scope = scrapy.Field()


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


class ImperialClassCardItem(DefaultDataItem):
    imperial_class_deck = scrapy.Field()


class SupplyCardItem(DefaultDataItem):
    pass


class StoryMissionCardItem(DefaultDataItem):
    pass


class ThreatMissionCardItem(DefaultDataItem):
    pass


class SideMissionCardItem(DefaultDataItem):
    color = scrapy.Field()


class RewardItem(DefaultDataItem):
    pass


class CompanionItem(DefaultDataItem):
    pass


class UpgradeItem(DefaultDataItem):
    tier = scrapy.Field(serializer=int)


class CardBackItem(scrapy.Item):
    deck = scrapy.Field()
    variant = scrapy.Field()
    image = scrapy.Field()


