"""Application-level errors that the CLI can present without a traceback."""


class AudioExtenderError(Exception):
    """Base class for expected AudioExtender failures."""


class ConfigurationError(AudioExtenderError, ValueError):
    """Configuration or command-line values are inconsistent."""


class AnalysisError(AudioExtenderError, RuntimeError):
    """A track could not be analyzed reliably."""


class CandidateSelectionError(AudioExtenderError, RuntimeError):
    """No candidate satisfies the requested musical constraints."""


class StemSeparationError(AudioExtenderError, RuntimeError):
    """Optional stem separation failed."""


class ExportError(AudioExtenderError, RuntimeError):
    """An output artifact could not be written."""
