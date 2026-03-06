"""Shared exceptions for data hub."""


class DataHubError(RuntimeError):
    """Base error for data hub failures."""


class DataSourceError(DataHubError):
    """A source adapter raised an error."""


class DataUnavailableError(DataHubError):
    """No source can provide valid data."""


class AdapterNotSupportedError(DataHubError):
    """Adapter does not support requested metric."""

