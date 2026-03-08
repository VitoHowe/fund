"""Shared exceptions for data hub."""


class DataHubError(RuntimeError):
    """Base error for data hub failures."""


class DataSourceError(DataHubError):
    """A source adapter raised an error."""


class DataTimeoutError(DataSourceError):
    """A source request timed out."""


class DataTransportError(DataSourceError):
    """A source request failed at the transport layer."""


class DataUpstreamError(DataSourceError):
    """A source responded with a non-success upstream error."""


class DataProtocolError(DataSourceError):
    """A source returned an invalid or unexpected payload."""


class DataValidationError(DataSourceError):
    """A source returned a payload that is semantically unusable."""


class DataUnavailableError(DataHubError):
    """No source can provide valid data."""


class AdapterNotSupportedError(DataHubError):
    """Adapter does not support requested metric."""

