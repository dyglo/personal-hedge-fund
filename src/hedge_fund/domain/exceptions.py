class HedgeFundError(Exception):
    """Base application exception."""


class ConfigurationError(HedgeFundError):
    """Invalid application configuration."""


class ProviderError(HedgeFundError):
    """Raised when an external provider fails."""


class DataUnavailableError(HedgeFundError):
    """Raised when fallback providers cannot satisfy a request."""


class PersistenceError(HedgeFundError):
    """Raised when the database layer fails."""
