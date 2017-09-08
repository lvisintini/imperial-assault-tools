import subprocess
import time
from collections import Counter, OrderedDict

from look_at.wmctrl import WmCtrl

from normalize import base
from normalize.manager import Task


class ImageAppendChoiceDataCollector(base.ShowImageMixin, base.AppendChoiceDataCollector):
    pass


class ImageChoiceDataCollector(base.ShowImageMixin, base.ChoiceDataCollector):
    pass


class ImageIntegerDataCollector(base.ShowImageMixin, base.IntegerDataCollector):
    pass


class ImageTextDataCollector(base.ShowImageMixin, base.TextDataCollector):
    pass


class ForeignKeyBuilder(Task):
    source = None
    source_pk = 'id'
    source_field_path = None
    fk_source = None
    fk_source_pk = 'id'
    fk_field_path = None

    attrs_to_copy = []

    def __init__(self, source=None, source_pk=None, source_field_path=None, fk_source=None, fk_source_pk=None,
                 fk_field_path=None, attrs_to_copy=None):
        super(ForeignKeyBuilder, self).__init__()
        self.source = source or self.source
        self.source_pk = source_pk or self.source_pk
        self.source_field_path = source_field_path or self.source_field_path
        self.fk_source = fk_source or self.fk_source
        self.fk_source_pk = fk_source_pk or self.fk_source_pk
        self.fk_field_path = fk_field_path or self.fk_field_path
        self.attrs_to_copy = attrs_to_copy or self.attrs_to_copy

    def get_model_field(self, model, field_path):
        fk = model
        for path in field_path:
            fk = fk.get(path)
            if fk is None:
                break
        return fk

    def set_model_field(self, model, field_path, new_fk):
        current = model
        for path in field_path[:-1]:
            if path not in current:
                current[path] = {}
            current = current[path]
        current[field_path[-1]] = new_fk

    def process(self, data_helper):
        for fk_model in data_helper.data[self.fk_source]:
            fk = self.get_model_field(fk_model, self.fk_field_path)
            fks = [fk, ] if isinstance(fk, int) else fk
            pk = fk_model[self.fk_source_pk]

            for fk in fks:
                model = next(m for m in data_helper.data[self.source] if m[self.source_pk] == fk)

                current = self.get_model_field(model, self.source_field_path)
                if current is None:
                    current = []

                current.append(OrderedDict([
                    (self.fk_source_pk, pk),
                    *[(a, fk_model[a]) for a in self.attrs_to_copy]
                ]))

                self.set_model_field(model, self.source_field_path, current)

        return data_helper


class DeDupMerge(Task):
    source = None

    def __init__(self, source=None):
        super(DeDupMerge, self).__init__()
        self.source = source or self.source

    def process(self, data_helper):
        hashes = []
        for model in data_helper.data[self.source]:
            hashes.append(model['hash'])

        duplicate_hashes = [h for h, c in Counter(hashes).items() if c > 1]

        for dh in duplicate_hashes:
            sources = []
            images = []
            for model in [m for m in data_helper.data[self.source] if m['hash'] == dh]:
                if model['source'] not in sources:
                    sources.append(model['source'])
                if model['image_file'] not in images:
                    images.append(model['image_file'])

            for model in [m for m in data_helper.data[self.source] if m['hash'] == dh]:
                model['source'] = sources
                model['image_file'] = images

        for model in [m for m in data_helper.data[self.source] if m['hash'] not in duplicate_hashes]:
            model['source'] = [model['source'], ]
            model['image_file'] = [model['image_file'], ]

        new_collection = []
        deduped = []

        for model in data_helper.data[self.source]:
            if model['hash'] in duplicate_hashes:
                if model['hash'] not in deduped:
                    deduped.append(model['hash'])
                    new_collection.append(model)
            else:
                new_collection.append(model)

        data_helper.data[self.source] = new_collection

        return data_helper


class ChooseOne(base.ChoiceDataCollector):
    amend_data = True
    use_memory = True
    null_input = None
    skip_input = ''

    def __init__(self, *args, **kwargs):
        super(ChooseOne, self).__init__(*args, **kwargs)
        self.viewers = []
        self.active_window = WmCtrl().get_active_window()
        # This is because this lib is not python3 ready ...
        self.active_window.id = self.active_window.id.decode('utf-8')

    def pre_process_existing_value_to_prefill_input(self, value):
        return ''

    def before_each(self, model):
        self.choices = [(x, x) for x in model[self.field_name]]

        if len(model[self.field_name]) > 1 and isinstance(model[self.field_name], list):
            for image in model[self.field_name]:
                self.viewers.append(subprocess.Popen(['eog', image]))
            time.sleep(0.25)
            self.active_window.activate()

    def after_each(self, model):
        for p in self.viewers:
            p.terminate()
            p.kill()
        self.viewers = []

    def handle_input_loop(self, model):
        existing_data = self.field_name in model
        new_data = model.get(self.field_name, None)

        if isinstance(new_data, list):
            if len(new_data) == 1:
                new_data = self.clean_input('0')
                return True, new_data
        else:
            return False, None

        first = True

        while first or not self.validate_input(new_data):
            if not first:
                print('No. That value is not right!. Try again...')
            else:
                first = False

            new_data = self.prompt_user(model, new_data, existing_data)

            if self.skip_input is not None and new_data == self.skip_input:
                return False, None

            new_data = self.clean_input(new_data)

        else:
            return True, new_data
