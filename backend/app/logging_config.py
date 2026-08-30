import logging
import sys

# Third-party libraries that log verbosely at INFO and drown out application
# logs (faster-whisper model loading, HTTP client internals). Capped at
# WARNING regardless of the app's own log level.
_NOISY_LOGGERS = ["httpx", "httpcore", "faster_whisper", "openai"]

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s :: %(message)s"


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.handlers = [handler]

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
