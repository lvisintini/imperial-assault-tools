import json
from collections import OrderedDict


class SingleDataCollector(object):
    source_key = ''
    root = None

    def load_data(self):
        with open('{}/{}.js'.format(self.root, self.source_key), 'r') as file_object:
            self.data.extend(json.load(file_object, object_pairs_hook=OrderedDict))

    def save_data(self):
        with open('{}/{}.js'.format(self.root, self.source_key), 'w') as file_object:
            json.dump(self.data, file_object, indent=2, ensure_ascii=False)

    field_name = None
    memory = {}

    def __init__(self):
        super().__init__()
        self.data = []
        self.load_data()
        self.gather()
        self.save_data()

    @staticmethod
    def print_model(model):
        print('\n' + model['name'])

    def input_text(self):
        return 'Which {} should it have?\nResponse (leave empty to skip): '.format(self.field_name)

    def clean_input(self, new_data):
        raise NotImplementedError

    def validate_input(self, new_data):
        raise NotImplementedError

    def gather(self):
        for model in self.data:
            if self.field_name not in model:
                if model.get('id') in self.memory:
                    model[self.field_name] = self.memory[model.get('id')]
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
                    self.memory[model['id']] = new_data
        print('Done!!')
