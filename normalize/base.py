import os
import json
import readline
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
    amend_data = False
    use_memory = True

    def __init__(self, source=None, field_name=None, pk=None, amend_data=None, use_memory=None):
        super(DataCollector, self).__init__()
        self.source = source or self.source
        self.pk = pk or self.pk
        self.field_name = field_name or self.field_name
        self.amend_data = amend_data if amend_data is not None else self.amend_data
        self.use_memory = use_memory if use_memory is not None else self.use_memory

    def before_each(self, model):
        pass

    def after_each(self, model):
        pass

    def input_text(self, model):
        return 'Which {!r} should it have?\nResponse (leave empty to skip): '.format(self.field_name)

    def clean_input(self, new_data):
        raise NotImplementedError

    def validate_input(self, new_data):
        raise NotImplementedError

    def load_from_memory(self, data_helper, model):
        if hasattr(data_helper, 'memory'):
            if self.pk in model and model[self.pk] in data_helper.memory[self.source][self.field_name]:
                model[self.field_name] = data_helper.memory[self.source][self.field_name][model[self.pk]]
                return model
        return model

    def pre_process_existing_value(self, value):
        return str(value)

    def prompt_user(self, model, value, existing):
        def hook():
            readline.insert_text(self.pre_process_existing_value(value))
            readline.redisplay()
        if existing:
            readline.set_pre_input_hook(hook)
        result = input(self.input_text(model))
        readline.set_pre_input_hook()
        return result

    def process(self, data_helper):
        try:
            for model in data_helper.data[self.source]:
                if not self.amend_data:
                    if self.use_memory:
                        self.load_from_memory(data_helper, model)

                    if (self.field_name in model) and (self.validate_input(model[self.field_name])):
                        continue
                else:
                    if self.use_memory:
                        self.load_from_memory(data_helper, model)

                self.before_each(model)
                existing_data = self.field_name in model
                new_data = model.get(self.field_name, None)

                first = True

                while first or not self.validate_input(new_data):
                    if not first:
                        print('No. That value is not right!. Try again...')
                    else:
                        first = False

                    new_data = self.prompt_user(model, new_data, existing_data)

                    if not new_data:
                        break

                    new_data = self.clean_input(new_data)

                else:
                    model[self.field_name] = new_data
                    if self.use_memory and hasattr(data_helper, 'memory'):
                        data_helper.memory[self.source][self.field_name][model[self.pk]] = new_data
                self.after_each(model)

        except (KeyboardInterrupt, SystemExit):
            print('')
            data_helper.log.warning('Exiting data gathering ...')
        finally:
            data_helper.log.info('Done collecting data for {}.{}!!'.format(self.source, self.field_name))
        return data_helper


class IntegerDataCollector(DataCollector):

    def pre_process_existing_value(self, value):
        return '.' if value is None else str(value)

    def clean_input(self, new_data):
        if new_data == '.':
            return None
        try:
            return int(new_data)
        except ValueError:
            return new_data

    def validate_input(self, new_data):
        return isinstance(new_data, int) or new_data is None


class TextDataCollector(DataCollector):
    def pre_process_existing_value(self, value):
        return '' if value is None else value

    def clean_input(self, new_data):
        return '' if new_data is None else new_data

    def validate_input(self, new_data):
        return isinstance(new_data, str)


class ChoiceDataCollector(DataCollector):
    choices = []

    def __init__(self, choices=None, **kwargs):
        self.choices = choices or self.choices

        if self.choices and hasattr(self, 'get_choices'):
            self.choices = self.get_choices()

        super(ChoiceDataCollector, self).__init__(**kwargs)

    def pre_process_existing_value(self, value):
        return next(i for i in range(len(self.choices)) if self.choices[i][0] == value)

    def clean_input(self, new_data):
        if new_data.isdigit() and int(new_data) in range(len(self.choices)):
            return self.choices[int(new_data)][0]
        else:
            return new_data

    def validate_input(self, new_data):
        new_data = tuple(new_data) if isinstance(new_data, list) else new_data
        return new_data in dict(self.choices).keys()

    def input_text(self, model):
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


class RemoveField(Task):
    source = None

    def __init__(self, source=None, field_name=None):
        super(RemoveField, self).__init__()
        self.source = source or self.source
        self.field_name = field_name or self.field_name

    def process(self, data_helper):
        for model in data_helper.data[self.source]:
            model.pop(self.field_name, None)
        return data_helper


class RenameField(Task):
    source = None
    field_name = None
    new_name = None

    def __init__(self, source=None, field_name=None, new_name=None):
        super(RenameField, self).__init__()
        self.source = source or self.source
        self.field_name = field_name or self.field_name
        self.new_name = new_name or self.new_name

    def process(self, data_helper):
        for model in data_helper.data[self.source]:
            model[self.new_name] = model.pop(self.field_name, None)
        return data_helper


#  Preferred Key Order
#  Dedup By Hash
#  Sort data
#  Foreign key to sources
#  Value that can be interpreted as None as a instance attribute
#  Show image as Mixin
#  Choices list append (Deployment types)