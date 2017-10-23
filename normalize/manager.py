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
        for task in tqdm(self.tasks, desc='Setups ...'):
            try:
                self.data_helper = task.do_setup(self.data_helper)
            except Exception as e:
                self.log.exception(e)
                break
            self.log.debug('Success: Setup for {!r}'.format(task))

        for task in tqdm(self.tasks, desc='Processes ...'):
            try:
                self.data_helper = task.do_pre_process(self.data_helper)
            except Exception as e:
                self.log.error('Error: Pre-Process for {!r}'.format(task))
                self.log.exception(e)
                break
            self.log.debug('Success: Pre-Process for {!r}'.format(task))

            try:
                self.data_helper = task.do_process(self.data_helper)
            except Exception as e:
                self.log.error('Error: Process for {!r}'.format(task))
                self.log.exception(e)
                break
            self.log.debug('Success: Process for {!r}'.format(task))

            try:
                self.data_helper = task.do_post_process(self.data_helper)
            except Exception as e:
                self.log.error('Error: Post-Process for {!r}'.format(task))
                self.log.exception(e)
                break
            self.log.debug('Success: Post-Process for {!r}'.format(task))

        for task in tqdm(self.tasks, desc='Teardowns'):
            try:
                self.data_helper = task.do_teardown(self.data_helper)
            except Exception as e:
                self.log.exception(e)
                break
            self.log.debug('Success: Teardown for {!r}'.format(task))


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


class Task(object):
    log = logging.getLogger(__name__)

    def __init__(self):
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
