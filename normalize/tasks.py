from normalize import base
from normalize.manager import Task
from collections import Counter


class ImageAppendChoiceDataCollector(base.ShowImageMixin, base.AppendChoiceDataCollector):
    pass


class ImageChoiceDataCollector(base.ShowImageMixin, base.ChoiceDataCollector):
    pass


class ImageIntegerDataCollector(base.ShowImageMixin, base.IntegerDataCollector):
    pass


class ImageTextDataCollector(base.ShowImageMixin, base.TextDataCollector):
    pass


class DeDupMerge(Task):
    source = None

    def __init__(self, source=None):
        super(DeDupMerge, self).__init__()
        self.source = source or self.source

    def process(self, data_helper):
        hashes = []
        for model in data_helper.data[self.source]:
            hashes.append(model['hash'])

        for h, c in Counter(hashes).items():
            if c > 1:
                self.log.warning(h)
        return data_helper
