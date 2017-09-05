from normalize import base


class ImageAppendChoiceDataCollector(base.ShowImageMixin, base.AppendChoiceDataCollector):
    pass


class ImageChoiceDataCollector(base.ShowImageMixin, base.ChoiceDataCollector):
    pass


class ImageIntegerDataCollector(base.ShowImageMixin, base.IntegerDataCollector):
    pass


class ImageTextDataCollector(base.ShowImageMixin, base.TextDataCollector):
    pass
