class SourceError(Exception):
    pass


class MultipleEntriesDetectedSourceError(SourceError):
    pass


class EntryNotFoundSourceError(SourceError):
    pass
