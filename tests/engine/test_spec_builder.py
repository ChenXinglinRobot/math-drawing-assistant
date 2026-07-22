"""Stage 8A tests for the validated explicit-function scene handoff."""

from __future__ import annotations

from dataclasses import fields, replace
from typing import cast

import pytest

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    analyze_explicit_function,
    build_explicit_function_spec,
    build_explicit_scene_spec,
)
from math_drawing_assistant.models import (
    ErrorCode,
    ErrorInfo,
    ExplicitFunctionSpec,
    InputSource,
    PlotItemRequest,
    PlotItemSpec,
    PlotKind,
    PlotSceneSpec,
    RestrictedExpression,
    ValidatedExplicitExpression,
)


def _request(
    *,
    item_id: str = "item-1",
    requested_plot_kind: PlotKind = PlotKind.AUTO,
    display_order: int = 7,
) -> PlotItemRequest:
    return PlotItemRequest(
        item_id=item_id,
        input_text="y=x^2",
        input_source=InputSource.MANUAL,
        requested_plot_kind=requested_plot_kind,
        display_order=display_order,
    )


def _validated(text: str = "y=x^2") -> ValidatedExplicitExpression:
    result = analyze_explicit_function(text)
    assert isinstance(result, ValidatedExplicitExpression), result
    return result


@pytest.mark.parametrize(
    "requested_plot_kind",
    [PlotKind.AUTO, PlotKind.EXPLICIT_FUNCTION],
)
def test_request_and_validated_expression_build_one_explicit_scene(
    requested_plot_kind: PlotKind,
) -> None:
    request = _request(requested_plot_kind=requested_plot_kind)
    validated = _validated()

    item_spec = build_explicit_function_spec(request, validated)
    scene_spec = build_explicit_scene_spec(request, validated)

    assert isinstance(item_spec, ExplicitFunctionSpec)
    assert isinstance(item_spec, PlotItemSpec)
    assert item_spec.item_id == request.item_id
    assert item_spec.validated_expression is validated
    assert item_spec.expression is validated.expression
    assert item_spec.plot_kind is PlotKind.EXPLICIT_FUNCTION
    assert item_spec.limits_version == DEFAULT_LIMITS.version
    assert isinstance(scene_spec, PlotSceneSpec)
    assert len(scene_spec.items) == 1
    assert isinstance(scene_spec.items[0], ExplicitFunctionSpec)
    assert scene_spec.items[0].item_id == request.item_id
    assert scene_spec.items[0].expression is validated.expression


def test_scene_tuple_order_is_authoritative_without_copying_display_order() -> None:
    scene_spec = build_explicit_scene_spec(
        _request(display_order=99),
        _validated("sin(x)"),
    )

    assert isinstance(scene_spec, PlotSceneSpec)
    item_spec = scene_spec.items[0]
    assert isinstance(scene_spec.items, tuple)
    assert "display_order" not in {field.name for field in fields(item_spec)}
    assert not hasattr(item_spec, "display_order")


@pytest.mark.parametrize("item_id", [" ", "\t", "\r\n"])
def test_blank_item_id_is_rejected_at_the_builder_boundary(item_id: str) -> None:
    result = build_explicit_scene_spec(_request(item_id=item_id), _validated())

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INVALID_REQUEST
    assert result.field_name == "item_id"
    assert result.recoverable is True


def test_non_string_item_id_that_slipped_through_request_is_rejected() -> None:
    request = _request(item_id=cast(str, True))

    result = build_explicit_function_spec(request, _validated())

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INVALID_REQUEST
    assert result.field_name == "item_id"


@pytest.mark.parametrize(
    "requested_plot_kind",
    [PlotKind.LINE_EQUATION, PlotKind.CONIC_EQUATION],
)
def test_non_explicit_requested_plot_kind_is_rejected(
    requested_plot_kind: PlotKind,
) -> None:
    result = build_explicit_function_spec(
        _request(requested_plot_kind=requested_plot_kind),
        _validated(),
    )

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INVALID_REQUEST
    assert result.field_name == "requested_plot_kind"


def _old_unsealed_result() -> ValidatedExplicitExpression:
    current = _validated()
    old = object.__new__(ValidatedExplicitExpression)
    for name in (
        "expression",
        "normalized_input",
        "normalized_span",
        "source_span",
        "source_form",
        "free_variables",
        "limits_version",
    ):
        object.__setattr__(old, name, getattr(current, name))
    return old


@pytest.mark.parametrize(
    "injected",
    [
        "x",
        object(),
    ],
)
def test_string_and_arbitrary_object_cannot_replace_validated_result(
    injected: object,
) -> None:
    result = build_explicit_function_spec(
        _request(),
        cast(ValidatedExplicitExpression, injected),
    )

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INTERNAL_ERROR
    assert result.field_name == "validated_expression"
    assert result.recoverable is False


def test_plain_restricted_ast_cannot_be_injected_as_a_validated_result() -> None:
    expression: RestrictedExpression = _validated().expression

    result = build_explicit_scene_spec(
        _request(),
        cast(ValidatedExplicitExpression, expression),
    )

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INTERNAL_ERROR


def test_old_or_forged_validated_receipt_is_rejected() -> None:
    old = _old_unsealed_result()
    forged = _old_unsealed_result()
    object.__setattr__(forged, "_contract", object())

    for injected in (old, forged):
        result = build_explicit_function_spec(_request(), injected)
        assert isinstance(result, ErrorInfo)
        assert result.code is ErrorCode.INTERNAL_ERROR
        assert result.technical_message == (
            "validated explicit expression contract mismatch"
        )


def test_incompatible_active_limits_version_is_rejected_without_reparsing() -> None:
    incompatible = replace(DEFAULT_LIMITS, version="limits-v2-incompatible-test")

    result = build_explicit_scene_spec(
        _request(),
        _validated(),
        limits=incompatible,
    )

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INTERNAL_ERROR
    assert result.field_name == "validated_expression"


def test_explicit_spec_constructor_rejects_unvalidated_payloads() -> None:
    with pytest.raises(TypeError, match="ValidatedExplicitExpression"):
        ExplicitFunctionSpec(
            item_id="item-1",
            validated_expression=cast(ValidatedExplicitExpression, "x"),
        )
