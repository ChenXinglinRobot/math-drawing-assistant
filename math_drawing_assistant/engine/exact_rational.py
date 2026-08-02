"""Bounded exact-rational primitives for stage 13B-1."""

from __future__ import annotations

from enum import Enum
from fractions import Fraction
from math import gcd

from math_drawing_assistant.config.limits import ApplicationLimits, DEFAULT_LIMITS


_CHUNK_SIZE = 9


class ExactLimitComponent(str, Enum):
    """The three bounded integer spaces used by exact equation arithmetic."""

    COEFFICIENT_NUMERATOR = "coefficient numerator"
    COEFFICIENT_DENOMINATOR = "coefficient denominator"
    CANONICAL_INTEGER = "canonical integer"


class ExactRationalLimitExceeded(ArithmeticError):
    """Report one exact-arithmetic digit limit without retaining operands."""

    component: ExactLimitComponent
    limit: int

    def __init__(self, component: ExactLimitComponent, limit: int) -> None:
        if type(component) is not ExactLimitComponent:
            raise TypeError("component must be an ExactLimitComponent")
        if type(limit) is not int:
            raise TypeError("limit must be a positive exact int")
        if limit <= 0:
            raise ValueError("limit must be a positive exact int")
        self.component = component
        self.limit = limit
        super().__init__(f"{component.value} digit limit exceeded (limit={limit})")


class ExactRationalZeroDivision(ZeroDivisionError):
    """Report exact division by zero without retaining either operand."""

    def __init__(self) -> None:
        super().__init__("exact rational division by zero")


def _require_limits(limits: object) -> ApplicationLimits:
    if type(limits) is not ApplicationLimits:
        raise TypeError("limits must be an exact ApplicationLimits")
    return limits


def _require_exact_integer(value: object, message: str) -> int:
    if type(value) is not int:
        raise TypeError(message)
    return value


def _require_positive_exact_integer(value: object, message: str) -> int:
    integer = _require_exact_integer(value, message)
    if integer <= 0:
        raise ValueError(message)
    return integer


def _require_fraction(value: object) -> Fraction:
    if type(value) is not Fraction:
        raise TypeError("value must be an exact Fraction")
    return value


def _require_component(component: object) -> ExactLimitComponent:
    if type(component) is not ExactLimitComponent:
        raise TypeError("component must be an ExactLimitComponent")
    return component


def _decimal_threshold(limit: int) -> int:
    """Return 10**limit after validating the small controlling exponent."""

    positive_limit = _require_positive_exact_integer(
        limit,
        "limit must be a positive exact int",
    )
    return 10**positive_limit


def _ensure_integer_within_digits(
    value: int,
    *,
    limit: int,
    component: ExactLimitComponent,
) -> int:
    """Apply the exact ``abs(value) < 10**limit`` decimal digit rule."""

    integer = _require_exact_integer(value, "value must be an exact int")
    positive_limit = _require_positive_exact_integer(
        limit,
        "limit must be a positive exact int",
    )
    exact_component = _require_component(component)

    magnitude = abs(integer)
    if magnitude == 0:
        return integer
    bits = magnitude.bit_length()

    # 2^33 < 10^10, so this condition proves magnitude < 10^limit.
    if 10 * bits <= 33 * positive_limit:
        return integer
    # 2^10 > 10^3, so this condition proves magnitude > 10^limit.
    if 3 * (bits - 1) >= 10 * positive_limit:
        raise ExactRationalLimitExceeded(exact_component, positive_limit)

    if magnitude >= _decimal_threshold(positive_limit):
        raise ExactRationalLimitExceeded(exact_component, positive_limit)
    return integer


def _checked_integer_product(
    left: int,
    right: int,
    *,
    digit_limit: int,
    component: ExactLimitComponent,
) -> int:
    """Multiply exact integers only after a deterministic decimal bound check."""

    left_integer = _require_exact_integer(left, "left must be an exact int")
    right_integer = _require_exact_integer(right, "right must be an exact int")
    positive_limit = _require_positive_exact_integer(
        digit_limit,
        "digit_limit must be a positive exact int",
    )
    exact_component = _require_component(component)

    _ensure_integer_within_digits(
        left_integer,
        limit=positive_limit,
        component=exact_component,
    )
    _ensure_integer_within_digits(
        right_integer,
        limit=positive_limit,
        component=exact_component,
    )
    if left_integer == 0 or right_integer == 0:
        return 0

    maximum_magnitude = _decimal_threshold(positive_limit) - 1
    if abs(left_integer) > maximum_magnitude // abs(right_integer):
        raise ExactRationalLimitExceeded(exact_component, positive_limit)

    product = left_integer * right_integer
    return _ensure_integer_within_digits(
        product,
        limit=positive_limit,
        component=exact_component,
    )


def _checked_integer_add(
    left: int,
    right: int,
    *,
    digit_limit: int,
    component: ExactLimitComponent,
) -> int:
    left_integer = _require_exact_integer(left, "left must be an exact int")
    right_integer = _require_exact_integer(right, "right must be an exact int")
    positive_limit = _require_positive_exact_integer(
        digit_limit,
        "digit_limit must be a positive exact int",
    )
    exact_component = _require_component(component)
    result = left_integer + right_integer
    return _ensure_integer_within_digits(
        result,
        limit=positive_limit,
        component=exact_component,
    )


def _checked_integer_subtract(
    left: int,
    right: int,
    *,
    digit_limit: int,
    component: ExactLimitComponent,
) -> int:
    left_integer = _require_exact_integer(left, "left must be an exact int")
    right_integer = _require_exact_integer(right, "right must be an exact int")
    positive_limit = _require_positive_exact_integer(
        digit_limit,
        "digit_limit must be a positive exact int",
    )
    exact_component = _require_component(component)
    result = left_integer - right_integer
    return _ensure_integer_within_digits(
        result,
        limit=positive_limit,
        component=exact_component,
    )


def ensure_fraction_within_limits(
    value: Fraction,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> Fraction:
    """Validate an exact Fraction against coefficient numerator and denominator limits."""

    fraction = _require_fraction(value)
    active_limits = _require_limits(limits)
    _ensure_integer_within_digits(
        fraction.numerator,
        limit=active_limits.max_equation_coefficient_numerator_digits,
        component=ExactLimitComponent.COEFFICIENT_NUMERATOR,
    )
    _ensure_integer_within_digits(
        fraction.denominator,
        limit=active_limits.max_equation_coefficient_denominator_digits,
        component=ExactLimitComponent.COEFFICIENT_DENOMINATOR,
    )
    return fraction


def _integer_from_ascii_digits(
    digits: str,
    *,
    limit: int,
    component: ExactLimitComponent,
) -> int:
    if type(digits) is not str:
        raise TypeError("digits must be an exact str")
    if not digits or any(character < "0" or character > "9" for character in digits):
        raise ValueError("digits must be a non-empty ASCII digit string")
    positive_limit = _require_positive_exact_integer(
        limit,
        "limit must be a positive exact int",
    )
    exact_component = _require_component(component)

    significant = digits.lstrip("0")
    if not significant:
        return 0
    if len(significant) > positive_limit:
        raise ExactRationalLimitExceeded(exact_component, positive_limit)

    # Parse digit-by-digit in small chunks so that int() never receives
    # a full long digit string.  This keeps the module independent of the
    # process-level Python int-to-string conversion limit
    # (sys.set_int_max_str_digits) even when the project canonical
    # integer limit is configured above the CPython default.
    accumulator = 0
    pos = 0
    while pos < len(significant):
        chunk_end = min(pos + _CHUNK_SIZE, len(significant))
        chunk = significant[pos:chunk_end]
        chunk_value = int(chunk)  # safe: len(chunk) <= 9

        scaled = _checked_integer_product(
            accumulator,
            10 ** len(chunk),
            digit_limit=positive_limit,
            component=exact_component,
        )
        accumulator = _checked_integer_add(
            scaled,
            chunk_value,
            digit_limit=positive_limit,
            component=exact_component,
        )
        pos = chunk_end

    return accumulator


def _split_number_lexeme(lexeme: object) -> tuple[str, str | None]:
    if type(lexeme) is not str:
        raise TypeError("lexeme must be an exact str")
    if not lexeme or lexeme.count(".") > 1:
        raise ValueError("number lexeme does not match the supported NUMBER grammar")
    if "." not in lexeme:
        if not lexeme.isascii() or not lexeme.isdigit():
            raise ValueError(
                "number lexeme does not match the supported NUMBER grammar",
            )
        return lexeme, None

    whole, fractional = lexeme.split(".")
    if (
        not fractional
        or not fractional.isascii()
        or not fractional.isdigit()
        or (whole and (not whole.isascii() or not whole.isdigit()))
    ):
        raise ValueError("number lexeme does not match the supported NUMBER grammar")
    return whole, fractional


def fraction_from_number_lexeme(
    lexeme: str,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> Fraction:
    """Convert one unsigned integer or finite-decimal NUMBER lexeme exactly."""

    whole_digits, fractional_digits = _split_number_lexeme(lexeme)
    active_limits = _require_limits(limits)
    canonical_limit = active_limits.max_equation_canonical_coefficient_digits
    component = ExactLimitComponent.CANONICAL_INTEGER
    trimmed_fraction = (
        None if fractional_digits is None else fractional_digits.rstrip("0")
    )

    whole_value = _integer_from_ascii_digits(
        whole_digits or "0",
        limit=canonical_limit,
        component=component,
    )
    if trimmed_fraction is None:
        return ensure_fraction_within_limits(
            Fraction(whole_value, 1),
            limits=active_limits,
        )

    if not trimmed_fraction:
        return ensure_fraction_within_limits(
            Fraction(whole_value, 1),
            limits=active_limits,
        )

    scale = len(trimmed_fraction)
    if scale >= canonical_limit:
        raise ExactRationalLimitExceeded(component, canonical_limit)
    denominator = 10**scale
    _ensure_integer_within_digits(
        denominator,
        limit=canonical_limit,
        component=component,
    )
    scaled_whole = _checked_integer_product(
        whole_value,
        denominator,
        digit_limit=canonical_limit,
        component=component,
    )
    fractional_value = _integer_from_ascii_digits(
        trimmed_fraction,
        limit=canonical_limit,
        component=component,
    )
    raw_numerator = _checked_integer_add(
        scaled_whole,
        fractional_value,
        digit_limit=canonical_limit,
        component=component,
    )
    return ensure_fraction_within_limits(
        Fraction(raw_numerator, denominator),
        limits=active_limits,
    )


def checked_negate(
    value: Fraction,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> Fraction:
    fraction = ensure_fraction_within_limits(value, limits=limits)
    result = Fraction(-fraction.numerator, fraction.denominator)
    return ensure_fraction_within_limits(result, limits=limits)


def _checked_add_or_subtract(
    left: Fraction,
    right: Fraction,
    *,
    limits: ApplicationLimits,
    subtract: bool,
) -> Fraction:
    left_fraction = ensure_fraction_within_limits(left, limits=limits)
    right_fraction = ensure_fraction_within_limits(right, limits=limits)
    canonical_limit = limits.max_equation_canonical_coefficient_digits
    component = ExactLimitComponent.CANONICAL_INTEGER

    denominator_gcd = gcd(left_fraction.denominator, right_fraction.denominator)
    left_scale = right_fraction.denominator // denominator_gcd
    right_scale = left_fraction.denominator // denominator_gcd
    left_term = _checked_integer_product(
        left_fraction.numerator,
        left_scale,
        digit_limit=canonical_limit,
        component=component,
    )
    right_term = _checked_integer_product(
        right_fraction.numerator,
        right_scale,
        digit_limit=canonical_limit,
        component=component,
    )
    common_denominator = _checked_integer_product(
        left_fraction.denominator,
        left_scale,
        digit_limit=canonical_limit,
        component=component,
    )
    if subtract:
        raw_numerator = _checked_integer_subtract(
            left_term,
            right_term,
            digit_limit=canonical_limit,
            component=component,
        )
    else:
        raw_numerator = _checked_integer_add(
            left_term,
            right_term,
            digit_limit=canonical_limit,
            component=component,
        )
    result = Fraction(raw_numerator, common_denominator)
    return ensure_fraction_within_limits(result, limits=limits)


def checked_add(
    left: Fraction,
    right: Fraction,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> Fraction:
    active_limits = _require_limits(limits)
    return _checked_add_or_subtract(
        left,
        right,
        limits=active_limits,
        subtract=False,
    )


def checked_subtract(
    left: Fraction,
    right: Fraction,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> Fraction:
    active_limits = _require_limits(limits)
    return _checked_add_or_subtract(
        left,
        right,
        limits=active_limits,
        subtract=True,
    )


def checked_multiply(
    left: Fraction,
    right: Fraction,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> Fraction:
    active_limits = _require_limits(limits)
    left_fraction = ensure_fraction_within_limits(left, limits=active_limits)
    right_fraction = ensure_fraction_within_limits(right, limits=active_limits)

    a = left_fraction.numerator
    b = left_fraction.denominator
    c = right_fraction.numerator
    d = right_fraction.denominator
    first_gcd = gcd(abs(a), d)
    second_gcd = gcd(abs(c), b)
    a_reduced = a // first_gcd
    d_reduced = d // first_gcd
    c_reduced = c // second_gcd
    b_reduced = b // second_gcd
    numerator = _checked_integer_product(
        a_reduced,
        c_reduced,
        digit_limit=active_limits.max_equation_coefficient_numerator_digits,
        component=ExactLimitComponent.COEFFICIENT_NUMERATOR,
    )
    denominator = _checked_integer_product(
        b_reduced,
        d_reduced,
        digit_limit=active_limits.max_equation_coefficient_denominator_digits,
        component=ExactLimitComponent.COEFFICIENT_DENOMINATOR,
    )
    return ensure_fraction_within_limits(
        Fraction(numerator, denominator),
        limits=active_limits,
    )


def checked_divide(
    dividend: Fraction,
    divisor: Fraction,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> Fraction:
    active_limits = _require_limits(limits)
    dividend_fraction = ensure_fraction_within_limits(dividend, limits=active_limits)
    divisor_fraction = ensure_fraction_within_limits(divisor, limits=active_limits)
    if divisor_fraction.numerator == 0:
        raise ExactRationalZeroDivision()

    a = dividend_fraction.numerator
    b = dividend_fraction.denominator
    c = divisor_fraction.numerator
    d = divisor_fraction.denominator
    c_abs = abs(c)
    first_gcd = gcd(abs(a), c_abs)
    a_reduced = a // first_gcd
    c_reduced = c_abs // first_gcd
    second_gcd = gcd(d, b)
    d_reduced = d // second_gcd
    b_reduced = b // second_gcd
    numerator = _checked_integer_product(
        a_reduced,
        d_reduced,
        digit_limit=active_limits.max_equation_coefficient_numerator_digits,
        component=ExactLimitComponent.COEFFICIENT_NUMERATOR,
    )
    if c < 0:
        numerator = -numerator
    _ensure_integer_within_digits(
        numerator,
        limit=active_limits.max_equation_coefficient_numerator_digits,
        component=ExactLimitComponent.COEFFICIENT_NUMERATOR,
    )
    denominator = _checked_integer_product(
        b_reduced,
        c_reduced,
        digit_limit=active_limits.max_equation_coefficient_denominator_digits,
        component=ExactLimitComponent.COEFFICIENT_DENOMINATOR,
    )
    return ensure_fraction_within_limits(
        Fraction(numerator, denominator),
        limits=active_limits,
    )


def ensure_canonical_integer_within_limit(
    value: int,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> int:
    integer = _require_exact_integer(value, "value must be an exact int")
    active_limits = _require_limits(limits)
    return _ensure_integer_within_digits(
        integer,
        limit=active_limits.max_equation_canonical_coefficient_digits,
        component=ExactLimitComponent.CANONICAL_INTEGER,
    )


def checked_positive_lcm(
    left: int,
    right: int,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> int:
    left_integer = _require_exact_integer(left, "left must be an exact int")
    right_integer = _require_exact_integer(right, "right must be an exact int")
    if left_integer <= 0:
        raise ValueError("left must be a positive exact int")
    if right_integer <= 0:
        raise ValueError("right must be a positive exact int")
    active_limits = _require_limits(limits)
    ensure_canonical_integer_within_limit(left_integer, limits=active_limits)
    ensure_canonical_integer_within_limit(right_integer, limits=active_limits)
    left_reduced = left_integer // gcd(left_integer, right_integer)
    return _checked_integer_product(
        left_reduced,
        right_integer,
        digit_limit=active_limits.max_equation_canonical_coefficient_digits,
        component=ExactLimitComponent.CANONICAL_INTEGER,
    )


def checked_scale_fraction_to_integer(
    value: Fraction,
    common_denominator: int,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> int:
    active_limits = _require_limits(limits)
    fraction = ensure_fraction_within_limits(value, limits=active_limits)
    common = _require_exact_integer(
        common_denominator,
        "common_denominator must be an exact int",
    )
    if common <= 0:
        raise ValueError("common_denominator must be positive")
    ensure_canonical_integer_within_limit(common, limits=active_limits)
    if common % fraction.denominator != 0:
        raise ValueError(
            "common denominator must be divisible by the Fraction denominator",
        )
    scale = common // fraction.denominator
    ensure_canonical_integer_within_limit(scale, limits=active_limits)
    return _checked_integer_product(
        fraction.numerator,
        scale,
        digit_limit=active_limits.max_equation_canonical_coefficient_digits,
        component=ExactLimitComponent.CANONICAL_INTEGER,
    )


__all__ = [
    "ExactLimitComponent",
    "ExactRationalLimitExceeded",
    "ExactRationalZeroDivision",
    "checked_add",
    "checked_divide",
    "checked_multiply",
    "checked_negate",
    "checked_positive_lcm",
    "checked_scale_fraction_to_integer",
    "checked_subtract",
    "ensure_canonical_integer_within_limit",
    "ensure_fraction_within_limits",
    "fraction_from_number_lexeme",
]
