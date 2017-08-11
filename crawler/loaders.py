# -*- coding: utf-8 -*-
import scrapy

from scrapy.loader import ItemLoader
from scrapy.loader.processors import TakeFirst, MapCompose, Join, Identity


class SourceLoader(ItemLoader):
    default_output_processor = Identity()
    id = scrapy.Field(serializer=int)
    name = scrapy.Field()
    release_date = scrapy.Field(serializer=as_iso_format_date)
    image = scrapy.Field()


class SkirmishMapLoader(ItemLoader):
    name = scrapy.Field()
    release_date = scrapy.Field(serializer=as_iso_format_date)
    image = scrapy.Field()


class AgendaCardLoader(ItemLoader):
    source = scrapy.Field(serializer=int)
    agenda = scrapy.Field()
    name = scrapy.Field()
    agenda_deck = scrapy.Field(serializer=int)
    image = scrapy.Field()


class CommandCardLoader(ItemLoader):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    image = scrapy.Field()


class ConditionLoader(ItemLoader):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    type = scrapy.Field()
    image = scrapy.Field()


class DeploymentCardLoader(ItemLoader):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    faction = scrapy.Field()
    image = scrapy.Field()


class HeroLoader(ItemLoader):
    id = scrapy.Field(serializer=int)
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    healthy = scrapy.Field()
    wounded = scrapy.Field()
    deck_back = scrapy.Field()


class HeroClassCardLoader(ItemLoader):
    name = scrapy.Field()
    hero = scrapy.Field(serializer=int)
    image = scrapy.Field()


class ImperialClassCardLoader(ItemLoader):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    imperial_class = scrapy.Field()
    image = scrapy.Field()


class SupplyCardLoader(ItemLoader):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    image = scrapy.Field()


class StoryMissionCardLoader(ItemLoader):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    image = scrapy.Field()


class SideMissionCardLoader(ItemLoader):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    color = scrapy.Field()
    image = scrapy.Field()


class RewardLoader(ItemLoader):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    image = scrapy.Field()


class Companion(ItemLoader):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    image = scrapy.Field()


class UpgradeLoader(ItemLoader):
    name = scrapy.Field()
    source = scrapy.Field(serializer=int)
    tier = scrapy.Field(serializer=int)
    image = scrapy.Field()


class CardBackLoader(ItemLoader):
    id = scrapy.Field(serializer=int)
    name = scrapy.Field()
    image = scrapy.Field()
