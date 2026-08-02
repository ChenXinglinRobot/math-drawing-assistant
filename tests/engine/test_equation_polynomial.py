"""Stage 13B-2 tests for bounded six-slot polynomial normalization."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from math_drawing_assistant.config.limits import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.equation_polynomial import (
    BoundedQuadraticPolynomial,
    EquationPolynomialError,
    PolynomialFailureKind,
    canonicalize_equation,
    canonicalize_polynomial,
    polynomial_from_equation,
    polynomial_from_restricted_expression,
)
from math_drawing_assistant.engine.exact_rational import (
    ExactLimitComponent,
    ExactRationalLimitExceeded,
)
from math_drawing_assistant.engine.normalizer import NormalizedInput, normalize_input
from math_drawing_assistant.engine.equation_splitter import (
    EquationInput,
    ExpressionInput,
    split_equation,
)
from math_drawing_assistant.engine.parser import (
    ParsedEquationInput,
    ParsedExpressionInput,
    parse_input,
)
from math_drawing_assistant.engine.tokenizer import tokenize
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo, SourceSpan
from math_drawing_assistant.models.plot_specs import PrimitiveEquationCoefficients
from math_drawing_assistant.models.restricted_ast import (
    BinaryOpNode,
    BinaryOperator,
    FunctionCallNode,
    NumberNode,
    RestrictedExpression,
    SymbolNode,
    UnaryOpNode,
    UnaryOperator,
)


_SMALL_LIMITS = replace(
    DEFAULT_LIMITS,
    max_rational_numerator_digits=2,
    max_rational_denominator_digits=2,
    max_equation_coefficient_numerator_digits=2,
    max_equation_coefficient_denominator_digits=2,
    max_equation_canonical_coefficient_digits=12,
)


class _FractionSubclass(Fraction):
    pass


class _IntSubclass(int):
    pass


class _SpanSubclass(SourceSpan):
    pass


def _parse(
    text: str,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> ParsedExpressionInput | ParsedEquationInput:
    normalized = normalize_input(text, limits=limits)
    assert isinstance(normalized, NormalizedInput), normalized
    tokens = tokenize(normalized, limits=limits)
    assert isinstance(tokens, tuple), tokens
    split = split_equation(tokens)
    assert isinstance(split, (ExpressionInput, EquationInput)), split
    parsed = parse_input(split, limits=limits)
    assert isinstance(parsed, (ParsedExpressionInput, ParsedEquationInput)), parsed
    return parsed


def _expression(
    text: str,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> RestrictedExpression:
    parsed = _parse(text, limits=limits)
    assert isinstance(parsed, ParsedExpressionInput)
    return parsed.expression


def _equation(
    text: str,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> tuple[RestrictedExpression, RestrictedExpression]:
    parsed = _parse(text, limits=limits)
    assert isinstance(parsed, ParsedEquationInput)
    return parsed.left, parsed.right


def _polynomial(
    text: str,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> BoundedQuadraticPolynomial:
    return polynomial_from_restricted_expression(
        _expression(text, limits=limits),
        limits=limits,
    )


def _canonical(
    text: str,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> PrimitiveEquationCoefficients:
    left, right = _equation(text, limits=limits)
    return canonicalize_equation(left, right, limits=limits)


def _slots(polynomial: BoundedQuadraticPolynomial) -> tuple[Fraction, ...]:
    return (
        polynomial.constant,
        polynomial.x,
        polynomial.y,
        polynomial.x_squared,
        polynomial.x_y,
        polynomial.y_squared,
    )


def _failure(
    text: str,
    kind: PolynomialFailureKind,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> EquationPolynomialError:
    with pytest.raises(EquationPolynomialError) as exception:
        polynomial_from_restricted_expression(
            _expression(text, limits=limits),
            limits=limits,
        )
    assert exception.value.kind is kind
    return exception.value


def _direct_power(
    exponent: RestrictedExpression,
) -> BinaryOpNode:
    x = SymbolNode(SourceSpan(0, 1), SourceSpan(0, 1), "x")
    return BinaryOpNode(
        SourceSpan(0, exponent.normalized_span.end),
        SourceSpan(0, exponent.source_span.end),
        BinaryOperator.POWER,
        x,
        exponent,
    )


def test_failure_kind_values_match_the_stable_error_registry() -> None:
    expected = {
        PolynomialFailureKind.NON_RATIONAL_COEFFICIENT: (
            ErrorCode.EQUATION_NON_RATIONAL_COEFFICIENT
        ),
        PolynomialFailureKind.NON_POLYNOMIAL: ErrorCode.EQUATION_NON_POLYNOMIAL,
        PolynomialFailureKind.VARIABLE_DENOMINATOR: (
            ErrorCode.EQUATION_VARIABLE_DENOMINATOR
        ),
        PolynomialFailureKind.ZERO_DENOMINATOR: ErrorCode.EQUATION_ZERO_DENOMINATOR,
        PolynomialFailureKind.DEGREE_EXCEEDED: ErrorCode.EQUATION_DEGREE_EXCEEDED,
        PolynomialFailureKind.UNSUPPORTED_EQUATION: ErrorCode.UNSUPPORTED_EQUATION,
        PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED: (
            ErrorCode.RESOURCE_LIMIT_EXCEEDED
        ),
    }
    assert len(PolynomialFailureKind) == 7
    assert all(kind.value == code.value for kind, code in expected.items())


def test_equation_error_has_exactly_five_business_fields_and_safe_messages() -> None:
    normalized_span = SourceSpan(2, 4)
    source_span = SourceSpan(7, 11)
    semantic = EquationPolynomialError(
        PolynomialFailureKind.NON_POLYNOMIAL,
        normalized_span,
        source_span,
    )
    resource = EquationPolynomialError(
        PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED,
        normalized_span,
        source_span,
        ExactLimitComponent.COEFFICIENT_DENOMINATOR,
        17,
    )

    assert isinstance(semantic, ValueError)
    assert EquationPolynomialError.__slots__ == (
        "kind",
        "normalized_span",
        "source_span",
        "exact_limit_component",
        "exact_limit",
    )
    assert semantic.kind is PolynomialFailureKind.NON_POLYNOMIAL
    assert semantic.normalized_span is normalized_span
    assert semantic.source_span is source_span
    assert semantic.exact_limit_component is None
    assert semantic.exact_limit is None
    assert semantic.__dict__ == {}
    assert "equation_non_polynomial" in str(semantic)
    assert resource.exact_limit_component is ExactLimitComponent.COEFFICIENT_DENOMINATOR
    assert resource.exact_limit == 17
    assert "coefficient denominator" in str(resource)
    assert "limit=17" in str(resource)
    for forbidden in ("payload", "expression", "ast", "lexeme", "exception"):
        assert not hasattr(resource, forbidden)


@pytest.mark.parametrize(
    "component",
    list(ExactLimitComponent),
)
def test_resource_error_preserves_each_distinct_typed_component(
    component: ExactLimitComponent,
) -> None:
    error = EquationPolynomialError(
        PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED,
        SourceSpan(0, 1),
        SourceSpan(2, 3),
        component,
        9,
    )
    assert error.exact_limit_component is component
    assert component.value in str(error)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"exact_limit_component": ExactLimitComponent.CANONICAL_INTEGER},
        {"exact_limit": 1},
        {
            "exact_limit_component": ExactLimitComponent.CANONICAL_INTEGER,
            "exact_limit": True,
        },
        {
            "exact_limit_component": ExactLimitComponent.CANONICAL_INTEGER,
            "exact_limit": 1.0,
        },
        {
            "exact_limit_component": "canonical integer",
            "exact_limit": 1,
        },
    ],
)
def test_resource_error_rejects_incomplete_or_wrong_typed_metadata(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(TypeError):
        EquationPolynomialError(
            PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED,
            SourceSpan(0, 1),
            SourceSpan(0, 1),
            **kwargs,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("limit", [0, -1])
def test_resource_error_rejects_nonpositive_limits(limit: int) -> None:
    with pytest.raises(ValueError):
        EquationPolynomialError(
            PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED,
            SourceSpan(0, 1),
            SourceSpan(0, 1),
            ExactLimitComponent.CANONICAL_INTEGER,
            limit,
        )


@pytest.mark.parametrize(
    "kind",
    [kind for kind in PolynomialFailureKind if kind is not PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED],
)
def test_every_non_resource_error_rejects_and_never_carries_limit_metadata(
    kind: PolynomialFailureKind,
) -> None:
    error = EquationPolynomialError(kind, SourceSpan(0, 1), SourceSpan(0, 1))
    assert error.exact_limit_component is None
    assert error.exact_limit is None
    with pytest.raises(ValueError):
        EquationPolynomialError(
            kind,
            SourceSpan(0, 1),
            SourceSpan(0, 1),
            ExactLimitComponent.CANONICAL_INTEGER,
            1,
        )


def test_equation_error_requires_exact_enum_and_spans() -> None:
    span = SourceSpan(0, 1)
    with pytest.raises(TypeError):
        EquationPolynomialError("equation_non_polynomial", span, span)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        EquationPolynomialError(
            PolynomialFailureKind.NON_POLYNOMIAL,
            _SpanSubclass(0, 1),
            span,
        )


def test_bounded_polynomial_is_frozen_slotted_hashable_and_keeps_field_order() -> None:
    polynomial = BoundedQuadraticPolynomial(
        Fraction(1),
        Fraction(2),
        Fraction(3),
        Fraction(4),
        Fraction(5),
        Fraction(6),
        2,
        True,
    )
    assert [field.name for field in fields(polynomial)] == [
        "constant",
        "x",
        "y",
        "x_squared",
        "x_y",
        "y_squared",
        "structural_degree",
        "contains_variable",
    ]
    assert not hasattr(polynomial, "__dict__")
    assert hash(polynomial)
    with pytest.raises(FrozenInstanceError):
        polynomial.x = Fraction(0)  # type: ignore[misc]


@pytest.mark.parametrize(
    "bad",
    [1, True, 1.0, Decimal("1"), _FractionSubclass(1, 2)],
)
def test_bounded_polynomial_requires_six_exact_fractions(bad: object) -> None:
    values: list[object] = [Fraction(0)] * 6
    values[3] = bad
    with pytest.raises(TypeError, match="exact Fraction"):
        BoundedQuadraticPolynomial(*values, 2, True)  # type: ignore[arg-type]


@pytest.mark.parametrize("degree", [True, 1.0, _IntSubclass(1)])
def test_bounded_polynomial_requires_exact_structural_degree(degree: object) -> None:
    with pytest.raises(TypeError):
        BoundedQuadraticPolynomial(
            Fraction(0), Fraction(0), Fraction(0),
            Fraction(0), Fraction(0), Fraction(0),
            degree, True,  # type: ignore[arg-type]
        )


def test_bounded_polynomial_enforces_degree_metadata_without_lowering_it() -> None:
    zero = Fraction(0)
    with pytest.raises(ValueError):
        BoundedQuadraticPolynomial(zero, zero, zero, zero, zero, zero, 0, True)
    with pytest.raises(ValueError):
        BoundedQuadraticPolynomial(zero, zero, zero, zero, zero, zero, 1, False)
    with pytest.raises(ValueError):
        BoundedQuadraticPolynomial(zero, zero, zero, Fraction(1), zero, zero, 1, True)
    with pytest.raises(ValueError):
        BoundedQuadraticPolynomial(zero, zero, zero, zero, zero, zero, 2, False)

    linear_cancel = _polynomial("x-x")
    quadratic_cancel = _polynomial("x^2-x^2")
    assert _slots(linear_cancel) == (zero,) * 6
    assert linear_cancel.structural_degree == 1
    assert linear_cancel.contains_variable is True
    assert _slots(quadratic_cancel) == (zero,) * 6
    assert quadratic_cancel.structural_degree == 2
    assert quadratic_cancel.contains_variable is True


def test_direct_polynomial_construction_retains_the_typed_exact_exception() -> None:
    with pytest.raises(ExactRationalLimitExceeded) as exception:
        BoundedQuadraticPolynomial(
            Fraction(100),
            Fraction(0),
            Fraction(0),
            Fraction(0),
            Fraction(0),
            Fraction(0),
            0,
            False,
            limits=_SMALL_LIMITS,
        )
    assert exception.value.component is ExactLimitComponent.COEFFICIENT_NUMERATOR
    assert exception.value.limit == 2


@pytest.mark.parametrize(
    ("text", "expected", "degree"),
    [
        ("2", (2, 0, 0, 0, 0, 0), 0),
        ("x", (0, 1, 0, 0, 0, 0), 1),
        ("y", (0, 0, 1, 0, 0, 0), 1),
        ("-x", (0, -1, 0, 0, 0, 0), 1),
        ("+x", (0, 1, 0, 0, 0, 0), 1),
        ("x+y", (0, 1, 1, 0, 0, 0), 1),
        ("x-y", (0, 1, -1, 0, 0, 0), 1),
        ("2*x", (0, 2, 0, 0, 0, 0), 1),
        ("x/2", (0, Fraction(1, 2), 0, 0, 0, 0), 1),
        ("x^2", (0, 0, 0, 1, 0, 0), 2),
        ("x*y", (0, 0, 0, 0, 1, 0), 2),
        ("y^2", (0, 0, 0, 0, 0, 1), 2),
        ("(x+y)^2", (0, 0, 0, 1, 2, 1), 2),
    ],
)
def test_basic_six_slot_normalization(
    text: str,
    expected: tuple[int | Fraction, ...],
    degree: int,
) -> None:
    polynomial = _polynomial(text)
    assert _slots(polynomial) == tuple(Fraction(value) for value in expected)
    assert polynomial.structural_degree == degree
    assert polynomial.contains_variable is (degree != 0)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2*(x+1)=3*(y-2)", (0, 0, 0, 2, -3, 8)),
        ("(x-1)^2+(y+2)^2=9", (1, 0, 1, -2, 4, -4)),
        ("(x+y)^2+(x-y)^2=4", (1, 0, 1, 0, 0, -2)),
        ("0.5*x+0.25*y=1", (0, 0, 0, 2, 1, -4)),
        ("x/2+y/3=1", (0, 0, 0, 3, 2, -6)),
    ],
)
def test_equation_normalization_and_canonicalization(
    text: str,
    expected: tuple[int, ...],
) -> None:
    coefficients = _canonical(text)
    assert tuple(getattr(coefficients, name) for name in "abcdef") == expected


@pytest.mark.parametrize(
    "text",
    [
        "x^3-x^3+x^2+y^2=1",
        "x^2*y-x^2*y+x=0",
        "(x-x)*x^2=0",
        "(x^2-x^2)*y=0",
    ],
)
def test_high_degree_structure_is_rejected_before_cancellation(text: str) -> None:
    left, right = _equation(text)
    with pytest.raises(EquationPolynomialError) as exception:
        canonicalize_equation(left, right)
    assert exception.value.kind is PolynomialFailureKind.DEGREE_EXCEEDED


def test_structurally_quadratic_cancellation_can_normalize_then_fail_if_constant() -> None:
    assert tuple(getattr(_canonical("x^2-x^2+x=0"), name) for name in "abcdef") == (
        0, 0, 0, 1, 0, 0,
    )
    left, right = _equation("(x-x)^2=0")
    with pytest.raises(EquationPolynomialError) as exception:
        canonicalize_equation(left, right)
    assert exception.value.kind is PolynomialFailureKind.UNSUPPORTED_EQUATION


@pytest.mark.parametrize("text", ["x/2", "(x+y)/2.5", "(x^2+y^2)/3"])
def test_constant_denominators_are_accepted(text: str) -> None:
    assert isinstance(_polynomial(text), BoundedQuadraticPolynomial)


@pytest.mark.parametrize(
    "text",
    ["x/y", "x/(y-y+1)", "x/(x-x+2)", "(x^2-1)/(x-1)"],
)
def test_variable_denominators_are_rejected_without_cancellation(text: str) -> None:
    _failure(text, PolynomialFailureKind.VARIABLE_DENOMINATOR)


@pytest.mark.parametrize("text", ["x/(2-2)", "1/(0.0)"])
def test_exact_zero_denominator_uses_the_denominator_span(text: str) -> None:
    root = _expression(text)
    assert isinstance(root, BinaryOpNode)
    error = _failure(text, PolynomialFailureKind.ZERO_DENOMINATOR)
    assert error.normalized_span == root.right.normalized_span
    assert error.source_span == root.right.source_span


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("1/(x^3)", PolynomialFailureKind.DEGREE_EXCEEDED),
        ("1/sin(x)", PolynomialFailureKind.NON_POLYNOMIAL),
        ("1/(x/0)", PolynomialFailureKind.ZERO_DENOMINATOR),
        ("x/(y-y+1)", PolynomialFailureKind.VARIABLE_DENOMINATOR),
    ],
)
def test_child_errors_are_immediately_propagated_by_parent_division(
    text: str,
    kind: PolynomialFailureKind,
) -> None:
    _failure(text, kind)


@pytest.mark.parametrize(
    "text",
    ["pi*x", "E", "sqrt(2)", "sin(1)", "abs(-2)", "sin(1/0)", "sqrt(2^3)"],
)
def test_non_rational_nodes_and_constant_function_arguments_use_real_parser(
    text: str,
) -> None:
    _failure(text, PolynomialFailureKind.NON_RATIONAL_COEFFICIENT)


@pytest.mark.parametrize("text", ["sin(x)", "sqrt(x+1)", "abs(x)", "sin(x/0)"])
def test_function_arguments_with_variables_are_terminal_non_polynomial_rejections(
    text: str,
) -> None:
    _failure(text, PolynomialFailureKind.NON_POLYNOMIAL)


def test_function_nodes_do_not_evaluate_zero_division_power_or_fraction_arithmetic() -> None:
    assert _failure("sin(1/0)", PolynomialFailureKind.NON_RATIONAL_COEFFICIENT)
    assert _failure("sin(x/0)", PolynomialFailureKind.NON_POLYNOMIAL)
    assert _failure("sqrt(2^3)", PolynomialFailureKind.NON_RATIONAL_COEFFICIENT)


@pytest.mark.parametrize("text", ["x^1", "x^2", "(x+1)^2", "(x-y)^2", "x^+2"])
def test_allowed_direct_signed_exponents_follow_real_parser_contract(text: str) -> None:
    assert isinstance(_polynomial(text), BoundedQuadraticPolynomial)


@pytest.mark.parametrize("text", ["x^0", "x^-0", "(x+1)^0", "(x-y)^0"])
def test_variable_zero_powers_are_unsupported(text: str) -> None:
    _failure(text, PolynomialFailureKind.UNSUPPORTED_EQUATION)


def test_negative_decimal_zero_is_classified_by_exact_value_on_a_legal_direct_node() -> None:
    literal = NumberNode(SourceSpan(3, 6), SourceSpan(3, 6), "0.0")
    exponent = UnaryOpNode(
        SourceSpan(2, 6),
        SourceSpan(2, 6),
        UnaryOperator.NEGATIVE,
        literal,
    )
    with pytest.raises(EquationPolynomialError) as exception:
        polynomial_from_restricted_expression(_direct_power(exponent))
    assert exception.value.kind is PolynomialFailureKind.UNSUPPORTED_EQUATION


@pytest.mark.parametrize("text", ["x^-1", "x^-2"])
def test_negative_integer_variable_powers_are_variable_denominators(text: str) -> None:
    _failure(text, PolynomialFailureKind.VARIABLE_DENOMINATOR)


@pytest.mark.parametrize("text", ["x^3", "(x+1)^3"])
def test_large_integer_variable_powers_exceed_degree(text: str) -> None:
    _failure(text, PolynomialFailureKind.DEGREE_EXCEEDED)


def test_direct_fractional_exponent_is_non_polynomial_without_parser_changes() -> None:
    exponent = NumberNode(SourceSpan(2, 5), SourceSpan(2, 5), "0.5")
    with pytest.raises(EquationPolynomialError) as exception:
        polynomial_from_restricted_expression(_direct_power(exponent))
    assert exception.value.kind is PolynomialFailureKind.NON_POLYNOMIAL


@pytest.mark.parametrize("text", ["x^(1+1)", "x^y", "x^pi"])
def test_non_direct_exponent_nodes_are_non_polynomial(text: str) -> None:
    _failure(text, PolynomialFailureKind.NON_POLYNOMIAL)


@pytest.mark.parametrize("text", ["2^3", "(1/2)^2", "3^0"])
def test_pure_numeric_powers_are_not_coefficient_arithmetic(text: str) -> None:
    _failure(text, PolynomialFailureKind.UNSUPPORTED_EQUATION)


@pytest.mark.parametrize(
    "text",
    ["0=0", "1=0", "1=1", "x=x", "x-x=0", "x-x=1", "x^2-x^2=0"],
)
def test_zero_and_constant_equations_are_unsupported(text: str) -> None:
    left, right = _equation(text)
    with pytest.raises(EquationPolynomialError) as exception:
        canonicalize_equation(left, right)
    assert exception.value.kind is PolynomialFailureKind.UNSUPPORTED_EQUATION
    assert exception.value.normalized_span == SourceSpan(
        min(left.normalized_span.start, right.normalized_span.start),
        max(left.normalized_span.end, right.normalized_span.end),
    )


@pytest.mark.parametrize(
    "text",
    [
        "-2*x+2*y-4=0",
        "2*x-2*y+4=0",
        "x-y+2=0",
        "0=-x+y-2",
        "(x-y+2)/3=0",
    ],
)
def test_integer_rational_and_side_swapped_equations_share_one_canonical_value(
    text: str,
) -> None:
    assert _canonical(text) == PrimitiveEquationCoefficients(0, 0, 0, 1, -1, 2)


def test_canonicalize_polynomial_uses_explicit_caller_spans() -> None:
    polynomial = _polynomial("x-x")
    normalized_span = SourceSpan(10, 20)
    source_span = SourceSpan(30, 50)
    with pytest.raises(EquationPolynomialError) as exception:
        canonicalize_polynomial(
            polynomial,
            normalized_span=normalized_span,
            source_span=source_span,
        )
    assert exception.value.normalized_span is normalized_span
    assert exception.value.source_span is source_span


@pytest.mark.parametrize(
    ("text", "component"),
    [
        ("99+1", ExactLimitComponent.COEFFICIENT_NUMERATOR),
        ("1/97-1/89", ExactLimitComponent.COEFFICIENT_DENOMINATOR),
        ("99*x*2", ExactLimitComponent.COEFFICIENT_NUMERATOR),
    ],
)
def test_ast_arithmetic_preserves_resource_component_limit_span_and_safe_message(
    text: str,
    component: ExactLimitComponent,
) -> None:
    root = _expression(text, limits=_SMALL_LIMITS)
    with pytest.raises(EquationPolynomialError) as exception:
        polynomial_from_restricted_expression(root, limits=_SMALL_LIMITS)
    error = exception.value
    assert error.kind is PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED
    assert error.exact_limit_component is component
    assert error.exact_limit == 2
    assert error.normalized_span == root.normalized_span
    assert error.source_span == root.source_span
    assert text not in str(error)
    assert "99" not in str(error)
    assert error.__cause__ is None
    assert error.__suppress_context__ is True


def test_lhs_rhs_checked_subtraction_resource_error_uses_the_full_equation_span() -> None:
    left, right = _equation("99=-1", limits=_SMALL_LIMITS)
    with pytest.raises(EquationPolynomialError) as exception:
        polynomial_from_equation(left, right, limits=_SMALL_LIMITS)
    error = exception.value
    assert error.kind is PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED
    assert error.exact_limit_component is ExactLimitComponent.COEFFICIENT_NUMERATOR
    assert error.exact_limit == 2
    assert error.normalized_span == SourceSpan(0, 5)
    assert error.source_span == SourceSpan(0, 5)


def test_active_limit_revalidation_preserves_original_typed_metadata() -> None:
    wide_limits = replace(
        DEFAULT_LIMITS,
        max_equation_coefficient_numerator_digits=129,
        max_equation_canonical_coefficient_digits=769,
    )
    polynomial = BoundedQuadraticPolynomial(
        Fraction(0),
        Fraction(10**128),
        Fraction(0),
        Fraction(0),
        Fraction(0),
        Fraction(0),
        1,
        True,
        limits=wide_limits,
    )
    with pytest.raises(EquationPolynomialError) as exception:
        canonicalize_polynomial(
            polynomial,
            normalized_span=SourceSpan(1, 2),
            source_span=SourceSpan(3, 4),
        )
    assert exception.value.exact_limit_component is ExactLimitComponent.COEFFICIENT_NUMERATOR
    assert exception.value.exact_limit == 128


def test_non_public_canonical_helper_failure_mapping_preserves_metadata_and_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This branch test is intentionally not a public-input-reachable case."""

    import math_drawing_assistant.engine.equation_polynomial as module

    limit = DEFAULT_LIMITS.max_equation_canonical_coefficient_digits

    def fail_lcm(
        left: int,
        right: int,
        *,
        limits: ApplicationLimits = DEFAULT_LIMITS,
    ) -> int:
        del left, right, limits
        raise ExactRationalLimitExceeded(
            ExactLimitComponent.CANONICAL_INTEGER,
            limit,
        )

    monkeypatch.setattr(module, "checked_positive_lcm", fail_lcm)
    normalized_span = SourceSpan(10, 20)
    source_span = SourceSpan(30, 40)
    with pytest.raises(EquationPolynomialError) as exception:
        canonicalize_polynomial(
            _polynomial("x"),
            normalized_span=normalized_span,
            source_span=source_span,
        )
    error = exception.value
    assert error.kind is PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED
    assert error.exact_limit_component is ExactLimitComponent.CANONICAL_INTEGER
    assert error.exact_limit == limit
    assert error.normalized_span is normalized_span
    assert error.source_span is source_span
    assert "canonical integer" in str(error)
    assert str(10**100) not in str(error)


def test_legal_ndk_relationship_proves_public_lcm_and_scaling_boundaries() -> None:
    limits = DEFAULT_LIMITS
    numerator_digits = limits.max_equation_coefficient_numerator_digits
    denominator_digits = limits.max_equation_coefficient_denominator_digits
    canonical_digits = limits.max_equation_canonical_coefficient_digits
    assert canonical_digits >= 6 * denominator_digits
    assert canonical_digits >= numerator_digits + 5 * denominator_digits

    polynomial = BoundedQuadraticPolynomial(
        Fraction(1, 2),
        Fraction(1, 3),
        Fraction(1, 5),
        Fraction(1, 7),
        Fraction(1, 11),
        Fraction(1, 13),
        2,
        True,
    )
    result = canonicalize_polynomial(
        polynomial,
        normalized_span=SourceSpan(0, 1),
        source_span=SourceSpan(0, 1),
    )
    assert isinstance(result, PrimitiveEquationCoefficients)


def test_production_module_has_only_approved_dependencies_and_fixed_helpers() -> None:
    path = (
        Path(__file__).parents[2]
        / "math_drawing_assistant"
        / "engine"
        / "equation_polynomial.py"
    )
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)

    assert imports <= {
        "__future__",
        "dataclasses",
        "enum",
        "fractions",
        "math",
        "math_drawing_assistant.config.limits",
        "math_drawing_assistant.engine.exact_rational",
        "math_drawing_assistant.models.errors",
        "math_drawing_assistant.models.plot_specs",
        "math_drawing_assistant.models.restricted_ast",
    }
    assert {
        "checked_negate",
        "checked_add",
        "checked_subtract",
        "checked_multiply",
        "checked_divide",
        "checked_positive_lcm",
        "checked_scale_fraction_to_integer",
        "ensure_canonical_integer_within_limit",
    } <= calls
    assert calls.isdisjoint(
        {
            "eval", "exec", "float", "Decimal", "sympify", "parse_expr",
            "expand", "factor", "simplify", "solve",
        },
    )
    for forbidden in (
        "ErrorInfo",
        "LineSpec",
        "CircleSpec",
        "EllipseSpec",
        "HyperbolaSpec",
        "ParabolaSpec",
        "PlotKind",
        "RenderPlan",
        "viewport",
        "sampler",
        "renderer",
        "PySide6",
        "numpy",
        "matplotlib",
        "sympy",
    ):
        assert forbidden not in source


def test_static_structure_has_no_arbitrary_monomial_map_or_second_tree_prescan() -> None:
    path = (
        Path(__file__).parents[2]
        / "math_drawing_assistant"
        / "engine"
        / "equation_polynomial.py"
    )
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "monomial" not in source.lower()
    assert not any(isinstance(node, (ast.Dict, ast.DictComp)) for node in ast.walk(tree))
    assert "parser" not in source
    assert "tokenizer" not in source
    assert "_contains_variable(node.left)" not in source
    assert "_contains_variable(node.right)" not in source
    assert source.count("left = _visit(node.left, limits=limits)") == 1
    assert source.count("right = _visit(node.right, limits=limits)") == 1
