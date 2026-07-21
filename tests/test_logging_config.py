"""Behavioral tests for redaction, rotation, idempotence, and failure isolation."""

from __future__ import annotations

from dataclasses import replace
import logging
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import pytest

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.logging_config import (
    APPLICATION_NAME,
    LOG_FILE_NAME,
    FailSafeRotatingFileHandler,
    configure_logging,
    default_log_directory,
    log_event,
)


@pytest.fixture
def logger_name() -> Iterator[str]:
    name = f"math_drawing_assistant.test.{uuid4().hex}"
    yield name

    logger = logging.getLogger(name)
    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def _flush(logger: logging.Logger) -> None:
    for handler in logger.handlers:
        handler.flush()


def _read_log(directory: Path, logger: logging.Logger) -> str:
    _flush(logger)
    return (directory / LOG_FILE_NAME).read_text(encoding="utf-8")


def test_default_log_directory_uses_application_metadata_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_log_directory() == tmp_path / APPLICATION_NAME / "logs"


def test_logging_writes_to_injected_directory_without_touching_root(
    tmp_path: Path,
    logger_name: str,
) -> None:
    root_handlers = tuple(logging.getLogger().handlers)
    logger = configure_logging(tmp_path, logger_name=logger_name)
    log_event(logger, "configured", request_id=7, success=True)

    content = _read_log(tmp_path, logger)
    assert '"event":"configured"' in content
    assert '"request_id":7' in content
    assert tuple(logging.getLogger().handlers) == root_handlers
    assert logger.propagate is False


def test_repeated_configuration_does_not_duplicate_handlers(
    tmp_path: Path,
    logger_name: str,
) -> None:
    first = configure_logging(tmp_path, logger_name=logger_name)
    second = configure_logging(tmp_path, logger_name=logger_name)

    assert first is second
    assert len(first.handlers) == 1


def test_capacity_rotation_occurs_and_backup_count_is_bounded(
    tmp_path: Path,
    logger_name: str,
) -> None:
    rotation_limits = replace(
        DEFAULT_LIMITS,
        max_log_file_bytes=DEFAULT_LIMITS.max_log_field_text_length * 2,
    )
    logger = configure_logging(
        tmp_path,
        limits=rotation_limits,
        logger_name=logger_name,
    )
    payload = "x" * rotation_limits.max_log_field_text_length
    for index in range(rotation_limits.log_backup_count * 4):
        log_event(
            logger,
            "rotation_probe",
            limits=rotation_limits,
            request_id=index + 1,
            item_id=payload,
        )
    _flush(logger)

    backups = tuple(tmp_path.glob(f"{LOG_FILE_NAME}.*"))
    assert (tmp_path / LOG_FILE_NAME).is_file()
    assert backups
    assert len(backups) <= rotation_limits.log_backup_count


def test_field_whitelist_redacts_credentials_private_text_paths_and_payloads(
    tmp_path: Path,
    logger_name: str,
) -> None:
    logger = configure_logging(tmp_path, logger_name=logger_name)
    secrets = {
        "authorization": "Bearer auth-private-marker",
        "api_key": "api-private-marker",
        "token": "token-private-marker",
        "secret": "secret-private-marker",
        "password": "password-private-marker",
    }
    log_event(
        logger,
        "sensitive_fields",
        **secrets,
        formula="y=sin(formula-private-marker)",
        ocr_text="ocr-private-marker",
        path=r"C:\Users\teacher\private\lesson.txt",
        png_bytes=b"PNG-private-marker",
        image_base64="base64-private-marker",
        provider_response="provider-private-marker",
        unknown_payload="unknown-private-marker",
    )
    log_event(logger, "unix_path", path="/home/teacher/private/notes.txt")
    log_event(
        logger,
        "unc_path",
        path=r"\\school-server\share\private\worksheet.png",
    )
    logger.info(
        "Authorization: Bearer raw-private-marker "
        "password=raw-password-marker "
        r"path=C:\Users\teacher\private\raw.png "
        "formula=y=x^2",
    )

    content = _read_log(tmp_path, logger)
    forbidden = (
        *secrets.values(),
        "formula-private-marker",
        "ocr-private-marker",
        r"C:\Users\teacher\private\lesson.txt",
        "/home/teacher/private/notes.txt",
        r"\\school-server\share\private\worksheet.png",
        "PNG-private-marker",
        "base64-private-marker",
        "provider-private-marker",
        "unknown-private-marker",
        "raw-private-marker",
        "raw-password-marker",
        r"C:\Users\teacher\private\raw.png",
        "y=x^2",
    )
    for private_value in forbidden:
        assert private_value not in content

    assert "<redacted>" in content
    assert "<text-redacted:length=" in content
    assert "<bytes:length=" in content
    assert "lesson.txt" in content
    assert "notes.txt" in content
    assert "worksheet.png" in content


def test_overlong_safe_field_is_bounded(
    tmp_path: Path,
    logger_name: str,
) -> None:
    logger = configure_logging(tmp_path, logger_name=logger_name)
    marker = "字段-" * DEFAULT_LIMITS.max_log_field_text_length
    log_event(logger, "long_field", item_id=marker)

    content = _read_log(tmp_path, logger)
    assert marker not in content
    assert "<truncated>" in content


def test_directory_creation_failure_degrades_without_raising(
    tmp_path: Path,
    logger_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked = tmp_path / "blocked" / "logs"
    original_mkdir = Path.mkdir

    def fail_target_mkdir(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if path == blocked:
            raise OSError("simulated directory failure")
        original_mkdir(
            path,
            mode=mode,
            parents=parents,
            exist_ok=exist_ok,
        )

    monkeypatch.setattr(Path, "mkdir", fail_target_mkdir)
    logger = configure_logging(blocked, logger_name=logger_name)
    log_event(logger, "business_continues", request_id=1)

    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.NullHandler)
    assert not blocked.exists()


def test_rotation_emit_failure_is_swallowed_and_code_continues(
    tmp_path: Path,
    logger_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure_limits = replace(
        DEFAULT_LIMITS,
        max_log_file_bytes=DEFAULT_LIMITS.max_log_field_text_length,
    )
    logger = configure_logging(
        tmp_path,
        limits=failure_limits,
        logger_name=logger_name,
    )
    handler = logger.handlers[0]
    assert isinstance(handler, FailSafeRotatingFileHandler)

    def fail_rotation() -> None:
        raise OSError("simulated rotation failure")

    monkeypatch.setattr(handler, "doRollover", fail_rotation)
    logger.info("x" * failure_limits.max_log_field_text_length)
    ordinary_code_ran = True

    assert ordinary_code_ran is True
