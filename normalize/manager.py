import logging
from types import MethodType
from tqdm import tqdm


class DataHelperInstanceNotReturnedError(Exception):
    pass


class DataHelper(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class PipelineHelper(object):
    tasks = []

    def __init__(self, data_helper=None, **kwargs):
        self.data_helper = DataHelper(**kwargs) if data_helper is None else data_helper
        if data_helper is not None:
            self.data_helper.__dict__.update(kwargs)

        logger = logging.getLogger(__name__)
        self.log = logger
        self.data_helper.log = logger

    def run(self):
        for task in tqdm([t for t in self.tasks if hasattr(t, 'setup')], desc='Setups'):
            self.log.debug('Setup for {!r}'.format(task))
            try:
                self.data_helper = task.do_setup(self.data_helper)
            except Exception as e:
                self.log.error('Setup for {!r}'.format(task))
                self.log.exception(e)
                break

        for task in tqdm([t for t in self.tasks if hasattr(t, 'process')], desc='Processes'):
            if hasattr(task, 'pre_process'):
                self.log.debug('Pre-Process for {!r}'.format(task))
                try:
                    self.data_helper = task.do_pre_process(self.data_helper)
                except Exception as e:
                    self.log.error('Pre-Process for {!r}'.format(task))
                    self.log.exception(e)
                    break

            self.log.debug('Process for {!r}'.format(task))
            try:
                self.data_helper = task.do_process(self.data_helper)
            except Exception as e:
                self.log.error('Error: Process for {!r}'.format(task))
                self.log.exception(e)
                break

            if hasattr(task, 'post_process'):
                self.log.debug('Post-Process for {!r}'.format(task))
                try:
                    self.data_helper = task.do_post_process(self.data_helper)
                except Exception as e:
                    self.log.error('Post-Process for {!r}'.format(task))
                    self.log.exception(e)
                    break

        for task in tqdm([t for t in self.tasks if hasattr(t, 'teardown')], desc='Teardowns'):
            self.log.debug('Teardown for {!r}'.format(task))
            try:
                self.data_helper = task.do_teardown(self.data_helper)
            except Exception as e:
                self.log.error('Teardown for {!r}'.format(task))
                self.log.exception(e)
                break


# These functions are attached to Task as a class method (were `this` would the Task class)
# If Task is instantiated, then these functions override the class methods with regular instance methods
# (were, `this` would be a Task class instance)
#
# This way, these functions can be accessed from a class or an instance


def _do_pre_process(this, data_helper):
    if hasattr(this, 'pre_process'):
        res = this.pre_process(data_helper)

        if not isinstance(res, DataHelper):
            raise DataHelperInstanceNotReturnedError(
                '{!r}.pre_process did not return a DataHelperInstance'.format(this)
            )

        return res
    return data_helper


def _do_process(this, data_helper):
    if not hasattr(this, 'process'):
        raise NotImplementedError('process method should be implemented for every Task class/instance')
    res = this.process(data_helper)

    if not isinstance(res, DataHelper):
        raise DataHelperInstanceNotReturnedError(
            '{!r}.process did not return a DataHelperInstance'.format(this)
        )

    return res


def _do_post_process(this, data_helper):
    if hasattr(this, 'post_process'):
        res = this.post_process(data_helper)

        if not isinstance(res, DataHelper):
            raise DataHelperInstanceNotReturnedError(
                '{!r}.post_process did not return a DataHelperInstance'.format(this)
            )

        return res
    return data_helper


def _do_setup(this, data_helper):
    if hasattr(this, 'setup'):
        res = this.setup(data_helper)

        if not isinstance(res, DataHelper):
            raise DataHelperInstanceNotReturnedError(
                '{!r}.setup did not return a DataHelperInstance'.format(this)
            )

        return res
    return data_helper


def _do_teardown(this, data_helper):
    if hasattr(this, 'teardown'):
        res = this.teardown(data_helper)

        if not isinstance(res, DataHelper):
            raise DataHelperInstanceNotReturnedError(
                '{!r}.teardown did not return a DataHelperInstance'.format(this)
            )

        return res
    return data_helper


class ReprMeta(type):
    def __call__(cls, *args, **kwargs):
        label = kwargs.pop('label', None)

        inst = super(ReprMeta, cls).__call__(*args, **kwargs)

        if not label:
            if not getattr(inst, 'label', None):
                if args and kwargs:
                    inst.label = f'{cls.__name__} args={args!r}, kwargs={kwargs!r}'
                elif args:
                    inst.label = f'{cls.__name__} args={args!r}'
                elif kwargs:
                    inst.label = f'{cls.__name__} kwargs={kwargs!r}'
                else:
                    inst.label = cls.__name__
        else:
            inst.label = label

        return inst


class Task(object, metaclass=ReprMeta):
    log = logging.getLogger(__name__)

    def __init__(self, *args, **kwargs):
        self.do_setup = MethodType(_do_setup, self)
        self.do_pre_process = MethodType(_do_pre_process, self)
        self.do_process = MethodType(_do_process, self)
        self.do_post_process = MethodType(_do_post_process, self)
        self.do_teardown = MethodType(_do_teardown, self)

    do_setup = classmethod(_do_setup)
    do_pre_process = classmethod(_do_pre_process)
    do_process = classmethod(_do_process)
    do_post_process = classmethod(_do_post_process)
    do_teardown = classmethod(_do_teardown)

    def __repr__(self):
        return getattr(self, 'label', super().__repr__())
