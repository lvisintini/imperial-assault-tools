TRUE_FALSE_CHOICES = [
    (False, 'False'),
    (True, 'True'),
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


class FACTIONS:
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
