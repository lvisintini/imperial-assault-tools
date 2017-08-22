import json
from collections import OrderedDict, defaultdict
from normalize.manager import Task


def rec_dd():
    return defaultdict(rec_dd)


class LoadData(Task):
    sources = []
    extension = 'json'

    def __init__(self, root, sources=None, extension='json', indent=2, attr='data'):
        super(LoadData, self).__init__()
        self.root = root
        self.sources = sources if sources else []
        self.extension = extension
        self.indent = indent
        self.attr = attr

    def process(self, data_helper):
        data = OrderedDict()
        for source_key in self.sources:
            with open('{}/{}.js'.format(self.root, source_key), 'r') as file_object:
                data[source_key].extend(json.load(file_object, object_pairs_hook=OrderedDict))
        setattr(data_helper, 'data', data)
        return data_helper


class SaveData(Task):
    def __init__(self, root, sources=None, extension='json', indent=2, attr='data'):
        super(SaveData, self).__init__()
        self.root = root
        self.sources = sources if sources else []
        self.extension = extension
        self.indent = indent
        self.attr = attr

    def process(self, data_helper):
        for source_key in self.sources:
            with open('{}/{}.js'.format(self.root, source_key), 'w') as file_object:
                json.dump(
                    getattr(data_helper, self.attr).data[source_key],
                    file_object,
                    indent=self.indent,
                    ensure_ascii=False
                )
        return data_helper


class DataCollector(Task):

    def __init__(self, source, field_name, pk='id'):
        super(DataCollector, self).__init__()
        self.source = source
        self.pk = pk
        self.field_name = field_name

    @staticmethod
    def print_model(model):
        raise NotImplementedError

    def input_text(self):
        return 'Which {!r} should it have?\nResponse (leave empty to skip): '.format(self.field_name)

    def clean_input(self, new_data):
        raise NotImplementedError

    def validate_input(self, new_data):
        raise NotImplementedError

    def process(self, data_helper):
        for model in data_helper.data[self.source]:
            if self.field_name not in model:
                if hasattr(data_helper, 'memory') and self.pk in model and \
                                model[self.pk] in data_helper.memory[self.source][self.field_name]:
                    model[self.field_name] = data_helper.memory[self.source][self.field_name][model[self.pk]]
                    continue

                self.print_model(model)
                new_data = None

                while not self.validate_input(new_data):
                    if new_data is not None:
                        print('No. That value is not right!. Try again...')
                    new_data = input(self.input_text())
                    if not new_data:
                        break

                    new_data = self.clean_input(new_data)

                else:
                    model[self.field_name] = new_data
                    if hasattr(data_helper, 'memory'):
                        data_helper.memory[self.source][self.field_name][model[self.pk]] = new_data
        print('Done!!')


class ChoiceDataCollector(DataCollector):
    def __init__(self, source, field_name, choices=None, pk='id'):
        if choices is None:
            raise Exception('')
        super(ChoiceDataCollector, self).__init__(source, field_name, pk)

    def clean_input(self, new_data):
        try:
            new_data = int(new_data)
            new_data = self.slots[int(new_data)]
        except (ValueError, KeyError):
            pass
        else:
            return new_data
        return new_data

    def validate_input(self, new_data):
        return new_data in self.slots


    def input_text(self):
        options = '\n\t'.join(
            ['{} - {}'.format(i, self.slots[i]) for i in range(len(self.slots))]
        )
        return 'Which {} should it have?\n\t{}\nResponse:'.format(self.field_name, options)


class LoadMemory(Task):
    def __init__(self, file_path):
        super(LoadMemory, self).__init__()
        self.file_path = file_path

    def process(self, data_helper):
        return data_helper

    def setup(self, data_helper):
        memory = rec_dd()
        with open(self.file_path, 'r') as file_object:
            memory_data = json.load(file_object, object_pairs_hook=OrderedDict)

        for source in memory_data.keys():
            for field_name in memory_data[source].keys():
                for pk in memory_data[source][field_name].keys():
                    memory[source][field_name][pk] = memory_data[source][field_name][pk]

        data_helper.memory = memory
        return data_helper


class SaveMemory(Task):
    def __init__(self, file_path, indent=2):
        super(SaveMemory, self).__init__()
        self.file_path = file_path
        self.indent = indent

    def process(self, data_helper):
        return data_helper

    def teardown(self, data_helper):
        with open(self.file_path, 'w') as file_object:
            json.dump(
                data_helper.memory,
                file_object,
                indent=self.indent,
                ensure_ascii=False
            )
        return data_helper
