from normalize.manager import PipelineHelper
from normalize import tasks
from normalize import base
from normalize.contants import (
    SOURCES, TRUE_FALSE_CHOICES, GAME_MODES, AFFILIATION, DEPLOYMENT_CARD_TRAITS, DEPLOYMENT_CARD_PREFERRED_ATTR_ORDER
)


class NormalizeImperialData(PipelineHelper):
    tasks = [
        base.LoadMemory('./memory.json'),
        base.LoadData('./raw-data/', SOURCES.as_list),
        base.AddIds(source=SOURCES.DEPLOYMENT),
        base.AddIds(source=SOURCES.UPGRADE),
        base.AddIds(source=SOURCES.HERO_CLASS),
        base.RenameField(field_name='faction', source=SOURCES.DEPLOYMENT, new_name='affiliation'),
        tasks.ImageChoiceDataCollector(field_name='affiliation', source=SOURCES.DEPLOYMENT, choices=AFFILIATION.as_choices),
        tasks.ImageAppendChoiceDataCollector(field_name='traits', source=SOURCES.DEPLOYMENT, choices=DEPLOYMENT_CARD_TRAITS.as_choices),
        tasks.ImageIntegerDataCollector(field_name='deployment_cost', source=SOURCES.DEPLOYMENT),
        tasks.ImageIntegerDataCollector(field_name='deployment_group', source=SOURCES.DEPLOYMENT),
        tasks.ImageIntegerDataCollector(field_name='reinforce_cost', source=SOURCES.DEPLOYMENT),
        tasks.ImageChoiceDataCollector(field_name='elite', source=SOURCES.DEPLOYMENT, choices=TRUE_FALSE_CHOICES),
        tasks.ImageTextDataCollector(field_name='name', source=SOURCES.DEPLOYMENT),
        tasks.ImageTextDataCollector(field_name='description', source=SOURCES.DEPLOYMENT),
        tasks.ImageChoiceDataCollector(field_name='unique', source=SOURCES.DEPLOYMENT, choices=TRUE_FALSE_CHOICES),
        tasks.ImageAppendChoiceDataCollector(field_name='modes', source=SOURCES.DEPLOYMENT, choices=GAME_MODES.as_choices),
        base.RemoveField(field_name='scope', source=SOURCES.DEPLOYMENT),
        tasks.ImageIntegerDataCollector(field_name='credits', source=SOURCES.UPGRADE),
        tasks.ImageIntegerDataCollector(field_name='xp', source=SOURCES.HERO_CLASS),
        base.SaveMemory('./memory.json'),
        base.SortDataByAttrs('name', 'deployment_cost', source=SOURCES.DEPLOYMENT),
        base.SortDataKeys(source=SOURCES.DEPLOYMENT, preferred_order=DEPLOYMENT_CARD_PREFERRED_ATTR_ORDER),
        base.AddIds(source=SOURCES.DEPLOYMENT),
        base.RemoveField(field_name='id', source=SOURCES.DEPLOYMENT),
        base.SaveData('./data/', SOURCES.as_list),
    ]


def main():
    NormalizeImperialData().run()


if __name__ == '__main__':
    main()
