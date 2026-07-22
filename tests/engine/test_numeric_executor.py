"""Stage 8A tests for closed restricted-AST-to-NumPy execution."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast
import re
import warnings

import numpy as np
import pytest

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    NumericExecutionCost,
    NumericExecutionResult,
    analyze_explicit_function,
    build_explicit_function_spec,
    estimate_numeric_execution_cost,
    execute_explicit_function,
)
from math_drawing_assistant.engine.numeric_executor import (
    _compile_postorder,
    _validate_operation_output,
)
from math_drawing_assistant.models import (
    BinaryOpNode,
    BinaryOperator,
    ErrorCode,
    ErrorInfo,
    ExplicitFunctionSpec,
    FunctionCallNode,
    InputSource,
    NumberNode,
    PlotItemRequest,
    PlotKind,
    SourceSpan,
    SymbolNode,
    ValidatedExplicitExpression,
)


def _spec(text: str) -> ExplicitFunctionSpec:
    validated = analyze_explicit_function(text)
    assert isinstance(validated, ValidatedExplicitExpression), validated
    request = PlotItemRequest(
        item_id="numeric-item",
        input_text=text,
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.EXPLICIT_FUNCTION,
        display_order=0,
    )
    spec = build_explicit_function_spec(request, validated)
    assert isinstance(spec, ExplicitFunctionSpec), spec
    return spec


def _execute(text: str, x: np.ndarray) -> NumericExecutionResult:
    result = execute_explicit_function(_spec(text), x)
    assert isinstance(result, NumericExecutionResult), result
    return result


def _vector_result(text: str, x: np.ndarray) -> np.ndarray:
    value = _execute(text, x).value
    assert isinstance(value, np.ndarray)
    return value


def test_constants_remain_scalars_for_a_nonempty_batch() -> None:
    x = np.array([-2.0, 0.0, 3.0], dtype=np.float64)

    assert _execute("2", x).value == 2.0
    assert _execute("pi", x).value == pytest.approx(np.pi)
    assert _execute("E", x).value == pytest.approx(np.e)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("x", [-2.0, 0.5, 3.0]),
        ("+x", [-2.0, 0.5, 3.0]),
        ("-x", [2.0, -0.5, -3.0]),
        ("x+2", [0.0, 2.5, 5.0]),
        ("x-2", [-4.0, -1.5, 1.0]),
        ("x*2", [-4.0, 1.0, 6.0]),
        ("x/2", [-1.0, 0.25, 1.5]),
        ("x^2", [4.0, 0.25, 9.0]),
    ],
)
def test_variable_unary_and_binary_nodes_execute_as_float64_vectors(
    text: str,
    expected: list[float],
) -> None:
    x = np.array([-2.0, 0.5, 3.0], dtype=np.float64)

    actual = _vector_result(text, x)

    np.testing.assert_allclose(actual, expected)
    assert actual.dtype == np.dtype(np.float64)
    assert actual.shape == x.shape


@pytest.mark.parametrize(
    ("text", "x_values", "expected"),
    [
        ("sin(x)", [0.0, np.pi / 2], [0.0, 1.0]),
        ("cos(x)", [0.0, np.pi], [1.0, -1.0]),
        ("tan(x)", [0.0, np.pi / 4], [0.0, 1.0]),
        ("sqrt(x)", [0.0, 4.0], [0.0, 2.0]),
        ("abs(x)", [-2.0, 3.0], [2.0, 3.0]),
        ("exp(x)", [0.0, 1.0], [1.0, np.e]),
        ("ln(x)", [1.0, np.e], [0.0, 1.0]),
        ("lg(x)", [1.0, 100.0], [0.0, 2.0]),
        ("log(x,2)", [1.0, 8.0], [0.0, 3.0]),
    ],
)
def test_every_approved_function_has_closed_numpy_semantics(
    text: str,
    x_values: list[float],
    expected: list[float],
) -> None:
    x = np.array(x_values, dtype=np.float64)

    np.testing.assert_allclose(_vector_result(text, x), expected, rtol=1e-12)


@pytest.mark.parametrize(
    ("text", "x_values", "expected"),
    [
        ("x^3", [-2.0, 3.0], [-8.0, 27.0]),
        ("x^-2", [-2.0, 4.0], [0.25, 0.0625]),
        ("x^2^3", [-2.0, 2.0], [256.0, 256.0]),
        ("2^x", [-1.0, 3.0], [0.5, 8.0]),
    ],
)
def test_stage_7_integer_signed_chain_and_two_to_x_power_forms(
    text: str,
    x_values: list[float],
    expected: list[float],
) -> None:
    x = np.array(x_values, dtype=np.float64)

    np.testing.assert_allclose(_vector_result(text, x), expected)


@pytest.mark.parametrize("text", ["x^x", "x^(x+1)"])
def test_stage_7_rejected_power_forms_do_not_reach_numeric_execution(text: str) -> None:
    result = analyze_explicit_function(text)

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.UNSUPPORTED_EXPONENT


@pytest.mark.parametrize(
    "invalid_x",
    [
        [1.0, 2.0],
        np.array([1.0], dtype=np.float32),
        np.array([[1.0]], dtype=np.float64),
        np.array([np.nan], dtype=np.float64),
        np.array([np.inf], dtype=np.float64),
    ],
)
def test_input_requires_an_exact_finite_one_dimensional_float64_array(
    invalid_x: object,
) -> None:
    result = execute_explicit_function(
        _spec("x"),
        cast(np.ndarray, invalid_x),
    )

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INVALID_REQUEST
    assert result.field_name == "x"
    assert result.recoverable is True


def test_empty_float64_batch_is_valid_and_keeps_strict_shape() -> None:
    x = np.array([], dtype=np.float64)

    actual = _vector_result("sin(x)", x)

    assert actual.shape == (0,)
    assert actual.dtype == np.dtype(np.float64)


def test_input_is_not_modified_and_identity_output_has_independent_ownership() -> None:
    x = np.array([-2.0, 0.0, 3.0], dtype=np.float64)
    original = x.copy()
    original_writeable = x.flags.writeable

    result = _vector_result("x", x)

    np.testing.assert_array_equal(x, original)
    assert x.flags.writeable is original_writeable
    assert not np.shares_memory(result, x)
    assert result.flags.writeable is False


def test_each_call_owns_a_fresh_result_and_does_not_cache_user_values() -> None:
    spec = _spec("x+1")
    x = np.array([1.0, 2.0], dtype=np.float64)

    first = execute_explicit_function(spec, x)
    second = execute_explicit_function(spec, x)

    assert isinstance(first, NumericExecutionResult)
    assert isinstance(second, NumericExecutionResult)
    assert isinstance(first.value, np.ndarray)
    assert isinstance(second.value, np.ndarray)
    assert first.value is not second.value
    assert not np.shares_memory(first.value, second.value)


@pytest.mark.parametrize(
    ("text", "expected_peak"),
    [
        ("2", 1),
        ("x", 2),
        ("x+x", 2),
        ("log(x,2)", 3),
        ("sin(x)+cos(x)", 4),
    ],
)
def test_peak_live_vector_metadata_follows_the_postorder_strategy(
    text: str,
    expected_peak: int,
) -> None:
    spec = _spec(text)
    estimate = estimate_numeric_execution_cost(spec)
    execution = execute_explicit_function(
        spec,
        np.array([0.5, 1.0], dtype=np.float64),
    )

    assert estimate == NumericExecutionCost(expected_peak)
    assert isinstance(execution, NumericExecutionResult)
    assert execution.cost == estimate


def test_python_scalar_zero_dimensional_and_strict_vector_outputs_are_accepted() -> None:
    python_scalar = _validate_operation_output(
        1.5,
        expect_vector=False,
        batch_length=3,
        item_id="item",
    )
    zero_dimensional = _validate_operation_output(
        np.array(2.0, dtype=np.float64),
        expect_vector=False,
        batch_length=3,
        item_id="item",
    )
    vector = _validate_operation_output(
        np.ones(3, dtype=np.float64),
        expect_vector=True,
        batch_length=3,
        item_id="item",
    )

    assert not isinstance(python_scalar, ErrorInfo)
    assert not isinstance(zero_dimensional, ErrorInfo)
    assert not isinstance(vector, ErrorInfo)
    assert type(python_scalar.value) is np.float64
    assert type(zero_dimensional.value) is np.float64
    assert isinstance(vector.value, np.ndarray)


@pytest.mark.parametrize(
    "invalid_output",
    [
        np.ones((2, 2), dtype=np.float64),
        np.ones(2, dtype=np.float64),
        np.ones(3, dtype=object),
        np.ones(3, dtype=np.complex128),
    ],
)
def test_wrong_shape_length_object_and_complex_outputs_are_structured_errors(
    invalid_output: np.ndarray,
) -> None:
    result = _validate_operation_output(
        invalid_output,
        expect_vector=True,
        batch_length=3,
        item_id="item",
    )

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INTERNAL_ERROR
    assert result.recoverable is False


def test_non_float64_zero_dimensional_output_is_rejected() -> None:
    result = _validate_operation_output(
        np.array(2, dtype=np.int64),
        expect_vector=False,
        batch_length=3,
        item_id="item",
    )

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INTERNAL_ERROR


def test_divide_domain_overflow_and_underflow_follow_locked_numpy_without_warnings() -> None:
    x_divide = np.array([-1.0, 0.0, 1.0], dtype=np.float64)
    x_domain = np.array([-1.0, 0.0, 1.0], dtype=np.float64)
    x_overflow = np.array([0.0, 1_000.0], dtype=np.float64)
    x_underflow = np.array([-1_000.0], dtype=np.float64)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        divide = _vector_result("1/x", x_divide)
        square_root = _vector_result("sqrt(x)", x_domain)
        natural_log = _vector_result("ln(x)", x_domain)
        common_log = _vector_result("lg(x)", x_domain)
        based_log = _vector_result("log(x,2)", x_domain)
        overflow = _vector_result("exp(x)", x_overflow)
        underflow = _vector_result("exp(x)", x_underflow)

    assert caught == []
    assert divide[0] == -1.0 and np.isposinf(divide[1]) and divide[2] == 1.0
    assert np.isnan(square_root[0]) and square_root[1] == 0.0
    assert np.isnan(natural_log[0]) and np.isneginf(natural_log[1])
    assert np.isnan(common_log[0]) and np.isneginf(common_log[1])
    assert np.isnan(based_log[0]) and np.isneginf(based_log[1])
    assert overflow[0] == 1.0 and np.isposinf(overflow[1])
    assert underflow[0] == 0.0 and np.isfinite(underflow[0])


def test_incompatible_limits_contract_is_an_internal_error() -> None:
    incompatible = replace(DEFAULT_LIMITS, version="limits-v2-incompatible-test")
    spec = _spec("x")
    x = np.array([1.0], dtype=np.float64)

    estimate = estimate_numeric_execution_cost(spec, limits=incompatible)
    execution = execute_explicit_function(spec, x, limits=incompatible)

    for result in (estimate, execution):
        assert isinstance(result, ErrorInfo)
        assert result.code is ErrorCode.INTERNAL_ERROR
        assert result.recoverable is False


def test_non_spec_inputs_cannot_enter_numeric_execution() -> None:
    result = execute_explicit_function(
        cast(ExplicitFunctionSpec, _spec("x").expression),
        np.array([1.0], dtype=np.float64),
    )

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INTERNAL_ERROR


def _unsafe_binary(operator: object) -> BinaryOpNode:
    span = SourceSpan(0, 1)
    number = NumberNode(span, span, "1")
    node = object.__new__(BinaryOpNode)
    object.__setattr__(node, "normalized_span", span)
    object.__setattr__(node, "source_span", span)
    object.__setattr__(node, "operator", operator)
    object.__setattr__(node, "left", number)
    object.__setattr__(node, "right", number)
    object.__setattr__(node, "implicit", False)
    return node


def _unsafe_function(name: object) -> FunctionCallNode:
    span = SourceSpan(0, 1)
    number = NumberNode(span, span, "1")
    node = object.__new__(FunctionCallNode)
    object.__setattr__(node, "normalized_span", span)
    object.__setattr__(node, "source_span", span)
    object.__setattr__(node, "name", name)
    object.__setattr__(node, "arguments", (number,))
    return node


@pytest.mark.parametrize(
    "invalid_root",
    [
        object(),
        _unsafe_binary(cast(BinaryOperator, "%")),
        _unsafe_function("unknown"),
    ],
)
def test_unknown_typed_node_operator_and_function_are_internal_contract_errors(
    invalid_root: object,
) -> None:
    result = _compile_postorder(
        invalid_root,
        item_id="item",
        max_nodes=DEFAULT_LIMITS.max_ast_nodes,
    )

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INTERNAL_ERROR
    assert result.recoverable is False


def test_tampered_validated_typed_node_is_rejected_by_public_executor() -> None:
    spec = _spec("x")
    span = spec.source_span
    object.__setattr__(
        spec.validated_expression,
        "expression",
        SymbolNode(span, span, "y"),
    )

    result = execute_explicit_function(
        spec,
        np.array([1.0], dtype=np.float64),
    )

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INTERNAL_ERROR
    assert result.recoverable is False


@pytest.mark.parametrize("kind", ["log-base", "power-form"])
def test_tampered_stage_7_semantics_are_rechecked_by_numeric_program(
    kind: str,
) -> None:
    spec = _spec("x")
    span = spec.source_span
    symbol = SymbolNode(span, span, "x")
    if kind == "log-base":
        expression = FunctionCallNode(span, span, "log", (symbol, symbol))
    else:
        expression = BinaryOpNode(
            span,
            span,
            BinaryOperator.POWER,
            symbol,
            symbol,
        )
    object.__setattr__(spec.validated_expression, "expression", expression)

    result = execute_explicit_function(
        spec,
        np.array([1.0], dtype=np.float64),
    )

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INTERNAL_ERROR
    assert result.recoverable is False


def test_formal_engine_contains_no_prohibited_execution_calls() -> None:
    engine_root = Path(__file__).parents[2] / "math_drawing_assistant" / "engine"
    forbidden = re.compile(
        r"\b(?:eval|exec|compile|ast\s*\.\s*parse|sympify|parse_expr|"
        r"parse_latex|lambdify)\s*\(",
    )

    for path in engine_root.glob("*.py"):
        assert forbidden.search(path.read_text(encoding="utf-8")) is None, path
