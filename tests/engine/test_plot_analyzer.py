"""Stage 13D-3 tests for the unified single-item analysis boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

import math_drawing_assistant.engine.equation_validator as equation_validator_module
import math_drawing_assistant.engine.plot_analyzer as analyzer_module
from math_drawing_assistant.engine.equation_classifier import (
    EquationGeometryError,
    EquationGeometryFailureKind,
)
from math_drawing_assistant.engine.equation_polynomial import (
    EquationPolynomialError,
    PolynomialFailureKind,
)
from math_drawing_assistant.engine.equation_validator import (
    EquationValidationError,
    EquationValidationFailureKind,
)
from math_drawing_assistant.engine.exact_rational import ExactLimitComponent
from math_drawing_assistant.engine.plot_analyzer import analyze_plot_item
from math_drawing_assistant.engine.validators import analyze_explicit_function
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo, SourceSpan
from math_drawing_assistant.models.plot_specs import (
    CircleSpec,
    ExplicitFunctionSpec,
    LineSpec,
    ParabolaSpec,
)
from math_drawing_assistant.models.requests import PlotItemRequest
from math_drawing_assistant.models.state import InputSource, PlotKind


def _request(text: str, kind: PlotKind = PlotKind.AUTO) -> PlotItemRequest:
    return PlotItemRequest(
        item_id="item-13d3",
        input_text=text,
        input_source=InputSource.MANUAL,
        requested_plot_kind=kind,
        display_order=0,
        style_key=None,
    )


_ROUTE_MATRIX = (
    ("y=2*x+1", PlotKind.AUTO, ExplicitFunctionSpec),
    ("y=2*x+1", PlotKind.EXPLICIT_FUNCTION, ExplicitFunctionSpec),
    ("y=2*x+1", PlotKind.LINE_EQUATION, ErrorCode.INVALID_REQUEST),
    ("y=2*x+1", PlotKind.CONIC_EQUATION, ErrorCode.INVALID_REQUEST),
    ("x=y", PlotKind.AUTO, ExplicitFunctionSpec),
    ("x=y", PlotKind.EXPLICIT_FUNCTION, ExplicitFunctionSpec),
    ("x=y", PlotKind.LINE_EQUATION, ErrorCode.INVALID_REQUEST),
    ("x=y", PlotKind.CONIC_EQUATION, ErrorCode.INVALID_REQUEST),
    ("x=2", PlotKind.AUTO, LineSpec),
    ("x=2", PlotKind.EXPLICIT_FUNCTION, ErrorCode.UNSUPPORTED_EQUATION),
    ("x=2", PlotKind.LINE_EQUATION, LineSpec),
    ("x=2", PlotKind.CONIC_EQUATION, ErrorCode.INVALID_REQUEST),
    ("x+y=1", PlotKind.AUTO, LineSpec),
    ("x+y=1", PlotKind.EXPLICIT_FUNCTION, ErrorCode.UNSUPPORTED_EQUATION),
    ("x+y=1", PlotKind.LINE_EQUATION, LineSpec),
    ("x+y=1", PlotKind.CONIC_EQUATION, ErrorCode.INVALID_REQUEST),
    ("x^2+y^2=25", PlotKind.AUTO, CircleSpec),
    (
        "x^2+y^2=25",
        PlotKind.EXPLICIT_FUNCTION,
        ErrorCode.UNSUPPORTED_EQUATION,
    ),
    ("x^2+y^2=25", PlotKind.LINE_EQUATION, ErrorCode.INVALID_REQUEST),
    ("x^2+y^2=25", PlotKind.CONIC_EQUATION, CircleSpec),
    ("x^2=4*y", PlotKind.AUTO, ParabolaSpec),
    ("x^2=4*y", PlotKind.EXPLICIT_FUNCTION, ErrorCode.UNSUPPORTED_EQUATION),
    ("x^2=4*y", PlotKind.LINE_EQUATION, ErrorCode.INVALID_REQUEST),
    ("x^2=4*y", PlotKind.CONIC_EQUATION, ParabolaSpec),
    ("y=x+y", PlotKind.AUTO, LineSpec),
    (
        "y=x+y",
        PlotKind.EXPLICIT_FUNCTION,
        ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED,
    ),
    ("y=x+y", PlotKind.LINE_EQUATION, LineSpec),
    ("y=x+y", PlotKind.CONIC_EQUATION, ErrorCode.INVALID_REQUEST),
)


@pytest.mark.parametrize(("text", "kind", "expected"), _ROUTE_MATRIX)
def test_complete_typed_route_and_requested_kind_matrix(
    text: str,
    kind: PlotKind,
    expected: type[object] | ErrorCode,
) -> None:
    result = analyze_plot_item(_request(text, kind))

    if isinstance(expected, ErrorCode):
        assert type(result) is ErrorInfo
        assert result.code is expected
        assert result.item_id == "item-13d3"
        if expected is ErrorCode.INVALID_REQUEST:
            assert result.field_name == "requested_plot_kind"
            assert result.source_location is None
            assert result.recoverable is True
        return
    assert type(result) is expected
    assert result.item_id == "item-13d3"


_EXPRESSION_MATRIX = (
    ("x", PlotKind.AUTO, ExplicitFunctionSpec),
    ("x", PlotKind.EXPLICIT_FUNCTION, ExplicitFunctionSpec),
    ("x", PlotKind.LINE_EQUATION, ErrorCode.INVALID_REQUEST),
    ("x", PlotKind.CONIC_EQUATION, ErrorCode.INVALID_REQUEST),
    ("x+1", PlotKind.AUTO, ExplicitFunctionSpec),
    ("x+1", PlotKind.EXPLICIT_FUNCTION, ExplicitFunctionSpec),
    ("x+1", PlotKind.LINE_EQUATION, ErrorCode.INVALID_REQUEST),
    ("x+1", PlotKind.CONIC_EQUATION, ErrorCode.INVALID_REQUEST),
    ("x+y", PlotKind.AUTO, ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED),
    (
        "x+y",
        PlotKind.EXPLICIT_FUNCTION,
        ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED,
    ),
    ("x+y", PlotKind.LINE_EQUATION, ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED),
    (
        "x+y",
        PlotKind.CONIC_EQUATION,
        ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED,
    ),
    ("sin(x)+y", PlotKind.AUTO, ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED),
    (
        "sin(x)+y",
        PlotKind.EXPLICIT_FUNCTION,
        ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED,
    ),
    (
        "sin(x)+y",
        PlotKind.LINE_EQUATION,
        ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED,
    ),
    (
        "sin(x)+y",
        PlotKind.CONIC_EQUATION,
        ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED,
    ),
)


@pytest.mark.parametrize(("text", "kind", "expected"), _EXPRESSION_MATRIX)
def test_expression_inputs_are_never_reinterpreted_as_equations(
    text: str,
    kind: PlotKind,
    expected: type[object] | ErrorCode,
) -> None:
    result = analyze_plot_item(_request(text, kind))

    if isinstance(expected, ErrorCode):
        assert type(result) is ErrorInfo
        assert result.code is expected
        assert result.item_id == "item-13d3"
    else:
        assert type(result) is expected


@pytest.mark.parametrize(
    ("text", "code"),
    (
        ("", ErrorCode.EMPTY_INPUT),
        ("unknown", ErrorCode.UNKNOWN_IDENTIFIER),
        ("x=y=1", ErrorCode.MULTIPLE_EQUALS),
        ("x+", ErrorCode.ILLEGAL_TRAILING),
    ),
)
def test_every_shared_frontend_error_only_gains_the_request_item_id(
    text: str,
    code: ErrorCode,
) -> None:
    request = _request(text)
    raw = analyzer_module.normalize_input(text)
    if not isinstance(raw, ErrorInfo):
        raw = analyzer_module.tokenize(raw)
    if not isinstance(raw, ErrorInfo):
        raw = analyzer_module.split_equation(raw)
    if not isinstance(raw, ErrorInfo):
        raw = analyzer_module.parse_input(raw)
    assert type(raw) is ErrorInfo

    result = analyze_plot_item(request)

    assert type(result) is ErrorInfo
    assert result.code is code
    assert result.item_id == request.item_id
    assert result.user_message == raw.user_message
    assert result.technical_message == raw.technical_message
    assert result.field_name == raw.field_name
    assert result.source_location == raw.source_location
    assert result.recoverable is raw.recoverable


def test_explicit_validation_error_only_gains_item_id() -> None:
    legacy = analyze_explicit_function("x+y")
    result = analyze_plot_item(_request("x+y"))

    assert type(legacy) is ErrorInfo
    assert type(result) is ErrorInfo
    assert result.item_id == "item-13d3"
    assert (
        result.code,
        result.user_message,
        result.technical_message,
        result.field_name,
        result.source_location,
        result.recoverable,
    ) == (
        legacy.code,
        legacy.user_message,
        legacy.technical_message,
        legacy.field_name,
        legacy.source_location,
        legacy.recoverable,
    )


@pytest.mark.parametrize(
    ("text", "code"),
    (
        ("pi*x=0", ErrorCode.EQUATION_NON_RATIONAL_COEFFICIENT),
        ("sin(x)=0", ErrorCode.EQUATION_NON_POLYNOMIAL),
        ("(x^2-1)/(x-1)=0", ErrorCode.EQUATION_VARIABLE_DENOMINATOR),
        ("x/0=1", ErrorCode.EQUATION_ZERO_DENOMINATOR),
        ("x^3=1", ErrorCode.EQUATION_DEGREE_EXCEEDED),
        ("x^0=1", ErrorCode.UNSUPPORTED_EQUATION),
    ),
)
def test_every_polynomial_failure_kind_has_an_explicit_error_code_mapping(
    text: str,
    code: ErrorCode,
) -> None:
    result = analyze_plot_item(_request(text))

    assert type(result) is ErrorInfo
    assert result.code is code
    assert result.item_id == "item-13d3"
    assert result.field_name == "input_text"
    assert result.recoverable is True


@pytest.mark.parametrize(
    ("text", "code"),
    (
        ("x*y=0", ErrorCode.ROTATED_CONIC_NOT_SUPPORTED),
        ("(x+y)^2=0", ErrorCode.ROTATED_CONIC_NOT_SUPPORTED),
        ("x^2-y^2=0", ErrorCode.DEGENERATE_CONIC),
        ("x^2+y^2=0", ErrorCode.DEGENERATE_CONIC),
        ("x^2+y^2=-1", ErrorCode.CONIC_HAS_NO_REAL_POINTS),
        ("0=0", ErrorCode.UNSUPPORTED_EQUATION),
        ("1=0", ErrorCode.UNSUPPORTED_EQUATION),
    ),
)
def test_equation_math_error_priority_precedes_requested_kind_mismatch(
    text: str,
    code: ErrorCode,
) -> None:
    for kind in (PlotKind.EXPLICIT_FUNCTION, PlotKind.LINE_EQUATION):
        result = analyze_plot_item(_request(text, kind))
        assert type(result) is ErrorInfo
        assert result.code is code


def test_equation_errors_use_original_source_spans() -> None:
    polynomial = analyze_plot_item(_request(" pi*x=0 "))
    geometry = analyze_plot_item(_request(" x²+y²=-1 "))

    assert type(polynomial) is ErrorInfo
    assert polynomial.source_location == SourceSpan(1, 3)
    assert type(geometry) is ErrorInfo
    assert geometry.code is ErrorCode.CONIC_HAS_NO_REAL_POINTS
    assert geometry.source_location == SourceSpan(1, 9)


def test_polynomial_resource_component_limit_and_span_are_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = EquationPolynomialError(
        PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED,
        SourceSpan(2, 4),
        SourceSpan(7, 11),
        ExactLimitComponent.COEFFICIENT_DENOMINATOR,
        17,
    )

    def fail(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise error

    monkeypatch.setattr(analyzer_module, "canonicalize_equation", fail)
    result = analyze_plot_item(_request("x=2"))

    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert result.source_location == SourceSpan(7, 11)
    assert "coefficient denominator" in result.technical_message
    assert "limit=17" in result.technical_message


def test_geometry_resource_component_limit_and_provenance_span_are_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = EquationGeometryError(
        EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED,
        ExactLimitComponent.CANONICAL_INTEGER,
        23,
    )

    def fail(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise error

    monkeypatch.setattr(analyzer_module, "classify_equation_geometry", fail)
    result = analyze_plot_item(_request(" x=2 "))

    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert result.source_location == SourceSpan(1, 4)
    assert "canonical integer" in result.technical_message
    assert "limit=23" in result.technical_message


def test_validation_failure_uses_typed_kind_and_exception_source_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_PARSER_METRICS,
            SourceSpan(2, 3),
            SourceSpan(8, 9),
        )

    monkeypatch.setattr(analyzer_module, "validate_equation_candidate", fail)
    result = analyze_plot_item(_request("x=2"))

    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.INVALID_AST
    assert result.source_location == SourceSpan(8, 9)
    assert result.technical_message == (
        "equation validation failed (invalid_parser_metrics)"
    )
    for forbidden in ("contract", "seal", "snapshot", "identity", "AST"):
        assert forbidden not in result.technical_message


def test_explicit_route_runs_the_frontend_once_and_no_equation_math(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = {"normalize": 0, "tokenize": 0, "split": 0, "parse": 0}

    def counted(name: str, function: Callable[..., object]) -> Callable[..., object]:
        def wrapper(*args: object, **kwargs: object) -> object:
            counts[name] += 1
            return function(*args, **kwargs)

        return wrapper

    monkeypatch.setattr(
        analyzer_module,
        "normalize_input",
        counted("normalize", analyzer_module.normalize_input),
    )
    monkeypatch.setattr(
        analyzer_module,
        "tokenize",
        counted("tokenize", analyzer_module.tokenize),
    )
    monkeypatch.setattr(
        analyzer_module,
        "split_equation",
        counted("split", analyzer_module.split_equation),
    )
    monkeypatch.setattr(
        analyzer_module,
        "parse_input",
        counted("parse", analyzer_module.parse_input),
    )

    def forbidden(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("equation math must not run for an explicit route")

    monkeypatch.setattr(analyzer_module, "canonicalize_equation", forbidden)
    monkeypatch.setattr(analyzer_module, "classify_equation_geometry", forbidden)

    result = analyze_plot_item(_request("y=2*x+1"))

    assert type(result) is ExplicitFunctionSpec
    assert counts == {"normalize": 1, "tokenize": 1, "split": 1, "parse": 1}


def test_equation_route_has_one_frontend_and_one_frozen_provenance_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = {"normalize": 0, "tokenize": 0, "split": 0, "parse": 0}

    def counted(name: str, function: Callable[..., object]) -> Callable[..., object]:
        def wrapper(*args: object, **kwargs: object) -> object:
            counts[name] += 1
            return function(*args, **kwargs)

        return wrapper

    monkeypatch.setattr(
        analyzer_module,
        "normalize_input",
        counted("normalize", analyzer_module.normalize_input),
    )
    monkeypatch.setattr(
        analyzer_module,
        "tokenize",
        counted("tokenize", analyzer_module.tokenize),
    )
    monkeypatch.setattr(
        analyzer_module,
        "split_equation",
        counted("split", analyzer_module.split_equation),
    )
    monkeypatch.setattr(
        analyzer_module,
        "parse_input",
        counted("parse", analyzer_module.parse_input),
    )
    monkeypatch.setattr(
        equation_validator_module,
        "tokenize",
        counted("tokenize", equation_validator_module.tokenize),
    )
    monkeypatch.setattr(
        equation_validator_module,
        "split_equation",
        counted("split", equation_validator_module.split_equation),
    )
    monkeypatch.setattr(
        equation_validator_module,
        "parse_input",
        counted("parse", equation_validator_module.parse_input),
    )

    result = analyze_plot_item(_request("x=2"))

    assert type(result) is LineSpec
    assert counts == {"normalize": 1, "tokenize": 2, "split": 2, "parse": 2}


def test_receipt_gate_precedes_canonicalizer_and_classifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reached = {"canonicalizer": False, "classifier": False}

    def reject(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )

    def canonicalizer(*args: object, **kwargs: object) -> object:
        del args, kwargs
        reached["canonicalizer"] = True
        raise AssertionError

    def classifier(*args: object, **kwargs: object) -> object:
        del args, kwargs
        reached["classifier"] = True
        raise AssertionError

    monkeypatch.setattr(analyzer_module, "_validate_validated_equation_input", reject)
    monkeypatch.setattr(analyzer_module, "canonicalize_equation", canonicalizer)
    monkeypatch.setattr(analyzer_module, "classify_equation_geometry", classifier)
    result = analyze_plot_item(_request("x=2"))

    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.INVALID_AST
    assert reached == {"canonicalizer": False, "classifier": False}


def test_forged_receipt_cannot_reach_equation_math(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reached = {"canonicalizer": False, "classifier": False}

    def forged(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return object()

    def forbidden(name: str) -> Callable[..., object]:
        def fail(*args: object, **kwargs: object) -> object:
            del args, kwargs
            reached[name] = True
            raise AssertionError

        return fail

    monkeypatch.setattr(analyzer_module, "validate_equation_candidate", forged)
    monkeypatch.setattr(
        analyzer_module,
        "canonicalize_equation",
        forbidden("canonicalizer"),
    )
    monkeypatch.setattr(
        analyzer_module,
        "classify_equation_geometry",
        forbidden("classifier"),
    )
    result = analyze_plot_item(_request("x=2"))

    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.INTERNAL_ERROR
    assert result.recoverable is False
    assert reached == {"canonicalizer": False, "classifier": False}


def test_auto_equation_upgrade_explicit_legacy_and_old_entry_are_isolated() -> None:
    auto = analyze_plot_item(_request("y=x+y", PlotKind.AUTO))
    requested_explicit = analyze_plot_item(
        _request("y=x+y", PlotKind.EXPLICIT_FUNCTION),
    )
    legacy = analyze_explicit_function("y=x+y")

    assert type(auto) is LineSpec
    assert type(requested_explicit) is ErrorInfo
    assert type(legacy) is ErrorInfo
    assert requested_explicit.code is ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED
    assert requested_explicit.code is legacy.code
    assert requested_explicit.user_message == legacy.user_message
    assert requested_explicit.technical_message == legacy.technical_message


def test_variable_zero_power_new_and_legacy_entry_contracts() -> None:
    equation = analyze_plot_item(_request("x^0+y=1"))
    direct_y = analyze_plot_item(_request("y=x^0"))
    expression = analyze_plot_item(_request("x^0"))
    legacy_direct_y = analyze_explicit_function("y=x^0")
    legacy_expression = analyze_explicit_function("x^0")

    assert type(equation) is ErrorInfo
    assert equation.code is ErrorCode.UNSUPPORTED_EQUATION
    assert type(direct_y) is ExplicitFunctionSpec
    assert type(expression) is ExplicitFunctionSpec
    assert type(legacy_direct_y) is not ErrorInfo
    assert type(legacy_expression) is not ErrorInfo


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("item_id", ""),
        ("input_text", None),
        ("input_source", "manual"),
        ("requested_plot_kind", "auto"),
        ("display_order", True),
        ("display_order", -1),
        ("style_key", 1),
        ("style_key", ""),
    ),
)
def test_defensively_tampered_request_fields_return_invalid_request(
    field_name: str,
    bad_value: object,
) -> None:
    request = _request("x")
    object.__setattr__(request, field_name, bad_value)

    result = analyze_plot_item(request)

    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.INVALID_REQUEST
    assert result.field_name == field_name
    assert result.item_id == (None if field_name == "item_id" else "item-13d3")


def test_request_and_limits_boundary_types_are_checked() -> None:
    with pytest.raises(TypeError, match="exact PlotItemRequest"):
        analyze_plot_item(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ApplicationLimits"):
        analyze_plot_item(_request("x"), limits=object())  # type: ignore[arg-type]


def test_analyzer_source_routes_only_by_typed_candidates_and_geometry() -> None:
    source = (
        Path(__file__).parents[2]
        / "math_drawing_assistant"
        / "engine"
        / "plot_analyzer.py"
    ).read_text(encoding="utf-8")

    assert "isinstance(route, ExplicitFunctionCandidate)" in source
    assert "type(route) is not EquationCandidate" in source
    assert "candidate.legacy_rejection_reason" in source
    assert "if error.code" not in source
    assert "if error.user_message" not in source
    assert "if error.recoverable" not in source
    assert "_replay_parser" not in source
    for forbidden in ("sympy", "numpy", "float(", "eval(", "exec(", "compile("):
        assert forbidden not in source
