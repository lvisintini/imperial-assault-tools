from normalize.manager import PipelineHelper
from normalize import tasks
from normalize import base
from normalize.contants import SOURCES


class NormalizeImperialData(PipelineHelper):
    tasks = [
        base.LoadMemory('./memory.json'),
        base.LoadData('./raw-data/', SOURCES.as_list),
        base.AddIds(source=SOURCES.DEPLOYMENT),
        tasks.DeploymentCardFactionDataCollector(),
        base.SaveData('./data/', SOURCES.as_list),
        base.SaveMemory('./memory.json'),
    ]


def main():
    NormalizeImperialData().run()


if __name__ == '__main__':
    main()
