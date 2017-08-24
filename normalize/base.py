import os
import json
from collections import OrderedDict, defaultdict
from normalize.manager import Task

def rec_dd():
    return defaultdict(rec_dd)


class LoadData(Task):
    sources = []
    extension = 'json'
    attr = 'data'

    def __init__(self, root, sources=None, extension=None, attr=None):
        super(LoadData, self).__init__()
        self.root = root
        self.sources = sources or self.sources
        self.extension = extension or self.extension
        self.attr = attr or self.attr

    def process(self, data_helper):
        data = OrderedDict()
        for source_key in self.sources:
            with open('{}{}.{}'.format(self.root, source_key, self.extension), 'r') as file_object:
                data[source_key] = json.load(file_object, object_pairs_hook=OrderedDict)
        setattr(data_helper, self.attr, data)
        return data_helper


class SaveData(Task):
    sources = []
    extension = 'json'
    indent = 2
    attr = 'data'

    def __init__(self, root, sources=None, extension=None, indent=None, attr=None):
        super(SaveData, self).__init__()
        self.root = root
        self.sources = sources or self.sources
        self.extension = extension or self.extension
        self.indent = indent or self.indent
        self.attr = attr or self.attr

    def process(self, data_helper):
        for source_key in self.sources:
            with open('{}/{}.js'.format(self.root, source_key), 'w') as file_object:
                json.dump(
                    getattr(data_helper, self.attr)[source_key],
                    file_object,
                    indent=self.indent,
                    ensure_ascii=False
                )
        return data_helper


class DataCollector(Task):
    pk = 'id'

    def __init__(self, source=None, field_name=None, pk=None):
        super(DataCollector, self).__init__()
        self.source = source or self.source
        self.pk = pk or self.pk
        self.field_name = field_name or self.field_name

    def before_each(self, model):
        pass

    def after_each(self, model):
        pass

    def input_text(self):
        return 'Which {!r} should it have?\nResponse (leave empty to skip): '.format(self.field_name)

    def clean_input(self, new_data):
        raise NotImplementedError

    def validate_input(self, new_data):
        raise NotImplementedError

    def process(self, data_helper):
        try:
            for model in data_helper.data[self.source]:
                if (self.field_name not in model) or not self.validate_input(model[self.field_name]):
                    if hasattr(data_helper, 'memory') and self.pk in model and \
                                    model[self.pk] in data_helper.memory[self.source][self.field_name]:
                        model[self.field_name] = data_helper.memory[self.source][self.field_name][model[self.pk]]
                        continue

                    self.before_each(model)
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
                    self.after_each(model)
        except (KeyboardInterrupt, SystemExit):
            print('')
            data_helper.log.warning('Exiting data gathering ...')
        finally:
            data_helper.log.info('Done collecting data for {}.{}!!'.format(self.source, self.field_name))
        return data_helper


class IntegerDataCollector(DataCollector):

    def clean_input(self, new_data):
        try:
            return int(new_data)
        except ValueError:
            return new_data

    def validate_input(self, new_data):
        return isinstance(new_data, int)


class ChoiceDataCollector(DataCollector):
    choices = []

    def __init__(self, source=None, field_name=None, choices=None, pk=None):
        self.choices = choices or self.choices

        if self.choices and hasattr(self, 'get_choices'):
            self.choices = self.get_choices()

        super(ChoiceDataCollector, self).__init__(source, field_name, pk)

    def clean_input(self, new_data):
        if new_data.isdigit() and int(new_data) in range(len(self.choices)):
            return self.choices[int(new_data)][0]
        else:
            return new_data

    def validate_input(self, new_data):
        return new_data in dict(self.choices).keys()

    def input_text(self):
        options = []
        for i in range(len(self.choices)):
            v = f'{i} - {self.choices[i][1]} [{self.choices[i][0]}]'
            if self.choices[i][0] == self.choices[i][1]:
                v = f'{i} - {self.choices[i][1]}'
            options.append(v)

        options_text = '\n\t'.join(options)

        return f'Which {self.field_name!r} should it have?\n\t{options_text}\nResponse:'


class LoadMemory(Task):
    def __init__(self, file_path):
        super(LoadMemory, self).__init__()
        self.file_path = file_path

    def process(self, data_helper):
        return data_helper

    def setup(self, data_helper):
        memory_data = {}

        if os.path.exists(self.file_path):
            with open(self.file_path, 'r') as file_object:
                memory_data = json.load(file_object)

        memory = rec_dd()
        for source in memory_data.keys():
            for field_name in memory_data[source].keys():
                for pk in memory_data[source][field_name].keys():
                    memory[source][field_name][int(pk) if pk.isdigit() else pk] = memory_data[source][field_name][pk]

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


class AddIds(Task):
    source = None

    def __init__(self, source=None):
        super(AddIds, self).__init__()
        self.source = source or self.source

    def process(self, data_helper):
        i = -1

        if all(['id' not in model for model in data_helper.data[self.source]]):
            for model in data_helper.data[self.source]:
                i += 1
                model['id'] = i

        return data_helper
