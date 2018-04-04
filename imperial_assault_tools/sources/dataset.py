import os
from .base import DataSource


class SourceName(str):
    pass


class DataSetBase:
    @classmethod
    def fetch_data(cls):
        for source in cls.as_list:
            source.fetch_data()

    @classmethod
    def save_data(cls):
        for source in cls.as_list:
            source.save_data()

    @classmethod
    def add_sources(cls, **kwargs):
        for k, v in kwargs.items():
            setattr(cls, k, v)
            cls.as_list.append(v)
            cls.as_dict[v.source_name] = v


class DatasetMetaclass(type):
    def __new__(mcs, name, bases, dct):
        required = ['source_class', 'root', 'path', 'extension']
        if all([dct.get(key) for key in required]):
            dct['root'] = os.path.abspath(dct['root'])
            dct['path'] = os.path.abspath(os.path.join(dct['root'], dct['path']))

            if 'write_path' not in dct:
                dct['write_path'] = dct['path']
            else:
                dct['write_path'] = os.path.abspath(os.path.join(dct['root'], dct['write_path']))

            dct['as_list'] = []
            dct['as_dict'] = {}

            for identifier, source_name in [(k, v) for k, v in dct.items() if isinstance(v, SourceName)]:
                file_name = source_name if not dct['extension'] else f"{source_name}.{dct['extension']}"
                dct[identifier] = dct['source_class'](
                    root=dct['root'],
                    path=os.path.join(dct['path'], file_name),
                    write_path=os.path.join(dct['write_path'], file_name)
                )
                dct['as_list'].append(dct[identifier])
                dct['as_dict'][source_name] = dct[identifier]

            for identifier, source in [(k, v) for k, v in dct.items() if isinstance(v, DataSource)]:
                dct['as_list'].append(source)
                dct['as_dict'][source.source_name] = source

            bases = tuple(list(bases) + [DataSetBase])

        cls = super().__new__(mcs, name, bases, dct)

        return cls


class DataSet(metaclass=DatasetMetaclass):
    source_class = None
    root = None
    path = None
    write_path = None
    extension = None
