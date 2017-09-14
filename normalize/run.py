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

        base.SaveMemory('./memory.json'),

        # Structure
        tasks.ImperialClassCardToClass,
        tasks.AgendaCardToDeck,

        base.SortDataByAttrs('name', source=SOURCES.HERO),
        base.SortDataKeys(source=SOURCES.HERO, preferred_order=['id', 'name']),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.HERO, fk_field_path=['source', ]
        ),

        base.AddHashes(source=SOURCES.COMMAND, exclude=['image', 'image_file', 'id', 'source']),
        tasks.DeDupMerge(source=SOURCES.COMMAND),
        base.SortDataByAttrs('name', 'cost', 'limit', source=SOURCES.COMMAND),
        base.RemoveField(field_name='id', source=SOURCES.COMMAND),
        base.AddIds(source=SOURCES.COMMAND),
        base.SortDataKeys(source=SOURCES.COMMAND, preferred_order=['id', 'name', 'cost', 'limit']),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.COMMAND, fk_field_path=['source', ]
        ),
        tasks.ChooseOne(field_name='image_file', source=SOURCES.COMMAND),


        base.AddHashes(source=SOURCES.AGENDA, exclude=['image', 'image_file', 'id', 'source']),
        tasks.DeDupMerge(source=SOURCES.AGENDA),
        base.SortDataByAttrs('agenda_id', 'influence', 'name', source=SOURCES.AGENDA),
        base.RemoveField(field_name='id', source=SOURCES.AGENDA),
        base.AddIds(source=SOURCES.AGENDA),
        base.SortDataKeys(source=SOURCES.AGENDA, preferred_order=['id', 'name', 'agenda_id', 'influence']),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.AGENDA_DECKS, fk_field_path=['source', ]
        ),
        tasks.ChooseOne(field_name='image_file', source=SOURCES.AGENDA),

        base.AddHashes(source=SOURCES.DEPLOYMENT, exclude=['image', 'image_file', 'id', 'source']),
        tasks.DeDupMerge(source=SOURCES.DEPLOYMENT),
        base.SortDataByAttrs('name', 'deployment_cost', source=SOURCES.DEPLOYMENT),
        base.SortAttrData(source=SOURCES.DEPLOYMENT, attr='traits'),
        base.SortAttrData(source=SOURCES.DEPLOYMENT, attr='modes'),
        base.RemoveField(field_name='id', source=SOURCES.DEPLOYMENT),
        base.AddIds(source=SOURCES.DEPLOYMENT),
        base.SortDataKeys(source=SOURCES.DEPLOYMENT, preferred_order=DEPLOYMENT_CARD_PREFERRED_ATTR_ORDER),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.DEPLOYMENT, fk_field_path=['source', ]
        ),
        tasks.ChooseOne(field_name='image_file', source=SOURCES.DEPLOYMENT),


        base.AddHashes(source=SOURCES.IMPERIAL_CLASS_CARD, exclude=['image', 'image_file', 'id', 'source']),
        tasks.DeDupLog(source=SOURCES.IMPERIAL_CLASS_CARD),
        base.SortDataByAttrs('class', 'name', source=SOURCES.IMPERIAL_CLASS_CARD),
        base.RemoveField(field_name='id', source=SOURCES.IMPERIAL_CLASS_CARD),
        base.AddIds(source=SOURCES.IMPERIAL_CLASS_CARD),
        base.SortDataKeys(source=SOURCES.IMPERIAL_CLASS_CARD, preferred_order=['id', 'class_id', 'name', 'xp']),
        tasks.ForeignKeyBuilder(
            source=SOURCES.SOURCE_CONTENTS, fk_source=SOURCES.IMPERIAL_CLASSES, fk_field_path=['source', ],
        ),
        tasks.ChooseOne(field_name='image_file', source=SOURCES.DEPLOYMENT),


        # Images handling
        tasks.RenameImages(root='./images', source=SOURCES.CARD, file_attr='image_file', attrs_for_filename=['deck', 'variant']),
        tasks.RenameImages(root='./images', source=SOURCES.IMPERIAL_CLASS_CARD, file_attr='image_file', attrs_for_filename=['class', 'name']),
        tasks.RenameImages(root='./images', source=SOURCES.COMMAND, file_attr='image_file', attrs_for_filename=['name', ]),
        tasks.RenameImages(root='./images', source=SOURCES.AGENDA, file_attr='image_file', attrs_for_filename=['agenda', 'name']),
        tasks.RenameImages(root='./images', source=SOURCES.COMPANION, file_attr='image_file', attrs_for_filename=['name', ]),
        tasks.RenameImages(root='./images', source=SOURCES.HERO, file_attr='healthy_file', attrs_for_filename=['name', ], suffixes=['healthy', ]),
        tasks.RenameImages(root='./images', source=SOURCES.HERO, file_attr='wounded_file', attrs_for_filename=['name', ], suffixes=['wounded', ]),
        tasks.ClassHeroRenameImages(root='./images', source=SOURCES.HERO_CLASS, file_attr='image_file', attrs_for_filename=['name', ]),


        # Cleanup
        base.RemoveField(field_name='agenda', source=SOURCES.AGENDA),
        base.RemoveField(field_name='class', source=SOURCES.IMPERIAL_CLASS_CARD),

        base.RemoveField(field_name='hash', source=SOURCES.COMMAND),
        base.RemoveField(field_name='hash', source=SOURCES.AGENDA),
        base.RemoveField(field_name='hash', source=SOURCES.DEPLOYMENT),
        base.RemoveField(field_name='hash', source=SOURCES.IMPERIAL_CLASS_CARD),

        base.RemoveField(field_name='image', source=SOURCES.CARD),
        base.RemoveField(field_name='image', source=SOURCES.COMMAND),
        base.RemoveField(field_name='image', source=SOURCES.AGENDA),
        base.RemoveField(field_name='image', source=SOURCES.DEPLOYMENT),
        base.RemoveField(field_name='image', source=SOURCES.HERO_CLASS),

        base.RenameField(field_name='image_file', source=SOURCES.CARD, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.COMMAND, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.AGENDA, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.DEPLOYMENT, new_name='image'),
        base.RenameField(field_name='image_file', source=SOURCES.IMPERIAL_CLASS_CARD, new_name='image'),
        base.RenameField(field_name='healthy_file', source=SOURCES.HERO, new_name='healthy'),
        base.RenameField(field_name='wounded_file', source=SOURCES.HERO, new_name='wounded'),

        base.RemoveField(field_name='source', source=SOURCES.COMMAND),
        base.RemoveField(field_name='source', source=SOURCES.AGENDA),
        base.RemoveField(field_name='source', source=SOURCES.DEPLOYMENT),
        base.RemoveField(field_name='source', source=SOURCES.HERO),
        base.RemoveField(field_name='source', source=SOURCES.IMPERIAL_CLASS_CARD),
        base.RemoveField(field_name='source', source=SOURCES.AGENDA_DECKS),

        base.SaveData('./data/', SOURCES.as_list),
    ]


def main():
    NormalizeImperialData().run()


if __name__ == '__main__':
    main()
