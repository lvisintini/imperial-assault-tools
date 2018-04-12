import errno
import json
import os
import sys
from collections import OrderedDict, defaultdict

from .exceptions import SourceError, MultipleEntriesDetectedSourceError, EntryNotFoundSourceError

ERROR_INVALID_NAME = 123


class DataSource:

    def fetch_data(self):
        raise NotImplementedError()

    def save_data(self):
        raise NotImplementedError()


class FileSource(DataSource):
    root = None
    path = None
    write_path = None
    source_name = None
    default = None

    def __init__(self, root=None, path=None, write_path=None, source_name=None, default=None):
        self.root = root or self.root
        self.path = path or self.path
        self.write_path = write_path or self.write_path
        self.source_name = source_name or self.source_name

        self.default = default or self.default

        if not self.write_path:
            self.write_path = self.path

        if self.default is None:
            if os.path.isfile(self.get_read_path()):
                raise SourceError(f"{self.get_read_path()} is not a file")
        elif not callable(self.default):
            raise SourceError("If 'default' is provided, it needs to be a callable")

        if not self.is_pathname_valid(self.get_write_path()) or os.path.isdir(self.get_write_path()):
            raise SourceError(f"{self.get_write_path()} is not a valid file write path")

        if not self.source_name:
            self.source_name = '.'.join(os.path.basename(self.path).split('.')[:-1])

    def get_read_path(self):
        return os.path.abspath(os.path.join(self.root, self.path))

    def get_write_path(self):
        return os.path.abspath(os.path.join(self.root, self.write_path))

    def __repr__(self):
        return f"{self.__class__.__name__}({self.source_name})"

    @staticmethod
    def is_pathname_valid(pathname):
        """
        `True` if the passed pathname is a valid pathname for the current OS;
        `False` otherwise.

        https://stackoverflow.com/questions/9532499
        """

        # If this pathname is either not a string or is but is empty, this pathname
        # is invalid.
        try:
            if not isinstance(pathname, str) or not pathname:
                return False

            # Strip this pathname's Windows-specific drive specifier (e.g., `C:\`)
            # if any. Since Windows prohibits path components from containing `:`
            # characters, failing to strip this `:`-suffixed prefix would
            # erroneously invalidate all valid absolute Windows pathnames.
            _, pathname = os.path.splitdrive(pathname)

            # Directory guaranteed to exist. If the current OS is Windows, this is
            # the drive to which Windows was installed (e.g., the "%HOMEDRIVE%"
            # environment variable); else, the typical root directory.
            root_dirname = os.environ.get('HOMEDRIVE', 'C:') \
                if sys.platform == 'win32' else os.path.sep
            assert os.path.isdir(root_dirname)   # ...Murphy and her ironclad Law

            # Append a path separator to this directory if needed.
            root_dirname = root_dirname.rstrip(os.path.sep) + os.path.sep

            # Test whether each path component split from this pathname is valid or
            # not, ignoring non-existent and non-readable path components.
            for pathname_part in pathname.split(os.path.sep):
                try:
                    os.lstat(root_dirname + pathname_part)
                # If an OS-specific exception is raised, its error code
                # indicates whether this pathname is valid or not. Unless this
                # is the case, this exception implies an ignorable kernel or
                # filesystem complaint (e.g., path not found or inaccessible).
                #
                # Only the following exceptions indicate invalid pathnames:
                #
                # * Instances of the Windows-specific "WindowsError" class
                #   defining the "winerror" attribute whose value is
                #   "ERROR_INVALID_NAME". Under Windows, "winerror" is more
                #   fine-grained and hence useful than the generic "errno"
                #   attribute. When a too-long pathname is passed, for example,
                #   "errno" is "ENOENT" (i.e., no such file or directory) rather
                #   than "ENAMETOOLONG" (i.e., file name too long).
                # * Instances of the cross-platform "OSError" class defining the
                #   generic "errno" attribute whose value is either:
                #   * Under most POSIX-compatible OSes, "ENAMETOOLONG".
                #   * Under some edge-case OSes (e.g., SunOS, *BSD), "ERANGE".
                except OSError as exc:
                    if hasattr(exc, 'winerror'):
                        if exc.winerror == ERROR_INVALID_NAME:
                            return False
                    elif exc.errno in {errno.ENAMETOOLONG, errno.ERANGE}:
                        return False
        # If a "TypeError" exception was raised, it almost certainly has the
        # error message "embedded NUL character" indicating an invalid pathname.
        except TypeError:
            return False
        # If no exception was raised, all path components and hence this
        # pathname itself are valid. (Praise be to the curmudgeonly python.)
        else:
            return True


class JSONSource(FileSource):
    indent = 2
    ensure_ascii = False

    def __init__(self, **kwargs):
        self.indent = kwargs.pop('indent', self.indent)
        self.ensure_ascii = kwargs.pop('ensure_ascii', self.ensure_ascii)
        super().__init__(**kwargs)

    def fetch_data(self):
        if self.default is not None and not os.path.isfile(self.get_read_path()):
            data = self.default()
        else:
            with open(self.get_read_path(), 'r') as file_object:
                data = json.load(file_object, object_pairs_hook=OrderedDict)
        setattr(self, 'data', data)
        return data

    def set_data(self, data):
        setattr(self, 'data', data)

    def save_data(self):
        path = self.get_write_path()

        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(self.get_write_path(), 'w') as file_object:
            json.dump(
                getattr(self, 'data'),
                file_object,
                indent=self.indent,
                ensure_ascii=self.ensure_ascii
            )


class JSONNestedDictSource(JSONSource):
    default = dict

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = self.recursive_defaultdict()

    def recursive_defaultdict(self):
        return defaultdict(self.recursive_defaultdict)

    def recursive_dict_transform(self, data):
        memory = self.recursive_defaultdict()
        for source in data.keys():
            for field_name in data[source].keys():
                for pk in data[source][field_name].keys():
                    memory[source][field_name][int(pk) if pk.isdigit() else pk] = data[source][field_name][pk]
        return memory

    def fetch_data(self):
        data = super().fetch_data()
        self.data = self.recursive_dict_transform(data)
        return self.data

    def set_data(self, data):
        super().set_data(data)
        self.data = self.recursive_dict_transform(self.data)


class JSONCollectionSource(JSONSource):
    default = list
    pk = 'id'

    def __init__(self, **kwargs):
        self.pk = kwargs.pop('pk', self.pk)
        super().__init__(**kwargs)

    def filter(self, **kwargs):
        return [m for m in self.data if all([k in m and m.get(k) == v for k, v in kwargs.items()])]

    def set_data(self, data=None):
        if data is None:
            data = self.default()
        if not isinstance(data, list):
            raise ValueError('Data value should be a list')
        self.data = data

    def add_entry(self, entry):
        self.data.append(entry)

    def get(self, **kwargs):
        filtered = self.filter(**kwargs)
        if len(filtered) > 1:
            raise MultipleEntriesDetectedSourceError()
        elif len(filtered) == 0:
            raise EntryNotFoundSourceError()
        return filtered[0]
