"""Application-level exception types.

Domain/infra exceptions that FastAPI maps to HTTP responses via handlers
registered in app.main. Keeping them here lets service-layer code raise
semantically-typed errors without importing FastAPI/HTTP concerns.
"""


class ConfigurationError(Exception):
    """Raised when required server-side configuration is missing or invalid.

    Maps to HTTP 500 (server misconfiguration), distinct from client-input
    ``ValueError`` which maps to HTTP 400.
    """
