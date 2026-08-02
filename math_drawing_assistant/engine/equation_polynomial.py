"""Bounded six-slot polynomial normalization for stage 13B-2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from math import gcd

from math_drawing_assistant.config.limits import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.exact_rational import (
    ExactLimitComponent,
    ExactRationalLimitExceeded,
    ExactRationalZeroDivision,
    checked_add,
    checked_divide,
    checked_multiply,
    checked_negate,
    checked_positive_lcm,
    checked_scale_fraction_to_integer,
    checked_subtract,
    ensure_canonical_integer_within_limit,
    ensure_fraction_within_limits,
    fraction_from_number_lexeme,
)
from math_drawing_assistant.models.errors import SourceSpan
from math_drawing_assistant.models.plot_specs import PrimitiveEquationCoefficients
from math_drawing_assistant.models.restricted_ast import (
    BinaryOpNode,
    BinaryOperator,
    ConstantNode,
    FunctionCallNode,
    NumberNode,
    RestrictedExpression,
    SymbolNode,
    UnaryOpNode,
    UnaryOperator,
)


_ZERO = Fraction(0, 1)
_ONE = Fraction(1, 1)


class PolynomialFailureKind(str, Enum):
    """Closed normalization failures mapped by later equation stages."""

    NON_RATIONAL_COEFFICIENT = "equation_non_rational_coefficient"
    NON_POLYNOMIAL = "equation_non_polynomial"
    VARIABLE_DENOMINATOR = "equation_variable_denominator"
    ZERO_DENOMINATOR = "equation_zero_denominator"
    DEGREE_EXCEEDED = "equation_degree_exceeded"
    UNSUPPORTED_EQUATION = "unsupported_equation"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"


class EquationPolynomialError(ValueError):
    """A small, span-aware, operand-free polynomial normalization failure."""

    __slots__ = (
        "kind",
        "normalized_span",
        "source_span",
        "exact_limit_component",
        "exact_limit",
    )

    kind: PolynomialFailureKind
    normalized_span: SourceSpan
    source_span: SourceSpan
    exact_limit_component: ExactLimitComponent | None
    exact_limit: int | None

    def __init__(
        self,
        kind: PolynomialFailureKind,
        normalized_span: SourceSpan,
        source_span: SourceSpan,
        exact_limit_component: ExactLimitComponent | None = None,
        exact_limit: int | None = None,
    ) -> None:
        if type(kind) is not PolynomialFailureKind:
            raise TypeError("kind must be an exact PolynomialFailureKind")
        if type(normalized_span) is not SourceSpan:
            raise TypeError("normalized_span must be an exact SourceSpan")
        if type(source_span) is not SourceSpan:
            raise TypeError("source_span must be an exact SourceSpan")

        if kind is PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED:
            if type(exact_limit_component) is not ExactLimitComponent:
                raise TypeError(
                    "resource failures require an exact ExactLimitComponent",
                )
            if type(exact_limit) is not int:
                raise TypeError("resource failures require a positive exact int limit")
            if exact_limit <= 0:
                raise ValueError("resource failure limit must be positive")
            message = (
                "equation polynomial normalization failed "
                f"(resource_limit_exceeded: {exact_limit_component.value}, "
                f"limit={exact_limit})"
            )
        else:
            if exact_limit_component is not None or exact_limit is not None:
                raise ValueError(
                    "non-resource failures must not carry exact limit metadata",
                )
            message = f"equation polynomial normalization failed ({kind.value})"

        self.kind = kind
        self.normalized_span = normalized_span
        self.source_span = source_span
        self.exact_limit_component = exact_limit_component
        self.exact_limit = exact_limit
        super().__init__(message)


@dataclass(frozen=True, slots=True, init=False)
class BoundedQuadraticPolynomial:
    """A bounded polynomial in the fixed basis 1, x, y, x2, xy, y2."""

    constant: Fraction
    x: Fraction
    y: Fraction
    x_squared: Fraction
    x_y: Fraction
    y_squared: Fraction
    structural_degree: int
    contains_variable: bool

    def __init__(
        self,
        constant: Fraction,
        x: Fraction,
        y: Fraction,
        x_squared: Fraction,
        x_y: Fraction,
        y_squared: Fraction,
        structural_degree: int,
        contains_variable: bool,
        *,
        limits: ApplicationLimits = DEFAULT_LIMITS,
    ) -> None:
        _require_limits(limits)
        coefficients = (constant, x, y, x_squared, x_y, y_squared)
        names = ("constant", "x", "y", "x_squared", "x_y", "y_squared")
        for name, coefficient in zip(names, coefficients, strict=True):
            if type(coefficient) is not Fraction:
                raise TypeError(f"{name} must be an exact Fraction")
            ensure_fraction_within_limits(coefficient, limits=limits)
        if type(structural_degree) is not int:
            raise TypeError("structural_degree must be an exact int")
        if structural_degree not in {0, 1, 2}:
            raise ValueError("structural_degree must be 0, 1, or 2")
        if type(contains_variable) is not bool:
            raise TypeError("contains_variable must be an exact bool")

        if structural_degree == 0:
            if contains_variable:
                raise ValueError("degree-zero polynomials cannot contain variables")
            if any(coefficient != _ZERO for coefficient in coefficients[1:]):
                raise ValueError("degree-zero polynomials require zero variable slots")
        elif structural_degree == 1:
            if not contains_variable:
                raise ValueError("degree-one polynomials must contain a variable")
            if any(coefficient != _ZERO for coefficient in coefficients[3:]):
                raise ValueError("degree-one polynomials require zero quadratic slots")
        elif not contains_variable:
            raise ValueError("degree-two polynomials must contain a variable")

        object.__setattr__(self, "constant", constant)
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "x_squared", x_squared)
        object.__setattr__(self, "x_y", x_y)
        object.__setattr__(self, "y_squared", y_squared)
        object.__setattr__(self, "structural_degree", structural_degree)
        object.__setattr__(self, "contains_variable", contains_variable)


def polynomial_from_restricted_expression(
    expression: RestrictedExpression,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> BoundedQuadraticPolynomial:
    """Normalize one closed RestrictedExpression in one deterministic visit."""

    _require_expression(expression)
    _require_limits(limits)
    return _visit(expression, limits=limits)


def polynomial_from_equation(
    left: RestrictedExpression,
    right: RestrictedExpression,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> BoundedQuadraticPolynomial:
    """Normalize an equation as the bounded polynomial ``left - right``."""

    _require_expression(left)
    _require_expression(right)
    _require_limits(limits)
    normalized_span, source_span = _equation_spans(left, right)

    left_polynomial = _visit(left, limits=limits)
    right_polynomial = _visit(right, limits=limits)
    try:
        return _subtract_polynomials(
            left_polynomial,
            right_polynomial,
            limits=limits,
        )
    except ExactRationalLimitExceeded as exc:
        mapped_error = EquationPolynomialError(
            PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED,
            normalized_span,
            source_span,
            exc.component,
            exc.limit,
        )
        raise mapped_error from None
    except ExactRationalZeroDivision:
        mapped_error = EquationPolynomialError(
            PolynomialFailureKind.ZERO_DENOMINATOR,
            normalized_span,
            source_span,
        )
        raise mapped_error from None


def canonicalize_polynomial(
    polynomial: BoundedQuadraticPolynomial,
    *,
    normalized_span: SourceSpan,
    source_span: SourceSpan,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> PrimitiveEquationCoefficients:
    """Return primitive sign-normalized coefficients in A,B,C,D,E,F order."""

    if type(polynomial) is not BoundedQuadraticPolynomial:
        raise TypeError("polynomial must be an exact BoundedQuadraticPolynomial")
    _require_span(normalized_span, "normalized_span")
    _require_span(source_span, "source_span")
    _require_limits(limits)

    try:
        coefficients = _validated_coefficients(polynomial, limits=limits)
        if all(coefficient == _ZERO for coefficient in coefficients[1:]):
            raise EquationPolynomialError(
                PolynomialFailureKind.UNSUPPORTED_EQUATION,
                normalized_span,
                source_span,
            )

        common_denominator = 1
        for coefficient in coefficients:
            common_denominator = checked_positive_lcm(
                common_denominator,
                coefficient.denominator,
                limits=limits,
            )

        scaled = tuple(
            ensure_canonical_integer_within_limit(
                checked_scale_fraction_to_integer(
                    coefficient,
                    common_denominator,
                    limits=limits,
                ),
                limits=limits,
            )
            for coefficient in coefficients
        )
        common_divisor = 0
        for value in scaled:
            if value != 0:
                common_divisor = gcd(common_divisor, abs(value))
        if common_divisor <= 0:
            raise RuntimeError("variable coefficients unexpectedly vanished")

        primitive = tuple(
            ensure_canonical_integer_within_limit(
                value // common_divisor,
                limits=limits,
            )
            for value in scaled
        )
        constant, x, y, x_squared, x_y, y_squared = primitive
        model_order = (x_squared, x_y, y_squared, x, y, constant)
        first_nonzero = next(value for value in model_order if value != 0)
        if first_nonzero < 0:
            model_order = tuple(
                ensure_canonical_integer_within_limit(-value, limits=limits)
                for value in model_order
            )
    except ExactRationalLimitExceeded as exc:
        mapped_error = EquationPolynomialError(
            PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED,
            normalized_span,
            source_span,
            exc.component,
            exc.limit,
        )
        raise mapped_error from None
    except ExactRationalZeroDivision:
        mapped_error = EquationPolynomialError(
            PolynomialFailureKind.ZERO_DENOMINATOR,
            normalized_span,
            source_span,
        )
        raise mapped_error from None

    return PrimitiveEquationCoefficients(*model_order)


def canonicalize_equation(
    left: RestrictedExpression,
    right: RestrictedExpression,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> PrimitiveEquationCoefficients:
    """Normalize and canonicalize one equation using its full equation spans."""

    _require_expression(left)
    _require_expression(right)
    _require_limits(limits)
    normalized_span, source_span = _equation_spans(left, right)
    polynomial = polynomial_from_equation(left, right, limits=limits)
    return canonicalize_polynomial(
        polynomial,
        normalized_span=normalized_span,
        source_span=source_span,
        limits=limits,
    )


def _visit(
    expression: RestrictedExpression,
    *,
    limits: ApplicationLimits,
) -> BoundedQuadraticPolynomial:
    _require_expression(expression)
    try:
        node_type = type(expression)
        if node_type is NumberNode:
            node = expression
            return _polynomial(
                fraction_from_number_lexeme(node.lexeme, limits=limits),
                limits=limits,
            )
        if node_type is SymbolNode:
            node = expression
            if node.name == "x":
                return _polynomial(_ZERO, x=_ONE, degree=1, limits=limits)
            if node.name == "y":
                return _polynomial(_ZERO, y=_ONE, degree=1, limits=limits)
            raise TypeError("unknown closed variable")
        if node_type is ConstantNode:
            raise EquationPolynomialError(
                PolynomialFailureKind.NON_RATIONAL_COEFFICIENT,
                expression.normalized_span,
                expression.source_span,
            )
        if node_type is UnaryOpNode:
            node = expression
            operand = _visit(node.operand, limits=limits)
            if node.operator is UnaryOperator.POSITIVE:
                return operand
            if node.operator is UnaryOperator.NEGATIVE:
                return _negate_polynomial(operand, limits=limits)
            raise TypeError("unknown closed unary operator")
        if node_type is FunctionCallNode:
            kind = (
                PolynomialFailureKind.NON_POLYNOMIAL
                if any(_contains_variable(argument) for argument in expression.arguments)
                else PolynomialFailureKind.NON_RATIONAL_COEFFICIENT
            )
            raise EquationPolynomialError(
                kind,
                expression.normalized_span,
                expression.source_span,
            )
        if node_type is BinaryOpNode:
            return _visit_binary(expression, limits=limits)
        raise TypeError("expression must be a closed RestrictedExpression")
    except ExactRationalLimitExceeded as exc:
        mapped_error = EquationPolynomialError(
            PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED,
            expression.normalized_span,
            expression.source_span,
            exc.component,
            exc.limit,
        )
        raise mapped_error from None
    except ExactRationalZeroDivision:
        mapped_error = EquationPolynomialError(
            PolynomialFailureKind.ZERO_DENOMINATOR,
            expression.normalized_span,
            expression.source_span,
        )
        raise mapped_error from None


def _visit_binary(
    node: BinaryOpNode,
    *,
    limits: ApplicationLimits,
) -> BoundedQuadraticPolynomial:
    left = _visit(node.left, limits=limits)
    operator = node.operator
    if operator is BinaryOperator.POWER:
        exponent = _direct_exponent(node.right, limits=limits)
        if exponent is None:
            raise EquationPolynomialError(
                PolynomialFailureKind.NON_POLYNOMIAL,
                node.normalized_span,
                node.source_span,
            )
        if not left.contains_variable:
            raise EquationPolynomialError(
                PolynomialFailureKind.UNSUPPORTED_EQUATION,
                node.normalized_span,
                node.source_span,
            )
        if exponent == _ZERO:
            kind = PolynomialFailureKind.UNSUPPORTED_EQUATION
        elif exponent == _ONE:
            return left
        elif exponent == Fraction(2, 1):
            return _multiply_polynomials(
                left,
                left,
                normalized_span=node.normalized_span,
                source_span=node.source_span,
                limits=limits,
            )
        elif exponent < _ZERO:
            kind = PolynomialFailureKind.VARIABLE_DENOMINATOR
        elif exponent.denominator == 1 and exponent > Fraction(2, 1):
            kind = PolynomialFailureKind.DEGREE_EXCEEDED
        else:
            kind = PolynomialFailureKind.NON_POLYNOMIAL
        raise EquationPolynomialError(kind, node.normalized_span, node.source_span)

    right = _visit(node.right, limits=limits)
    if operator is BinaryOperator.ADD:
        return _add_polynomials(left, right, limits=limits)
    if operator is BinaryOperator.SUBTRACT:
        return _subtract_polynomials(left, right, limits=limits)
    if operator is BinaryOperator.MULTIPLY:
        return _multiply_polynomials(
            left,
            right,
            normalized_span=node.normalized_span,
            source_span=node.source_span,
            limits=limits,
        )
    if operator is BinaryOperator.DIVIDE:
        if right.contains_variable:
            raise EquationPolynomialError(
                PolynomialFailureKind.VARIABLE_DENOMINATOR,
                node.normalized_span,
                node.source_span,
            )
        if right.constant == _ZERO:
            raise EquationPolynomialError(
                PolynomialFailureKind.ZERO_DENOMINATOR,
                node.right.normalized_span,
                node.right.source_span,
            )
        return _divide_polynomial(left, right.constant, limits=limits)
    raise TypeError("unknown closed binary operator")


def _polynomial(
    constant: Fraction,
    *,
    x: Fraction = _ZERO,
    y: Fraction = _ZERO,
    x_squared: Fraction = _ZERO,
    x_y: Fraction = _ZERO,
    y_squared: Fraction = _ZERO,
    degree: int = 0,
    limits: ApplicationLimits,
) -> BoundedQuadraticPolynomial:
    return BoundedQuadraticPolynomial(
        constant,
        x,
        y,
        x_squared,
        x_y,
        y_squared,
        degree,
        degree != 0,
        limits=limits,
    )


def _negate_polynomial(
    value: BoundedQuadraticPolynomial,
    *,
    limits: ApplicationLimits,
) -> BoundedQuadraticPolynomial:
    return BoundedQuadraticPolynomial(
        checked_negate(value.constant, limits=limits),
        checked_negate(value.x, limits=limits),
        checked_negate(value.y, limits=limits),
        checked_negate(value.x_squared, limits=limits),
        checked_negate(value.x_y, limits=limits),
        checked_negate(value.y_squared, limits=limits),
        value.structural_degree,
        value.contains_variable,
        limits=limits,
    )


def _add_polynomials(
    left: BoundedQuadraticPolynomial,
    right: BoundedQuadraticPolynomial,
    *,
    limits: ApplicationLimits,
) -> BoundedQuadraticPolynomial:
    return BoundedQuadraticPolynomial(
        checked_add(left.constant, right.constant, limits=limits),
        checked_add(left.x, right.x, limits=limits),
        checked_add(left.y, right.y, limits=limits),
        checked_add(left.x_squared, right.x_squared, limits=limits),
        checked_add(left.x_y, right.x_y, limits=limits),
        checked_add(left.y_squared, right.y_squared, limits=limits),
        max(left.structural_degree, right.structural_degree),
        left.contains_variable or right.contains_variable,
        limits=limits,
    )


def _subtract_polynomials(
    left: BoundedQuadraticPolynomial,
    right: BoundedQuadraticPolynomial,
    *,
    limits: ApplicationLimits,
) -> BoundedQuadraticPolynomial:
    return BoundedQuadraticPolynomial(
        checked_subtract(left.constant, right.constant, limits=limits),
        checked_subtract(left.x, right.x, limits=limits),
        checked_subtract(left.y, right.y, limits=limits),
        checked_subtract(left.x_squared, right.x_squared, limits=limits),
        checked_subtract(left.x_y, right.x_y, limits=limits),
        checked_subtract(left.y_squared, right.y_squared, limits=limits),
        max(left.structural_degree, right.structural_degree),
        left.contains_variable or right.contains_variable,
        limits=limits,
    )


def _multiply_polynomials(
    left: BoundedQuadraticPolynomial,
    right: BoundedQuadraticPolynomial,
    *,
    normalized_span: SourceSpan,
    source_span: SourceSpan,
    limits: ApplicationLimits,
) -> BoundedQuadraticPolynomial:
    degree = left.structural_degree + right.structural_degree
    if degree > 2:
        raise EquationPolynomialError(
            PolynomialFailureKind.DEGREE_EXCEEDED,
            normalized_span,
            source_span,
        )

    constant = checked_multiply(left.constant, right.constant, limits=limits)
    x = checked_add(
        checked_multiply(left.x, right.constant, limits=limits),
        checked_multiply(left.constant, right.x, limits=limits),
        limits=limits,
    )
    y = checked_add(
        checked_multiply(left.y, right.constant, limits=limits),
        checked_multiply(left.constant, right.y, limits=limits),
        limits=limits,
    )
    x_squared = checked_add(
        checked_add(
            checked_multiply(left.x_squared, right.constant, limits=limits),
            checked_multiply(left.x, right.x, limits=limits),
            limits=limits,
        ),
        checked_multiply(left.constant, right.x_squared, limits=limits),
        limits=limits,
    )
    x_y = checked_add(
        checked_add(
            checked_add(
                checked_multiply(left.x_y, right.constant, limits=limits),
                checked_multiply(left.x, right.y, limits=limits),
                limits=limits,
            ),
            checked_multiply(left.y, right.x, limits=limits),
            limits=limits,
        ),
        checked_multiply(left.constant, right.x_y, limits=limits),
        limits=limits,
    )
    y_squared = checked_add(
        checked_add(
            checked_multiply(left.y_squared, right.constant, limits=limits),
            checked_multiply(left.y, right.y, limits=limits),
            limits=limits,
        ),
        checked_multiply(left.constant, right.y_squared, limits=limits),
        limits=limits,
    )
    return BoundedQuadraticPolynomial(
        constant,
        x,
        y,
        x_squared,
        x_y,
        y_squared,
        degree,
        left.contains_variable or right.contains_variable,
        limits=limits,
    )


def _divide_polynomial(
    numerator: BoundedQuadraticPolynomial,
    denominator: Fraction,
    *,
    limits: ApplicationLimits,
) -> BoundedQuadraticPolynomial:
    return BoundedQuadraticPolynomial(
        checked_divide(numerator.constant, denominator, limits=limits),
        checked_divide(numerator.x, denominator, limits=limits),
        checked_divide(numerator.y, denominator, limits=limits),
        checked_divide(numerator.x_squared, denominator, limits=limits),
        checked_divide(numerator.x_y, denominator, limits=limits),
        checked_divide(numerator.y_squared, denominator, limits=limits),
        numerator.structural_degree,
        numerator.contains_variable,
        limits=limits,
    )


def _direct_exponent(
    expression: RestrictedExpression,
    *,
    limits: ApplicationLimits,
) -> Fraction | None:
    if type(expression) is NumberNode:
        return fraction_from_number_lexeme(expression.lexeme, limits=limits)
    if type(expression) is not UnaryOpNode or type(expression.operand) is not NumberNode:
        return None
    value = fraction_from_number_lexeme(expression.operand.lexeme, limits=limits)
    if expression.operator is UnaryOperator.POSITIVE:
        return value
    if expression.operator is UnaryOperator.NEGATIVE:
        return checked_negate(value, limits=limits)
    raise TypeError("unknown closed unary operator in exponent")


def _contains_variable(expression: RestrictedExpression) -> bool:
    _require_expression(expression)
    node_type = type(expression)
    if node_type is SymbolNode:
        return True
    if node_type in {NumberNode, ConstantNode}:
        return False
    if node_type is UnaryOpNode:
        return _contains_variable(expression.operand)
    if node_type is BinaryOpNode:
        return _contains_variable(expression.left) or _contains_variable(expression.right)
    if node_type is FunctionCallNode:
        return any(_contains_variable(argument) for argument in expression.arguments)
    raise TypeError("expression must be a closed RestrictedExpression")


def _validated_coefficients(
    polynomial: BoundedQuadraticPolynomial,
    *,
    limits: ApplicationLimits,
) -> tuple[Fraction, Fraction, Fraction, Fraction, Fraction, Fraction]:
    return (
        ensure_fraction_within_limits(polynomial.constant, limits=limits),
        ensure_fraction_within_limits(polynomial.x, limits=limits),
        ensure_fraction_within_limits(polynomial.y, limits=limits),
        ensure_fraction_within_limits(polynomial.x_squared, limits=limits),
        ensure_fraction_within_limits(polynomial.x_y, limits=limits),
        ensure_fraction_within_limits(polynomial.y_squared, limits=limits),
    )


def _equation_spans(
    left: RestrictedExpression,
    right: RestrictedExpression,
) -> tuple[SourceSpan, SourceSpan]:
    return (
        SourceSpan(
            min(left.normalized_span.start, right.normalized_span.start),
            max(left.normalized_span.end, right.normalized_span.end),
        ),
        SourceSpan(
            min(left.source_span.start, right.source_span.start),
            max(left.source_span.end, right.source_span.end),
        ),
    )


def _require_expression(expression: object) -> None:
    if type(expression) not in {
        NumberNode,
        SymbolNode,
        ConstantNode,
        UnaryOpNode,
        BinaryOpNode,
        FunctionCallNode,
    }:
        raise TypeError("expression must be an exact RestrictedExpression node")


def _require_limits(limits: object) -> None:
    if type(limits) is not ApplicationLimits:
        raise TypeError("limits must be an exact ApplicationLimits")


def _require_span(span: object, name: str) -> None:
    if type(span) is not SourceSpan:
        raise TypeError(f"{name} must be an exact SourceSpan")


__all__ = [
    "BoundedQuadraticPolynomial",
    "EquationPolynomialError",
    "PolynomialFailureKind",
    "canonicalize_equation",
    "canonicalize_polynomial",
    "polynomial_from_equation",
    "polynomial_from_restricted_expression",
]
