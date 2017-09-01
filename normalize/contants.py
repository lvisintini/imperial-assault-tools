TRUE_FALSE_CHOICES = [
    (False, 'False'),
    (True, 'True'),
]


class GAME_MODES:
    CAMPAIGN = 'Campaign'
    SKIRMISH = 'Skirmish'

    as_choices = [
        ((CAMPAIGN, SKIRMISH), f'{CAMPAIGN} & {SKIRMISH}'),
        ((CAMPAIGN, ), CAMPAIGN),
        ((SKIRMISH, ), SKIRMISH),
    ]


class SOURCES:
    SOURCE = 'sources'
    SKIRMISH_MAP = 'skirmish-maps'
    AGENDA = 'agenda-cards'
    COMMAND = 'command-cards'
    CONDITION = 'condition-cards'
    DEPLOYMENT = 'deployment-cards'
    HERO = 'heroes'
    HERO_CLASS = 'hero-class-cards'
    IMPERIAL_CLASS = 'imperial-class-cards'
    SUPPLY = 'supply-cards'
    STORY_MISSION = 'story-mission-cards'
    SIDE_MISSION = 'side-mission-cards'
    REWARD = 'rewards-cards'
    COMPANION = 'companion-cards'
    UPGRADE = 'upgrade-cards'
    CARD = 'card-backs'
    THREAT_MISSION = 'threat-mission-cards'

    as_list = [
        SOURCE,
        SKIRMISH_MAP,
        AGENDA,
        COMMAND,
        CONDITION,
        DEPLOYMENT,
        HERO,
        HERO_CLASS,
        IMPERIAL_CLASS,
        SUPPLY,
        STORY_MISSION,
        SIDE_MISSION,
        REWARD,
        COMPANION,
        UPGRADE,
        CARD,
        THREAT_MISSION,
    ]


class AFFILIATION:
    REBEL = 'Rebel'
    IMPERIAL = 'Imperial'
    MERCENARY = 'Mercenary'
    NEUTRAL = 'Neutral'

    as_choices = [
        (REBEL, REBEL),
        (IMPERIAL, IMPERIAL),
        (MERCENARY, MERCENARY),
        (NEUTRAL, NEUTRAL),
    ]

class DEPLOYMENT_CARD_TRAITS:
    SPY = 'Spy'
    BRAWLER = 'Brawler'
    FORCE_USER = 'Force User'
    SKIRMISH_UPGRADE = 'Skirmish Upgrade'
    WOOKIEE = 'Wookiee'
    GUARDIAN = 'Guardian'
    TROOPER = 'Trooper'
    CREATURE = 'Creature'
    HEAVY_WEAPON = 'Heavy Weapon'
    LEADER = 'Leader'
    SMUGGLER = 'Smuggler'
    VEHICLE = 'Vehicle'
    HUNTER = 'Hunter'
    DROID = 'Droid'

    as_choices = (
        (SPY, SPY),
        (BRAWLER, BRAWLER),
        (FORCE_USER, FORCE_USER),
        (SKIRMISH_UPGRADE, SKIRMISH_UPGRADE),
        (WOOKIEE, WOOKIEE),
        (GUARDIAN, GUARDIAN),
        (TROOPER, ),
        (CREATURE, ),
        (HEAVY_WEAPON, ),
        (LEADER, ),
        (SMUGGLER, ),
        (VEHICLE, ),
        (HUNTER, ),
        (DROID, ),
    )
