"""Capacity-bounded, redacting, failure-isolated project logging.

Untrusted values should be sent through :func:`log_event`, which applies a
field whitelist before formatting.  The handler filter applies text-pattern
redaction as a second line of defence for ordinary logger calls.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from math import isfinite
import os
from pathlib import Path
import re
import tempfile
from enum import Enum
from collections.abc import Sized

from math_drawing_assistant.config.limits import ApplicationLimits, DEFAULT_LIMITS


APPLICATION_NAME = "数学绘图助手"
PROJECT_LOGGER_NAME = "math_drawing_assistant"
LOG_FILE_NAME = "application.log"

_HANDLER_MARKER = "_math_drawing_assistant_managed_handler"
_SANITIZED_RECORD_MARKER = "_math_drawing_assistant_sanitized"
_REDACTED = "<redacted>"
_PATH_REDACTED = "<path-redacted>"

_SENSITIVE_FIELD_PARTS = (
    "authorization",
    "api_key",
    "apikey",
    "bearer",
    "password",
    "secret",
    "token",
)
_TEXT_FIELDS = frozenset(
    {
        "formula",
        "formula_text",
        "input_text",
        "normalized_input",
        "ocr",
        "ocr_text",
        "raw_text",
    },
)
_PATH_FIELDS = frozenset({"file_path", "filename", "path"})
_BINARY_FIELDS = frozenset(
    {
        "base64",
        "image",
        "image_base64",
        "image_bytes",
        "png",
        "png_bytes",
    },
)
_RESPONSE_FIELDS = frozenset(
    {
        "http_request",
        "http_response",
        "provider_request",
        "provider_response",
        "request_body",
        "response_body",
    },
)
_SAFE_FIELDS = frozenset(
    {
        "byte_length",
        "count",
        "elapsed_ms",
        "error_code",
        "exception_type",
        "item_id",
        "plot_kind",
        "request_id",
        "scene_revision",
        "stage",
        "status_code",
        "success",
        "version",
    },
)

_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_CREDENTIAL_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"token|secret|password)[\"']?\s*[:=]\s*"
    r"(?:[\"'][^\"']*[\"']|[^\s,;}\]]+)",
)
_PRIVATE_TEXT_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"(formula(?:_text)?|input_text|normalized_input|ocr(?:_text)?|raw_text)"
    r"[\"']?\s*[:=]\s*(?:[\"'][^\"']*[\"']|[^,;}\]\r\n]+)",
)
_UNC_PATH_PATTERN = re.compile(
    r"\\\\[^\\\s\"']+\\[^\\\s\"']+(?:\\[^\\\s\"']+)*",
)
_WINDOWS_PATH_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"(?:[A-Z]:\\(?:[^\\\s\"']+\\)*[^\\\s\"']*|"
    r"[A-Z]:/(?:[^/\s\"']+/)*[^/\s\"']*)",
)
_UNIX_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_:/])/(?:[^/\s\"']+/)+[^/\s\"']+",
)
_BASE64_PATTERN = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{40,}={0,2}")


def default_log_directory(local_app_data: str | Path | None = None) -> Path:
    """Return the application-name-aligned log directory.

    Windows uses ``LOCALAPPDATA``.  A system temporary directory is the safe
    fallback when that environment location is unavailable; no home directory
    is guessed.
    """

    if local_app_data is None:
        configured = os.environ.get("LOCALAPPDATA")
        base = Path(configured) if configured else Path(tempfile.gettempdir())
    else:
        base = Path(local_app_data)
    return base / APPLICATION_NAME / "logs"


def redact_text(text: str, maximum_length: int) -> str:
    """Apply pattern-based fallback redaction and a hard text-length bound."""

    if not isinstance(text, str):
        raise TypeError("text must be a string.")
    if isinstance(maximum_length, bool) or not isinstance(maximum_length, int):
        raise TypeError("maximum_length must be an integer.")
    if maximum_length <= 0:
        raise ValueError("maximum_length must be positive.")

    redacted = _BEARER_PATTERN.sub("Bearer <redacted>", text)
    redacted = _CREDENTIAL_PATTERN.sub(lambda match: f"{match.group(1)}={_REDACTED}", redacted)
    redacted = _PRIVATE_TEXT_PATTERN.sub(
        lambda match: f"{match.group(1)}=<text-redacted>",
        redacted,
    )
    redacted = _UNC_PATH_PATTERN.sub(_PATH_REDACTED, redacted)
    redacted = _WINDOWS_PATH_PATTERN.sub(_PATH_REDACTED, redacted)
    redacted = _UNIX_PATH_PATTERN.sub(_PATH_REDACTED, redacted)
    redacted = _BASE64_PATTERN.sub("<base64-redacted>", redacted)
    return _truncate(redacted, maximum_length)


def _truncate(value: str, maximum_length: int) -> str:
    if len(value) <= maximum_length:
        return value
    marker = "…<truncated>"
    return value[: max(0, maximum_length - len(marker))] + marker


def _safe_filename(value: object, maximum_length: int) -> str:
    if not isinstance(value, (str, Path)):
        return _PATH_REDACTED
    normalized = str(value).replace("\\", "/").rstrip("/")
    filename = normalized.rsplit("/", 1)[-1]
    if not filename or filename in {".", ".."}:
        return _PATH_REDACTED
    return redact_text(filename, maximum_length)


def _value_length(value: object) -> int | None:
    if not isinstance(value, Sized):
        return None
    try:
        return len(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _length_placeholder(kind: str, value: object) -> str:
    length = _value_length(value)
    return f"<{kind}-redacted:length={length if length is not None else 'unknown'}>"


def _sanitize_safe_value(value: object, maximum_length: int) -> object:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<bytes:length={len(value)}>"
    if isinstance(value, Enum):
        return _sanitize_safe_value(value.value, maximum_length)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if isfinite(value) else "<non-finite>"
    if isinstance(value, str):
        return redact_text(value, maximum_length)
    return f"<type:{type(value).__name__}>"


def _sanitize_field(name: str, value: object, maximum_length: int) -> object:
    normalized_name = name.casefold()
    if any(part in normalized_name for part in _SENSITIVE_FIELD_PARTS):
        return _REDACTED
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<bytes:length={len(value)}>"
    if normalized_name in _TEXT_FIELDS:
        return _length_placeholder("text", value)
    if normalized_name in _PATH_FIELDS:
        return _safe_filename(value, maximum_length)
    if normalized_name in _BINARY_FIELDS:
        return _length_placeholder("binary", value)
    if normalized_name in _RESPONSE_FIELDS:
        return _length_placeholder("response", value)
    if normalized_name not in _SAFE_FIELDS:
        return "<field-redacted>"
    return _sanitize_safe_value(value, maximum_length)


class RedactingFilter(logging.Filter):
    """Second-line protection for records not created by ``log_event``."""

    def __init__(self, maximum_length: int) -> None:
        super().__init__()
        self._maximum_length = maximum_length

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, _SANITIZED_RECORD_MARKER, False):
            record.args = ()
            return True
        try:
            if isinstance(record.msg, (bytes, bytearray, memoryview)):
                message = f"<bytes:length={len(record.msg)}>"
            else:
                message = record.getMessage()
            record.msg = redact_text(message, self._maximum_length)
        except Exception:
            record.msg = "<log-message-redacted>"
        record.args = ()
        return True


class FailSafeRotatingFileHandler(RotatingFileHandler):
    """A rotating handler whose reporting path cannot escape into business code."""

    def handleError(self, record: logging.LogRecord) -> None:
        del record
        return None


def _managed_handler(logger: logging.Logger) -> logging.Handler | None:
    for handler in logger.handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            return handler
    return None


def configure_logging(
    log_directory: str | Path | None = None,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
    logger_name: str = PROJECT_LOGGER_NAME,
) -> logging.Logger:
    """Configure one named logger without touching the global root logger.

    Directory or handler failures safely install a ``NullHandler``.  Repeated
    calls for the same logger never add a second managed handler.
    """

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if _managed_handler(logger) is not None:
        return logger

    target_directory = (
        default_log_directory() if log_directory is None else Path(log_directory)
    )
    handler: logging.Handler | None = None
    try:
        target_directory.mkdir(parents=True, exist_ok=True)
        handler = FailSafeRotatingFileHandler(
            target_directory / LOG_FILE_NAME,
            maxBytes=limits.max_log_file_bytes,
            backupCount=limits.log_backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
            ),
        )
        handler.addFilter(RedactingFilter(limits.max_log_field_text_length))
    except Exception:
        if handler is not None:
            try:
                handler.close()
            except Exception:
                pass
        handler = logging.NullHandler()

    setattr(handler, _HANDLER_MARKER, True)
    logger.addHandler(handler)
    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    limits: ApplicationLimits = DEFAULT_LIMITS,
    **fields: object,
) -> None:
    """Write one structured event after field-level sanitization.

    Unknown fields are represented by a fixed placeholder.  Logging failures
    are intentionally isolated from the caller.
    """

    try:
        safe_event = redact_text(event, limits.max_log_field_text_length)
        safe_fields = {
            name: _sanitize_field(
                name,
                value,
                limits.max_log_field_text_length,
            )
            for name, value in fields.items()
        }
        message = json.dumps(
            {"event": safe_event, **safe_fields},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        logger.log(level, message, extra={_SANITIZED_RECORD_MARKER: True})
    except Exception:
        return None
