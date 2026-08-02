"""Stage 13B-1 tests for the bounded exact-rational kernel."""

from __future__ import annotations

import ast
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from math_drawing_assistant.config.limits import DEFAULT_LIMITS
from math_drawing_assistant.engine.exact_rational import (
    ExactLimitComponent,
    ExactRationalLimitExceeded,
    ExactRationalZeroDivision,
    _checked_integer_add,
    _checked_integer_product,
    _ensure_integer_within_digits,
    _integer_from_ascii_digits,
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


N = DEFAULT_LIMITS.max_equation_coefficient_numerator_digits
D = DEFAULT_LIMITS.max_equation_coefficient_denominator_digits
K = DEFAULT_LIMITS.max_equation_canonical_coefficient_digits


class _IntSubclass(int):
    pass


class _FractionSubclass(Fraction):
    pass


def _assert_limit(
    exception: pytest.ExceptionInfo[ExactRationalLimitExceeded],
    component: ExactLimitComponent,
    limit: int,
) -> None:
    assert exception.value.component is component
    assert exception.value.limit == limit
    assert str(exception.value) == (
        f"{component.value} digit limit exceeded (limit={limit})"
    )


def test_exact_limit_component_is_the_frozen_three_member_contract() -> None:
    assert [(member.name, member.value) for member in ExactLimitComponent] == [
        ("COEFFICIENT_NUMERATOR", "coefficient numerator"),
        ("COEFFICIENT_DENOMINATOR", "coefficient denominator"),
        ("CANONICAL_INTEGER", "canonical integer"),
    ]


def test_limit_exception_is_typed_stable_and_does_not_retain_operands() -> None:
    error = ExactRationalLimitExceeded(
        ExactLimitComponent.COEFFICIENT_NUMERATOR,
        128,
    )
    assert isinstance(error, ArithmeticError)
    assert error.component is ExactLimitComponent.COEFFICIENT_NUMERATOR
    assert error.limit == 128
    assert str(error) == "coefficient numerator digit limit exceeded (limit=128)"
    assert "private" not in repr(error)
    assert set(error.__dict__) == {"component", "limit"}

    with pytest.raises(TypeError):
        ExactRationalLimitExceeded("coefficient numerator", 128)  # type: ignore[arg-type]
    for value in (True, 1.0, "128"):
        with pytest.raises(TypeError):
            ExactRationalLimitExceeded(  # type: ignore[arg-type]
                ExactLimitComponent.CANONICAL_INTEGER,
                value,
            )
    for value in (0, -1):
        with pytest.raises(ValueError):
            ExactRationalLimitExceeded(ExactLimitComponent.CANONICAL_INTEGER, value)


def test_zero_division_exception_has_one_fixed_private_message() -> None:
    error = ExactRationalZeroDivision()
    assert isinstance(error, ZeroDivisionError)
    assert str(error) == "exact rational division by zero"
    assert error.args == ("exact rational division by zero",)


@pytest.mark.parametrize("value", [True, 1.0, _IntSubclass(1)])
def test_canonical_integer_api_rejects_non_exact_ints(value: object) -> None:
    with pytest.raises(TypeError, match="exact int"):
        ensure_canonical_integer_within_limit(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [1, True, 1.0, Decimal("1"), "1", _FractionSubclass(1, 2)],
)
def test_fraction_apis_reject_non_exact_fractions(value: object) -> None:
    with pytest.raises(TypeError, match="exact Fraction"):
        ensure_fraction_within_limits(value)  # type: ignore[arg-type]


def test_decimal_digit_gate_matches_exact_boundary_for_both_signs_and_zero() -> None:
    component = ExactLimitComponent.CANONICAL_INTEGER
    for value in (0, 10**K - 1, -(10**K - 1)):
        assert _ensure_integer_within_digits(
            value,
            limit=K,
            component=component,
        ) == value
    for value in (10**K, -(10**K)):
        with pytest.raises(ExactRationalLimitExceeded) as exception:
            _ensure_integer_within_digits(value, limit=K, component=component)
        _assert_limit(exception, component, K)


def test_bit_length_fast_accept_reject_and_ambiguous_boundaries_are_exact() -> None:
    component = ExactLimitComponent.CANONICAL_INTEGER
    assert _ensure_integer_within_digits(2**31, limit=10, component=component) == 2**31
    with pytest.raises(ExactRationalLimitExceeded):
        _ensure_integer_within_digits(2**34, limit=10, component=component)
    assert _ensure_integer_within_digits(10**10 - 1, limit=10, component=component)
    with pytest.raises(ExactRationalLimitExceeded):
        _ensure_integer_within_digits(10**10, limit=10, component=component)


def test_digit_gate_handles_more_than_the_default_int_string_limit_without_conversion() -> None:
    limits = replace(
        DEFAULT_LIMITS,
        max_input_characters=5_000,
        max_equation_canonical_coefficient_digits=5_000,
    )
    huge = 10**4_500
    assert ensure_canonical_integer_within_limit(huge, limits=limits) is huge


def test_checked_integer_product_preflights_and_rechecks_the_exact_boundary() -> None:
    component = ExactLimitComponent.CANONICAL_INTEGER
    assert _checked_integer_product(
        10**10 - 1,
        1,
        digit_limit=10,
        component=component,
    ) == 10**10 - 1
    assert _checked_integer_product(
        0,
        10**10 - 1,
        digit_limit=10,
        component=component,
    ) == 0
    with pytest.raises(ExactRationalLimitExceeded):
        _checked_integer_product(
            10**5,
            10**5,
            digit_limit=10,
            component=component,
        )


def test_checked_integer_add_protects_raw_canonical_sum_and_allows_cancellation() -> None:
    component = ExactLimitComponent.CANONICAL_INTEGER
    assert _checked_integer_add(
        10**K - 1,
        -(10**K - 1),
        digit_limit=K,
        component=component,
    ) == 0
    with pytest.raises(ExactRationalLimitExceeded):
        _checked_integer_add(
            10**K - 1,
            1,
            digit_limit=K,
            component=component,
        )


def test_number_lexeme_positive_matrix_is_exact() -> None:
    expected = {
        "0": Fraction(0),
        "1": Fraction(1),
        "10": Fraction(10),
        ".5": Fraction(1, 2),
        "0.1": Fraction(1, 10),
        "1.25": Fraction(5, 4),
        "1.2500": Fraction(5, 4),
        "0.000": Fraction(0),
        "0001.2500": Fraction(5, 4),
    }
    assert {text: fraction_from_number_lexeme(text) for text in expected} == expected


@pytest.mark.parametrize(
    "lexeme",
    ["", " ", "+1", "-1", "1e3", "1E3", "1_000", "1/2", "5.", "1..2", "pi", "NaN", "Infinity"],
)
def test_number_lexeme_rejects_every_unpublished_form_without_echo(lexeme: str) -> None:
    with pytest.raises(ValueError) as exception:
        fraction_from_number_lexeme(lexeme)
    assert str(exception.value) == (
        "number lexeme does not match the supported NUMBER grammar"
    )


def test_decimal_conversion_reduces_only_after_canonical_intermediates() -> None:
    lexeme = "1." + "0" * 127 + "5"
    result = fraction_from_number_lexeme(lexeme)
    assert result == Fraction(10**128 + 5, 10**128)
    assert len(str(result.numerator)) == N
    assert len(str(result.denominator)) == D


def test_decimal_conversion_removes_trailing_zeroes_before_scaling() -> None:
    assert fraction_from_number_lexeme("1.25" + "0" * (K + 10)) == Fraction(5, 4)


def test_decimal_scale_and_whole_product_fail_with_canonical_component() -> None:
    with pytest.raises(ExactRationalLimitExceeded) as scale_error:
        fraction_from_number_lexeme("." + "1" * K)
    _assert_limit(scale_error, ExactLimitComponent.CANONICAL_INTEGER, K)

    lexeme = "9" * 400 + "." + "1" * 400
    with pytest.raises(ExactRationalLimitExceeded) as product_error:
        fraction_from_number_lexeme(lexeme)
    _assert_limit(product_error, ExactLimitComponent.CANONICAL_INTEGER, K)
    assert lexeme not in str(product_error.value)


def test_integer_from_ascii_digits_parses_long_strings_via_chunking() -> None:
    """Chunked parsing avoids int(long_string) above the CPython default limit.

    Python 3.11+ defaults to sys.set_int_max_str_digits(4300).  This test
    verifies that _integer_from_ascii_digits parses a string longer than
    that threshold without calling int() on the full digit string and
    without modifying the process-level setting.
    """
    long_digits = "1" * 4_500
    expected = (10**4_500 - 1) // 9
    result = _integer_from_ascii_digits(
        long_digits,
        limit=5_140,
        component=ExactLimitComponent.CANONICAL_INTEGER,
    )
    assert result == expected
    # Length check still applies.
    with pytest.raises(ExactRationalLimitExceeded):
        _integer_from_ascii_digits(
            "1" * 5_141,
            limit=5_140,
            component=ExactLimitComponent.CANONICAL_INTEGER,
        )


@pytest.mark.parametrize(
    ("digits", "exception_type", "message"),
    [
        ("", ValueError, "digits must be a non-empty ASCII digit string"),
        (123, TypeError, "digits must be an exact str"),
        ("１２", ValueError, "digits must be a non-empty ASCII digit string"),
        ("١٢", ValueError, "digits must be a non-empty ASCII digit string"),
        ("12a", ValueError, "digits must be a non-empty ASCII digit string"),
    ],
)
def test_integer_from_ascii_digits_rejects_unclosed_inputs_without_echo(
    digits: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type) as exception:
        _integer_from_ascii_digits(
            digits,  # type: ignore[arg-type]
            limit=5_140,
            component=ExactLimitComponent.CANONICAL_INTEGER,
        )
    assert str(exception.value) == message
    if digits != "":
        assert str(digits) not in str(exception.value)


def test_integer_from_ascii_digits_validates_controls_before_length_limit() -> None:
    oversized = "1" * 10
    with pytest.raises(TypeError, match="limit must be a positive exact int"):
        _integer_from_ascii_digits(
            oversized,
            limit=True,  # type: ignore[arg-type]
            component=ExactLimitComponent.CANONICAL_INTEGER,
        )
    with pytest.raises(TypeError, match="component must be an ExactLimitComponent"):
        _integer_from_ascii_digits(
            oversized,
            limit=1,
            component="canonical integer",  # type: ignore[arg-type]
        )


def test_fraction_from_number_lexeme_chunked_parsing_under_custom_limits() -> None:
    """End-to-end: chunked parsing survives custom limits above the CPython default."""
    long_lexeme = "1" * 4_500
    long_limits = replace(
        DEFAULT_LIMITS,
        max_input_characters=5_000,
        max_equation_coefficient_numerator_digits=4_500,
        max_equation_coefficient_denominator_digits=128,
        max_equation_canonical_coefficient_digits=5_140,
    )
    result = fraction_from_number_lexeme(long_lexeme, limits=long_limits)
    expected = Fraction((10**4_500 - 1) // 9, 1)
    assert result == expected


def test_fraction_limits_check_numerator_before_denominator_and_return_identity() -> None:
    value = Fraction(10**N - 1, 10**D - 1)
    assert ensure_fraction_within_limits(value) is value

    with pytest.raises(ExactRationalLimitExceeded) as numerator_error:
        ensure_fraction_within_limits(Fraction(10**N, 1))
    _assert_limit(
        numerator_error,
        ExactLimitComponent.COEFFICIENT_NUMERATOR,
        N,
    )
    with pytest.raises(ExactRationalLimitExceeded) as denominator_error:
        ensure_fraction_within_limits(Fraction(1, 10**D))
    _assert_limit(
        denominator_error,
        ExactLimitComponent.COEFFICIENT_DENOMINATOR,
        D,
    )
    with pytest.raises(ExactRationalLimitExceeded) as both_error:
        ensure_fraction_within_limits(Fraction(10**N + 1, 10**D + 7))
    assert both_error.value.component is ExactLimitComponent.COEFFICIENT_NUMERATOR


@pytest.mark.parametrize(
    ("value", "expected"),
    [(Fraction(0), Fraction(0)), (Fraction(2, 3), Fraction(-2, 3)), (Fraction(-2, 3), Fraction(2, 3))],
)
def test_checked_negate(value: Fraction, expected: Fraction) -> None:
    assert checked_negate(value) == expected


def test_add_and_subtract_exact_arithmetic_and_large_cancellation() -> None:
    assert checked_add(Fraction(1, 3), Fraction(1, 6)) == Fraction(1, 2)
    assert checked_add(Fraction(-1, 3), Fraction(1, 6)) == Fraction(-1, 6)
    assert checked_subtract(Fraction(1, 3), Fraction(1, 3)) == Fraction(0)
    large = Fraction(10**(N - 1) - 1, 10**(D - 1) + 1)
    assert checked_subtract(large, large) == Fraction(0)


def test_add_reports_final_numerator_and_denominator_limits() -> None:
    with pytest.raises(ExactRationalLimitExceeded) as numerator_error:
        checked_add(Fraction(10**N - 1), Fraction(1))
    assert numerator_error.value.component is ExactLimitComponent.COEFFICIENT_NUMERATOR

    first_denominator = 10 ** (D - 1) + 1
    second_denominator = first_denominator + 1
    with pytest.raises(ExactRationalLimitExceeded) as denominator_error:
        checked_add(Fraction(1, first_denominator), Fraction(1, second_denominator))
    assert denominator_error.value.component is ExactLimitComponent.COEFFICIENT_DENOMINATOR


def test_binary_input_validation_is_left_then_right() -> None:
    invalid_left = Fraction(10**N, 1)
    invalid_right = Fraction(1, 10**D)
    with pytest.raises(ExactRationalLimitExceeded) as exception:
        checked_add(invalid_left, invalid_right)
    assert exception.value.component is ExactLimitComponent.COEFFICIENT_NUMERATOR


def test_multiply_uses_cross_cancellation_before_products() -> None:
    assert checked_multiply(Fraction(2, 3), Fraction(9, 4)) == Fraction(3, 2)
    assert checked_multiply(Fraction(-2, 3), Fraction(9, 4)) == Fraction(-3, 2)
    assert checked_multiply(Fraction(0), Fraction(10**(N - 1), 3)) == Fraction(0)
    power = 10**120
    assert checked_multiply(Fraction(power, 3), Fraction(3, power)) == Fraction(1)


def test_multiply_reports_output_component() -> None:
    with pytest.raises(ExactRationalLimitExceeded) as numerator_error:
        checked_multiply(Fraction(10**64), Fraction(10**64))
    assert numerator_error.value.component is ExactLimitComponent.COEFFICIENT_NUMERATOR

    with pytest.raises(ExactRationalLimitExceeded) as denominator_error:
        checked_multiply(Fraction(1, 10**64 + 1), Fraction(1, 10**64 + 3))
    assert denominator_error.value.component is ExactLimitComponent.COEFFICIENT_DENOMINATOR


@pytest.mark.parametrize(
    ("dividend", "divisor", "expected"),
    [
        (Fraction(2, 3), Fraction(4, 9), Fraction(3, 2)),
        (Fraction(-2, 3), Fraction(4, 9), Fraction(-3, 2)),
        (Fraction(2, 3), Fraction(-4, 9), Fraction(-3, 2)),
        (Fraction(-2, 3), Fraction(-4, 9), Fraction(3, 2)),
        (Fraction(0), Fraction(4, 9), Fraction(0)),
    ],
)
def test_divide_signs_and_values(
    dividend: Fraction,
    divisor: Fraction,
    expected: Fraction,
) -> None:
    assert checked_divide(dividend, divisor) == expected


def test_divide_uses_its_own_two_cross_cancellations() -> None:
    value = Fraction(10**120, 10**120 - 1)
    assert checked_divide(value, value) == Fraction(1)


def test_divide_zero_is_typed_and_input_limits_have_priority() -> None:
    with pytest.raises(ExactRationalZeroDivision, match="exact rational division by zero"):
        checked_divide(Fraction(7, 11), Fraction(0))
    with pytest.raises(ExactRationalLimitExceeded):
        checked_divide(Fraction(10**N), Fraction(0))


def test_divide_reports_output_component() -> None:
    with pytest.raises(ExactRationalLimitExceeded) as numerator_error:
        checked_divide(Fraction(10**64), Fraction(1, 10**64))
    assert numerator_error.value.component is ExactLimitComponent.COEFFICIENT_NUMERATOR

    with pytest.raises(ExactRationalLimitExceeded) as denominator_error:
        checked_divide(Fraction(1, 10**64 + 1), Fraction(10**64))
    assert denominator_error.value.component is ExactLimitComponent.COEFFICIENT_DENOMINATOR


def test_canonical_integer_public_boundary() -> None:
    for value in (0, 10**K - 1, -(10**K - 1)):
        assert ensure_canonical_integer_within_limit(value) == value
    with pytest.raises(ExactRationalLimitExceeded) as exception:
        ensure_canonical_integer_within_limit(10**K)
    _assert_limit(exception, ExactLimitComponent.CANONICAL_INTEGER, K)


def test_positive_lcm_contract_boundary_and_gcd_first_algorithm() -> None:
    assert checked_positive_lcm(1, 1) == 1
    assert checked_positive_lcm(6, 8) == 24
    assert checked_positive_lcm(17, 19) == 323
    shared = 10 ** (K - 1) - 1
    assert checked_positive_lcm(shared, shared) == shared
    for values in ((0, 1), (-1, 1), (1, 0), (1, -1)):
        with pytest.raises(ValueError):
            checked_positive_lcm(*values)
    for value in (True, 1.0, _IntSubclass(1)):
        with pytest.raises(TypeError):
            checked_positive_lcm(value, 1)  # type: ignore[arg-type]


def test_positive_lcm_result_overflow_is_canonical() -> None:
    left = 10 ** (K // 2)
    right = left + 1
    with pytest.raises(ExactRationalLimitExceeded) as exception:
        checked_positive_lcm(left, right)
    _assert_limit(exception, ExactLimitComponent.CANONICAL_INTEGER, K)


def test_scale_fraction_to_integer_contract_and_boundaries() -> None:
    assert checked_scale_fraction_to_integer(Fraction(1, 2), 6) == 3
    assert checked_scale_fraction_to_integer(Fraction(-2, 3), 12) == -8
    assert checked_scale_fraction_to_integer(Fraction(0), 10**100) == 0
    assert checked_scale_fraction_to_integer(Fraction(5, 7), 7) == 5
    with pytest.raises(ValueError, match="divisible"):
        checked_scale_fraction_to_integer(Fraction(1, 3), 4)
    for common in (0, -1):
        with pytest.raises(ValueError):
            checked_scale_fraction_to_integer(Fraction(1), common)
    for common in (True, 1.0, _IntSubclass(1)):
        with pytest.raises(TypeError):
            checked_scale_fraction_to_integer(Fraction(1), common)  # type: ignore[arg-type]


def test_scale_fraction_to_integer_result_limit_and_input_priority() -> None:
    exact_common = 10**K - 1
    assert checked_scale_fraction_to_integer(Fraction(1), exact_common) == exact_common
    with pytest.raises(ExactRationalLimitExceeded) as result_error:
        checked_scale_fraction_to_integer(
            Fraction(10 ** (N - 1) - 1),
            10 ** (K - 1) - 1,
        )
    assert result_error.value.component is ExactLimitComponent.CANONICAL_INTEGER
    with pytest.raises(ExactRationalLimitExceeded) as input_error:
        checked_scale_fraction_to_integer(Fraction(10**N), 1)
    assert input_error.value.component is ExactLimitComponent.COEFFICIENT_NUMERATOR


def test_production_module_ast_has_only_allowed_dependencies_and_calls() -> None:
    path = Path(__file__).parents[2] / "math_drawing_assistant" / "engine" / "exact_rational.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
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
        "enum",
        "fractions",
        "math",
        "math_drawing_assistant.config.limits",
    }
    assert calls.isdisjoint(
        {
            "eval",
            "exec",
            "float",
            "format",
            "log10",
            "log2",
            "repr",
            "set_int_max_str_digits",
            "str",
        },
    )


def test_int_is_not_called_on_full_digit_strings_and_no_global_int_string_patch() -> None:
    """Verify int() is only called on small chunks, never on full digit strings.

    The module must never pass a complete long digit string to int() because
    that could hit the CPython integer-string conversion limit
    (sys.set_int_max_str_digits) even when the value would be within the
    project canonical integer limit.
    """
    path = Path(__file__).parents[2] / "math_drawing_assistant" / "engine" / "exact_rational.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    int_calls = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "int"
        )
    ]
    assert len(int_calls) == 1
    int_call = int_calls[0]
    assert len(int_call.args) == 1
    assert not int_call.keywords
    assert isinstance(int_call.args[0], ast.Name)
    assert int_call.args[0].id == "chunk"

    chunk_size_assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_CHUNK_SIZE"
            for target in node.targets
        )
    ]
    assert len(chunk_size_assignments) == 1
    chunk_size = chunk_size_assignments[0].value
    assert isinstance(chunk_size, ast.Constant)
    assert type(chunk_size.value) is int
    assert 1 <= chunk_size.value <= 9

    source = path.read_text(encoding="utf-8")
    # Only check non-comment lines for the forbidden string.
    code_lines = [
        line for line in source.splitlines()
        if not line.strip().startswith("#")
    ]
    assert "set_int_max_str_digits" not in "\n".join(code_lines), (
        "module must not modify the Python global int-string conversion limit"
    )


def test_production_module_contains_no_later_stage_concepts() -> None:
    path = Path(__file__).parents[2] / "math_drawing_assistant" / "engine" / "exact_rational.py"
    source = path.read_text(encoding="utf-8")
    forbidden = {
        "BinaryOpNode",
        "ErrorInfo",
        "LineSpec",
        "NumberNode",
        "PlotKind",
        "PrimitiveEquationCoefficients",
        "RestrictedExpression",
        "SourceSpan",
        "lhs",
        "rhs",
        "structural_degree",
    }
    assert not (forbidden & set(source.replace("(", " ").split()))
