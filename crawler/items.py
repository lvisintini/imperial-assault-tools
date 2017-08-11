# -*- coding: utf-8 -*-
import scrapy


def as_iso_format_date(value):
    return value.isoformat()


class SourceItem(scrapy.Item):
    id = scrapy.Field(serializer=int)
    name = scrapy.Field()
    release_date = scrapy.Field(serializer=as_iso_format_date)
    image = scrapy.Field()


class SkirmishMapItem(scrapy.Item):
    name = scrapy.Field()
    release_date = scrapy.Field(serializer=as_iso_format_date)
    image = scrapy.Field()


class AgendaCardItem(scrapy.Item):
    source = scrapy.Field(serializer=int)
    agenda = scrapy.Field()
    name = scrapy.Field()
    agenda_deck = scrapy.Field(serializer=int)
    image = scrapy.Field()


class CommandCardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    image = scrapy.Field()


class ConditionItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    type = scrapy.Field()
    image = scrapy.Field()


class DeploymentCardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    faction = scrapy.Field()
    image = scrapy.Field()


class HeroItem(scrapy.Item):
    id = scrapy.Field(serializer=int)
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    healthy = scrapy.Field()
    wounded = scrapy.Field()
    deck_back = scrapy.Field()


class HeroClassCardItem(scrapy.Item):
    name = scrapy.Field()
    hero = scrapy.Field(serializer=int)
    image = scrapy.Field()


class ImperialClassCardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    imperial_class = scrapy.Field()
    image = scrapy.Field()


class SupplyCardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    image = scrapy.Field()


class StoryMissionCardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    image = scrapy.Field()


class SideMissionCardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    color = scrapy.Field()
    image = scrapy.Field()


class RewardItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    image = scrapy.Field()


class Companion(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    image = scrapy.Field()


class UpgradeItem(scrapy.Item):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    tier = scrapy.Field(serializer=int)
    image = scrapy.Field()


class CardBackItem(scrapy.Item):
    id = scrapy.Field(serializer=int)
    name = scrapy.Field()
    image = scrapy.Field()
