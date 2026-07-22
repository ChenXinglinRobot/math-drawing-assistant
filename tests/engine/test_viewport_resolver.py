"""Phase 8B tests for single explicit-function viewport resolution."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace

import pytest

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    ViewportResolution,
    analyze_explicit_function,
    build_explicit_scene_spec,
    resolve_single_explicit_viewport,
)
from math_drawing_assistant.engine import viewport_resolver
from math_drawing_assistant.models import (
    AspectRequest,
    ErrorCode,
    ErrorInfo,
    InputSource,
    PlotItemRequest,
    PlotKind,
    ResolvedViewport,
    ValidatedExplicitExpression,
    ViewportMode,
    ViewportRequest,
    ViewportSource,
)
from math_drawing_assistant.models.errors import (
    ViewportWarning,
    ViewportWarningCode,
)


def _scene(text: str = "x", *, item_id: str = "viewport-item"):
    validated = analyze_explicit_function(text)
    assert isinstance(validated, ValidatedExplicitExpression), validated
    request = PlotItemRequest(
        item_id=item_id,
        input_text=text,
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.EXPLICIT_FUNCTION,
        display_order=0,
    )
    scene = build_explicit_scene_spec(request, validated)
    assert not isinstance(scene, ErrorInfo), scene
    return scene


def _success(result: ViewportResolution) -> ResolvedViewport:
    assert result.error is None, result
    assert isinstance(result.viewport, ResolvedViewport)
    return result.viewport


def _error(result: ViewportResolution) -> ErrorInfo:
    assert result.viewport is None, result
    assert isinstance(result.error, ErrorInfo)
    return result.error


def test_manual_viewport_preserves_all_bounds_aspect_and_source_without_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("manual viewport must not probe")

    monkeypatch.setattr(viewport_resolver.np, "linspace", forbidden)
    monkeypatch.setattr(viewport_resolver, "execute_explicit_function", forbidden)
    request = ViewportRequest(
        mode=ViewportMode.MANUAL,
        x_min=-3,
        x_max=7,
        y_min=-2,
        y_max=8,
        aspect_request=AspectRequest.EQUAL,
    )

    viewport = _success(resolve_single_explicit_viewport(_scene("sin(x)"), request))

    assert (viewport.x_min, viewport.x_max, viewport.y_min, viewport.y_max) == (
        -3.0,
        7.0,
        -2.0,
        8.0,
    )
    assert viewport.aspect is AspectRequest.EQUAL
    assert viewport.source is ViewportSource.MANUAL


@pytest.mark.parametrize(
    ("kwargs", "field_name"),
    [
        ({"x_min": 2, "x_max": 1, "y_min": -1, "y_max": 1}, "x_bounds"),
        ({"x_min": -1, "x_max": 1, "y_min": 3, "y_max": 2}, "y_bounds"),
    ],
)
def test_manual_invalid_order_returns_typed_error_without_fallback(
    kwargs: dict[str, float],
    field_name: str,
) -> None:
    request = ViewportRequest(mode=ViewportMode.MANUAL, **kwargs)

    error = _error(resolve_single_explicit_viewport(_scene(), request))

    assert error.code is ErrorCode.INVALID_VIEWPORT
    assert error.field_name == field_name


def test_auto_default_x_and_robust_probe_return_probe_source() -> None:
    viewport = _success(
        resolve_single_explicit_viewport(
            _scene("x"),
            ViewportRequest(aspect_request=AspectRequest.EQUAL),
        ),
    )

    assert (viewport.x_min, viewport.x_max) == (-10.0, 10.0)
    assert viewport.y_min < -9.0
    assert viewport.y_max > 9.0
    assert viewport.aspect is AspectRequest.EQUAL
    assert viewport.source is ViewportSource.AUTO_PROBE


def test_auto_full_x_range_is_preserved() -> None:
    viewport = _success(
        resolve_single_explicit_viewport(
            _scene("x^2"),
            ViewportRequest(x_min=-2, x_max=3),
        ),
    )

    assert (viewport.x_min, viewport.x_max) == (-2.0, 3.0)
    assert viewport.source is ViewportSource.AUTO_PROBE


@pytest.mark.parametrize(
    "viewport_request",
    [
        ViewportRequest(x_min=-2),
        ViewportRequest(x_max=2),
        ViewportRequest(y_min=-2, y_max=2),
    ],
)
def test_auto_partial_or_explicit_y_bounds_return_typed_error(
    viewport_request: ViewportRequest,
) -> None:
    error = _error(
        resolve_single_explicit_viewport(_scene(), viewport_request),
    )

    assert error.code is ErrorCode.INVALID_VIEWPORT


def test_constant_is_centered_with_minimum_y_span() -> None:
    viewport = _success(
        resolve_single_explicit_viewport(_scene("2"), ViewportRequest()),
    )

    assert viewport.source is ViewportSource.AUTO_PROBE
    assert viewport.y_min < 2 < viewport.y_max
    assert viewport.y_max - viewport.y_min >= DEFAULT_LIMITS.min_viewport_span


def test_partial_domain_with_enough_finite_values_is_accepted() -> None:
    viewport = _success(
        resolve_single_explicit_viewport(_scene("sqrt(x)"), ViewportRequest()),
    )

    assert viewport.source is ViewportSource.AUTO_PROBE
    assert viewport.y_min < 0 < viewport.y_max


def test_unreliable_probe_falls_back_with_typed_warning_and_preserves_given_x() -> None:
    result = resolve_single_explicit_viewport(
        _scene("sqrt(-1)"),
        ViewportRequest(x_min=-2, x_max=3),
    )
    viewport = _success(result)

    assert (viewport.x_min, viewport.x_max) == (-2.0, 3.0)
    assert (viewport.y_min, viewport.y_max) == (-10.0, 10.0)
    assert viewport.source is ViewportSource.AUTO_FALLBACK
    assert isinstance(result.warning, ViewportWarning)
    assert result.warning.code is ViewportWarningCode.AUTO_VIEWPORT_FALLBACK


def test_unreliable_default_probe_uses_configured_fallback_x_and_y() -> None:
    limits = replace(
        DEFAULT_LIMITS,
        fallback_auto_x_min=-4,
        fallback_auto_x_max=6,
        fallback_auto_y_min=-7,
        fallback_auto_y_max=9,
    )

    viewport = _success(
        resolve_single_explicit_viewport(
            _scene("sqrt(-1)"),
            ViewportRequest(),
            limits=limits,
        ),
    )

    assert (viewport.x_min, viewport.x_max, viewport.y_min, viewport.y_max) == (
        -4.0,
        6.0,
        -7.0,
        9.0,
    )


def test_probe_budget_fails_before_grid_or_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("budget failure must precede probing")

    monkeypatch.setattr(viewport_resolver.np, "linspace", forbidden)
    monkeypatch.setattr(viewport_resolver, "execute_explicit_function", forbidden)
    limits = replace(DEFAULT_LIMITS, max_viewport_probe_bytes=1)

    error = _error(
        resolve_single_explicit_viewport(_scene("x"), ViewportRequest(), limits=limits),
    )

    assert error.code is ErrorCode.VIEWPORT_PROBE_BUDGET_EXCEEDED


def test_executor_error_never_becomes_a_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="Executor contract failed.",
        field_name="numeric_execution",
        recoverable=False,
    )
    monkeypatch.setattr(
        viewport_resolver,
        "execute_explicit_function",
        lambda *args, **kwargs: expected,
    )

    error = _error(resolve_single_explicit_viewport(_scene("x"), ViewportRequest()))

    assert error is expected


def test_resolution_is_frozen_and_has_no_array_bearing_fields() -> None:
    result = resolve_single_explicit_viewport(_scene("x"), ViewportRequest())
    viewport = _success(result)

    assert ViewportResolution.__dataclass_params__.frozen is True
    assert "__dict__" not in ViewportResolution.__dict__
    assert {field.name for field in fields(ViewportResolution)} == {
        "viewport",
        "warning",
        "error",
    }
    with pytest.raises(FrozenInstanceError):
        result.viewport = viewport  # type: ignore[misc]


def test_scene_must_contain_exactly_one_explicit_function_spec() -> None:
    scene = _scene()
    two_items = type(scene)(
        (scene.items[0], _scene("x+1", item_id="viewport-item-2").items[0]),
    )

    error = _error(
        resolve_single_explicit_viewport(two_items, ViewportRequest()),
    )

    assert error.code is ErrorCode.INVALID_REQUEST
    assert error.field_name == "scene_spec"
