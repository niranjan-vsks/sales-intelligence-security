"""Logging and tracing through Logfire, falling back to console output with no token."""

import logfire

from sis.config import settings

log = logfire

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    if settings.LOGFIRE_TOKEN:
        logfire.configure(token=settings.LOGFIRE_TOKEN)
    else:
        logfire.configure(send_to_logfire=False, console=logfire.ConsoleOptions())
    _configured = True
