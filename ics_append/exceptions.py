"""Custom exception hierarchy for ICS Append."""


class AppendError(Exception):
    """Base exception for all ICS append errors."""


class ConfigError(AppendError):
    """Configuration loading or validation error."""


class DataError(AppendError):
    """Data loading, validation, or processing error."""


class DetectionError(AppendError):
    """File or column detection error."""


class MergeError(AppendError):
    """Error during REF/DM merge."""


class MatchError(AppendError):
    """Error during ODD matching."""
