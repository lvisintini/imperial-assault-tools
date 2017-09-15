from normalize.manager import PipelineHelper
from normalize import tasks
from normalize import base
from normalize.contants import (
    SOURCES, TRUE_FALSE_CHOICES, GAME_MODES, AFFILIATION, CARD_TRAITS, DEPLOYMENT_CARD_PREFERRED_ATTR_ORDER
)


class NormalizeImperialData(PipelineHelper):
    tasks = [
        base.LoadMemory('./memory.json'),
        base.LoadData('./raw-data/', SOURCES.as_list),

        # Setup
        tasks.ImagesToPNG,
        base.RenameField(field_name='faction', source=SOURCES.DEPLOYMENT, new_name='affiliation'),

        base.AddIds(source=SOURCES.DEPLOYMENT),
        base.AddIds(source=SOURCES.UPGRADE),
        base.AddIds(source=SOURCES.HERO),
        base.AddIds(source=SOURCES.HERO_CLASS),
        base.AddIds(source=SOURCES.AGENDA),
        base.AddIds(source=SOURCES.COMPANION),
        base.AddIds(source=SOURCES.COMMAND),
        base.AddIds(source=SOURCES.IMPERIAL_CLASS_CARD),
        base.AddIds(source=SOURCES.REWARD),
        base.AddIds(source=SOURCES.STORY_MISSION),
        base.AddIds(source=SOURCES.SIDE_MISSION),
        base.AddIds(source=SOURCES.THREAT_MISSION),
        base.AddIds(source=SOURCES.SKIRMISH_MAP),
        base.AddIds(source=SOURCES.SUPPLY),
        base.SortDataByAttrs('deck', 'variant', source=SOURCES.CARD),

        # Data Collection
        tasks.ImageChoiceDataCollector(field_name='affiliation', source=SOURCES.DEPLOYMENT, choices=AFFILIATION.as_choices),
        tasks.ImageAppendChoiceDataCollector(field_name='traits', source=SOURCES.DEPLOYMENT, choices=CARD_TRAITS.as_choices),
        tasks.ImageIntegerDataCollector(field_name='deployment_cost', source=SOURCES.DEPLOYMENT),
        tasks.ImageIntegerDataCollector(field_name='deployment_group', source=SOURCES.DEPLOYMENT),
        tasks.ImageIntegerDataCollector(field_name='reinforce_cost', source=SOURCES.DEPLOYMENT),
        tasks.ImageChoiceDataCollector(field_name='elite', source=SOURCES.DEPLOYMENT, choices=TRUE_FALSE_CHOICES),
        tasks.ImageTextDataCollector(field_name='name', source=SOURCES.DEPLOYMENT),
        tasks.ImageTextDataCollector(field_name='name', source=SOURCES.COMPANION),
        tasks.ImageTextDataCollector(field_name='description', source=SOURCES.DEPLOYMENT),
        tasks.ImageTextDataCollector(field_name='class', source=SOURCES.IMPERIAL_CLASS_CARD),
        tasks.ImageIntegerDataCollector(field_name='xp', source=SOURCES.IMPERIAL_CLASS_CARD),
        tasks.ImageChoiceDataCollector(field_name='unique', source=SOURCES.DEPLOYMENT, choices=TRUE_FALSE_CHOICES),
        tasks.ImageAppendChoiceDataCollector(field_name='modes', source=SOURCES.DEPLOYMENT, choices=GAME_MODES.as_choices),
        base.RemoveField(field_name='scope', source=SOURCES.DEPLOYMENT),


        tasks.ImageIntegerDataCollector(field_name='credits', source=SOURCES.UPGRADE),
        tasks.ImageIntegerDataCollector(field_name='influence', source=SOURCES.AGENDA),
        tasks.ImageAppendChoiceDataCollector(field_name='traits', source=SOURCES.COMPANION, choices=CARD_TRAITS.as_choices),
        tasks.ImageIntegerDataCollector(field_name='xp', source=SOURCES.HERO_CLASS),

        tasks.ImageIntegerDataCollector(field_name='cost', source=SOURCES.COMMAND),
        tasks.ImageIntegerDataCollector(field_name='limit', source=SOURCES.COMMAND),

        tasks.CollectSources(source=SOURCES.SKIRMISH_MAP),

        base.SaveMemory('./memory.json'),

        # Structure
        tasks.ImperialClassCardToClass,
        tasks.AgendaCardToDeck,

        base.AddHashes(source=SOURCES.STORY_MISSION, exclude=['image', 'image_file', 'id', 'source']),
        tasks.DeDupMerge(source=SOURCES.STORY_MISSION),
        base.RemoveField(field_name='id', source=SOURCES.STORY_MISSION),
        base.SortDataByAttrs('name', source=SOURCES.STORY_MISSION),
        base.SortDataKeys(source=SOURCES.STORY_MISSION, preferred_order=['id', 'name']),
        base.AddIds(source=SOURCES.STORY_MISSION),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.STORY_MISSION, fk_field_path=['source', ]
        ),
        tasks.ChooseOne(field_name='image_file', source=SOURCES.STORY_MISSION),


        base.AddHashes(source=SOURCES.SIDE_MISSION, exclude=['image', 'image_file', 'id', 'source']),
        tasks.DeDupMerge(source=SOURCES.SIDE_MISSION),
        base.RemoveField(field_name='id', source=SOURCES.SIDE_MISSION),
        base.SortDataByAttrs('name', source=SOURCES.SIDE_MISSION),
        base.SortDataKeys(source=SOURCES.SIDE_MISSION, preferred_order=['name', 'color', ]),
        base.AddIds(source=SOURCES.SIDE_MISSION),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.SIDE_MISSION, fk_field_path=['source', ]
        ),
        tasks.ChooseOne(field_name='image_file', source=SOURCES.SIDE_MISSION),


        base.AddHashes(source=SOURCES.THREAT_MISSION, exclude=['image', 'image_file', 'id', 'source']),
        tasks.DeDupMerge(source=SOURCES.THREAT_MISSION),
        base.RemoveField(field_name='id', source=SOURCES.THREAT_MISSION),
        base.SortDataByAttrs('name', source=SOURCES.THREAT_MISSION),
        base.SortDataKeys(source=SOURCES.THREAT_MISSION, preferred_order=['name', ]),
        base.AddIds(source=SOURCES.THREAT_MISSION),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.THREAT_MISSION, fk_field_path=['source', ]
        ),
        tasks.ChooseOne(field_name='image_file', source=SOURCES.THREAT_MISSION),


        base.AddHashes(source=SOURCES.REWARD, exclude=['image', 'image_file', 'id', 'source']),
        tasks.DeDupMerge(source=SOURCES.REWARD),
        base.RemoveField(field_name='id', source=SOURCES.REWARD),
        base.SortDataByAttrs('name', source=SOURCES.REWARD),
        base.SortDataKeys(source=SOURCES.REWARD, preferred_order=['name', ]),
        base.AddIds(source=SOURCES.REWARD),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.REWARD, fk_field_path=['source', ]
        ),
        tasks.ChooseOne(field_name='image_file', source=SOURCES.REWARD),


        base.SortDataByAttrs('name', source=SOURCES.HERO),
        base.SortDataKeys(source=SOURCES.HERO, preferred_order=['id', 'name', ]),
        base.SortDataKeys(source=SOURCES.HERO_CLASS, preferred_order=['id', 'name', 'hero', 'xp']),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.HERO, fk_field_path=['source', ]
        ),

        base.AddHashes(source=SOURCES.COMMAND, exclude=['image', 'image_file', 'id', 'source']),
        tasks.DeDupMerge(source=SOURCES.COMMAND),
        base.RemoveField(field_name='id', source=SOURCES.COMMAND),
        base.SortDataByAttrs('name', 'cost', 'limit', source=SOURCES.COMMAND),
        base.SortDataKeys(source=SOURCES.COMMAND, preferred_order=['name', 'cost', 'limit']),
        base.AddIds(source=SOURCES.COMMAND),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.COMMAND, fk_field_path=['source', ]
        ),
        tasks.ChooseOne(field_name='image_file', source=SOURCES.COMMAND),


        base.AddHashes(source=SOURCES.AGENDA, exclude=['image', 'image_file', 'id', 'source']),
        tasks.DeDupMerge(source=SOURCES.AGENDA),
        base.RemoveField(field_name='id', source=SOURCES.AGENDA),
        base.SortDataByAttrs('agenda_id', 'influence', 'name', source=SOURCES.AGENDA),
        base.SortDataKeys(source=SOURCES.AGENDA, preferred_order=['name', 'agenda_id', 'influence']),
        base.AddIds(source=SOURCES.AGENDA),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.AGENDA_DECKS, fk_field_path=['source', ]
        ),
        tasks.ChooseOne(field_name='image_file', source=SOURCES.AGENDA),

        base.AddHashes(source=SOURCES.DEPLOYMENT, exclude=['image', 'image_file', 'id', 'source']),
        tasks.DeDupMerge(source=SOURCES.DEPLOYMENT),
        base.RemoveField(field_name='id', source=SOURCES.DEPLOYMENT),
        base.SortDataByAttrs('name', 'deployment_cost', source=SOURCES.DEPLOYMENT),
        base.SortAttrData(source=SOURCES.DEPLOYMENT, attr='traits'),
        base.SortAttrData(source=SOURCES.DEPLOYMENT, attr='modes'),
        base.AddIds(source=SOURCES.DEPLOYMENT),
        base.SortDataKeys(source=SOURCES.DEPLOYMENT, preferred_order=DEPLOYMENT_CARD_PREFERRED_ATTR_ORDER),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.DEPLOYMENT, fk_field_path=['source', ]
        ),
        tasks.ChooseOne(field_name='image_file', source=SOURCES.DEPLOYMENT),


        base.AddHashes(source=SOURCES.IMPERIAL_CLASS_CARD, exclude=['image', 'image_file', 'id', 'source']),
        base.RemoveField(field_name='id', source=SOURCES.IMPERIAL_CLASS_CARD),
        base.SortDataByAttrs('class_id', 'name', source=SOURCES.IMPERIAL_CLASS_CARD),
        base.SortDataKeys(source=SOURCES.IMPERIAL_CLASS_CARD, preferred_order=['class_id', 'name', 'xp']),
        base.AddIds(source=SOURCES.IMPERIAL_CLASS_CARD),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.IMPERIAL_CLASSES, fk_field_path=['source', ],
        ),
        tasks.ChooseOne(field_name='image_file', source=SOURCES.IMPERIAL_CLASS_CARD),


        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.SKIRMISH_MAP, fk_field_path=['source', ]
        ),

        base.RemoveField(field_name='id', source=SOURCES.UPGRADE),
        base.SortDataByAttrs('tier', 'name', source=SOURCES.UPGRADE),
        base.SortDataKeys(source=SOURCES.UPGRADE, preferred_order=['tier', 'name', 'credits']),
        base.AddIds(source=SOURCES.UPGRADE),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.UPGRADE, fk_field_path=['source', ]
        ),


        base.RemoveField(field_name='id', source=SOURCES.SUPPLY),
        base.SortDataByAttrs('name', source=SOURCES.SUPPLY),
        base.SortDataKeys(source=SOURCES.SUPPLY, preferred_order=['name', ]),
        base.AddIds(source=SOURCES.SUPPLY),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.SUPPLY, fk_field_path=['source', ]
        ),

        # Images handling
        tasks.RenameImages(root='./images', source=SOURCES.DEPLOYMENT, file_attr='image_file', attrs_for_filename=['name', 'description', 'elite', 'modes']),
        tasks.RenameImages(root='./images', source=SOURCES.CARD, file_attr='image_file', attrs_for_filename=['deck', 'variant']),
        tasks.RenameImages(root='./images', source=SOURCES.IMPERIAL_CLASS_CARD, file_attr='image_file', attrs_for_filename=['class', 'name']),
        tasks.RenameImages(root='./images', source=SOURCES.COMMAND, file_attr='image_file', attrs_for_filename=['name', ]),
        tasks.RenameImages(root='./images', source=SOURCES.AGENDA, file_attr='image_file', attrs_for_filename=['agenda', 'name']),
        tasks.RenameImages(root='./images', source=SOURCES.COMPANION, file_attr='image_file', attrs_for_filename=['name', ]),
        tasks.RenameImages(root='./images', source=SOURCES.HERO, file_attr='healthy_file', attrs_for_filename=['name', ], suffixes=['healthy', ]),
        tasks.RenameImages(root='./images', source=SOURCES.HERO, file_attr='wounded_file', attrs_for_filename=['name', ], suffixes=['wounded', ]),
        tasks.RenameImages(root='./images', source=SOURCES.CONDITION, file_attr='image_file', attrs_for_filename=['name', ]),
        tasks.RenameImages(root='./images', source=SOURCES.REWARD, file_attr='image_file', attrs_for_filename=['name', ]),
        tasks.RenameImages(root='./images', source=SOURCES.SIDE_MISSION, file_attr='image_file', attrs_for_filename=['name', ]),
        tasks.RenameImages(root='./images', source=SOURCES.STORY_MISSION, file_attr='image_file', attrs_for_filename=['name', ]),
        tasks.RenameImages(root='./images', source=SOURCES.THREAT_MISSION, file_attr='image_file', attrs_for_filename=['name', ]),
        tasks.RenameImages(root='./images', source=SOURCES.SKIRMISH_MAP, file_attr='image_file', attrs_for_filename=['name', ]),
        tasks.RenameImages(root='./images', source=SOURCES.UPGRADE, file_attr='image_file', attrs_for_filename=['name', ]),
        tasks.RenameImages(root='./images', source=SOURCES.SUPPLY, file_attr='image_file', attrs_for_filename=['name', ]),
        tasks.ClassHeroRenameImages(root='./images', source=SOURCES.HERO_CLASS, file_attr='image_file', attrs_for_filename=['name', ]),


        # Cleanup
        base.RemoveField(field_name='agenda', source=SOURCES.AGENDA),
        base.RemoveField(field_name='class', source=SOURCES.IMPERIAL_CLASS_CARD),

        base.RemoveField(field_name='hash', source=SOURCES.COMMAND),
        base.RemoveField(field_name='hash', source=SOURCES.SIDE_MISSION),
        base.RemoveField(field_name='hash', source=SOURCES.STORY_MISSION),
        base.RemoveField(field_name='hash', source=SOURCES.THREAT_MISSION),
        base.RemoveField(field_name='hash', source=SOURCES.REWARD),
        base.RemoveField(field_name='hash', source=SOURCES.AGENDA),
        base.RemoveField(field_name='hash', source=SOURCES.DEPLOYMENT),
        base.RemoveField(field_name='hash', source=SOURCES.IMPERIAL_CLASS_CARD),
        base.RemoveField(field_name='hash', source=SOURCES.SUPPLY),

        base.RemoveField(field_name='image', source=SOURCES.CARD),
        base.RemoveField(field_name='image', source=SOURCES.COMMAND),
        base.RemoveField(field_name='image', source=SOURCES.AGENDA),
        base.RemoveField(field_name='image', source=SOURCES.DEPLOYMENT),
        base.RemoveField(field_name='image', source=SOURCES.HERO_CLASS),
        base.RemoveField(field_name='image', source=SOURCES.CONDITION),
        base.RemoveField(field_name='image', source=SOURCES.REWARD),
        base.RemoveField(field_name='image', source=SOURCES.STORY_MISSION),
        base.RemoveField(field_name='image', source=SOURCES.SIDE_MISSION),
        base.RemoveField(field_name='image', source=SOURCES.THREAT_MISSION),
        base.RemoveField(field_name='image', source=SOURCES.SUPPLY),

        base.RenameField(field_name='image_file', source=SOURCES.CARD, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.COMMAND, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.AGENDA, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.DEPLOYMENT, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.IMPERIAL_CLASS_CARD, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.HERO_CLASS, new_name='image'),
        base.RenameField(field_name='healthy_file', source=SOURCES.HERO, new_name='healthy'),
        base.RenameField(field_name='wounded_file', source=SOURCES.HERO, new_name='wounded'),
        base.RenameField(field_name='image_file', source=SOURCES.CONDITION, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.REWARD, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.STORY_MISSION, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.SIDE_MISSION, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.THREAT_MISSION, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.SKIRMISH_MAP, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.UPGRADE, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.SUPPLY, new_name='image'),

        base.RenameField(field_name='hero', source=SOURCES.HERO_CLASS, new_name='hero_id'),
        base.SortDataKeys(source=SOURCES.HERO_CLASS, preferred_order=['id', 'name', 'hero_id', 'xp', 'image']),

        base.RemoveField(field_name='source', source=SOURCES.COMMAND),
        base.RemoveField(field_name='source', source=SOURCES.AGENDA),
        base.RemoveField(field_name='source', source=SOURCES.DEPLOYMENT),
        base.RemoveField(field_name='source', source=SOURCES.HERO),
        base.RemoveField(field_name='source', source=SOURCES.IMPERIAL_CLASS_CARD),
        base.RemoveField(field_name='source', source=SOURCES.AGENDA_DECKS),
        base.RemoveField(field_name='source', source=SOURCES.REWARD),
        base.RemoveField(field_name='source', source=SOURCES.STORY_MISSION),
        base.RemoveField(field_name='source', source=SOURCES.SIDE_MISSION),
        base.RemoveField(field_name='source', source=SOURCES.THREAT_MISSION),
        base.RemoveField(field_name='source', source=SOURCES.SKIRMISH_MAP),
        base.RemoveField(field_name='source', source=SOURCES.UPGRADE),

        base.SaveData('./data/', SOURCES.as_list),
    ]
# sources, supply, upgrade traits, supply traits

def main():
    NormalizeImperialData().run()


if __name__ == '__main__':
    main()
