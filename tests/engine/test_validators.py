"""Semantic, result-model, source-map, and production-entry stage 7 tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from typing import cast

import pytest

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    ExplicitFunctionCandidate,
    ExplicitValidation,
    NormalizedInput,
    ParsedExpressionInput,
    analyze_explicit_function,
    classify_plot,
    normalize_input,
    parse_input,
    split_equation,
    tokenize,
    validate_explicit_candidate,
)
from math_drawing_assistant.models import (
    BinaryOpNode,
    BinaryOperator,
    ConstantName,
    ConstantNode,
    ErrorCode,
    ErrorInfo,
    FunctionCallNode,
    FunctionName,
    NumberNode,
    PlotItemSpec,
    PlotKind,
    RestrictedExpression,
    SourceSpan,
    SymbolNode,
    UnaryOpNode,
    UnaryOperator,
    ValidatedExplicitExpression,
    VariableName,
)
from math_drawing_assistant.models.plot_specs import (
    _create_validated_explicit_expression,
    _issue_validated_expression_contract,
)


def _success(text: str) -> ValidatedExplicitExpression:
    result = analyze_explicit_function(text)
    assert isinstance(result, ValidatedExplicitExpression), result
    return result


def _error(text: str) -> ErrorInfo:
    result = analyze_explicit_function(text)
    assert isinstance(result, ErrorInfo), result
    return result


@pytest.mark.parametrize(
    "text",
    [
        "x",
        "-x",
        "+x",
        "x+1",
        "x-1",
        "2*x",
        "2x",
        "2(x+1)",
        "(x+1)(x-1)",
        "x^2",
        "x**2",
        "x²",
        "-x^2",
        "(-x)^2",
        "x^-2",
        "-x^-2",
        "x^2^3",
        "1/x",
        "x/2*3",
        "sqrt(x)",
        "abs(x)",
        "|x|",
        "|x|+|x+1|",
        "abs(abs(x))",
        "sin(x)",
        "cos(x)",
        "tan(x)",
        "ln(x)",
        "lg(x)",
        "log(x,2)",
        "log(x,10)",
        "exp(x)",
        "2",
        "pi",
        "E",
        "2^x",
        "y=x",
        "x=y",
        "y=x^2",
        "x^2=y",
        "y=2",
        "2=y",
    ],
)
def test_documented_positive_matrix_uses_the_single_typed_entry(text: str) -> None:
    result = _success(text)

    assert result.plot_kind is PlotKind.EXPLICIT_FUNCTION
    assert result.free_variables in {(), ("x",)}
    assert result.normalized_input


@pytest.mark.parametrize(
    ("text", "source_form"),
    [
        ("x", "expression"),
        ("y=x", "y_equals"),
        ("x=y", "equals_y"),
    ],
)
def test_validated_result_records_the_direct_source_form(
    text: str,
    source_form: str,
) -> None:
    assert _success(text).source_form == source_form


def test_constant_functions_have_no_free_variables() -> None:
    for text in ("2", "pi", "E", "y=2", "2=y"):
        assert _success(text).free_variables == ()


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("y+1=x+2", ErrorCode.UNSUPPORTED_EQUATION),
        ("x+y=1", ErrorCode.UNSUPPORTED_EQUATION),
        ("x=2", ErrorCode.UNSUPPORTED_EQUATION),
        ("x^2+y^2=25", ErrorCode.UNSUPPORTED_EQUATION),
        ("y^2=8*x", ErrorCode.UNSUPPORTED_EQUATION),
        ("x^2+y^3=1", ErrorCode.UNSUPPORTED_EQUATION),
        ("y^2=x^3", ErrorCode.UNSUPPORTED_EQUATION),
        ("x^3+y^3=1", ErrorCode.UNSUPPORTED_EQUATION),
        ("sin(x)+y=1", ErrorCode.UNSUPPORTED_EQUATION),
        ("y=y", ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED),
        ("y=x+y", ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED),
        ("y", ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED),
        ("log(x)", ErrorCode.LOG_REQUIRES_BASE),
        ("log()", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("log(x,)", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("log(,10)", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("log(x,10,2)", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("log(x,0)", ErrorCode.INVALID_LOG_BASE),
        ("log(x,1)", ErrorCode.INVALID_LOG_BASE),
        ("log(x,-2)", ErrorCode.INVALID_LOG_BASE),
        ("log(x,x)", ErrorCode.INVALID_LOG_BASE),
        ("log(x,E)", ErrorCode.INVALID_LOG_BASE),
        ("log(x,pi)", ErrorCode.INVALID_LOG_BASE),
        ("log(x,2+1)", ErrorCode.INVALID_LOG_BASE),
        ("sin()", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("sin(x,1)", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("sin", ErrorCode.FUNCTION_CALL_REQUIRED),
        ("sin x", ErrorCode.INVALID_INPUT),
        ("sqrt()", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("sqrt(x,2)", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("x2", ErrorCode.IMPLICIT_MULTIPLICATION_NOT_ALLOWED),
        ("x(x+1)", ErrorCode.IMPLICIT_MULTIPLICATION_NOT_ALLOWED),
        ("(x+1)x", ErrorCode.IMPLICIT_MULTIPLICATION_NOT_ALLOWED),
        ("2sin(x)", ErrorCode.IMPLICIT_MULTIPLICATION_NOT_ALLOWED),
        ("2pi", ErrorCode.IMPLICIT_MULTIPLICATION_NOT_ALLOWED),
        ("||x||", ErrorCode.NESTED_ABSOLUTE_VALUE),
        ("x^x", ErrorCode.UNSUPPORTED_EXPONENT),
        ("x^(x+1)", ErrorCode.UNSUPPORTED_EXPONENT),
        ("x^0.5", ErrorCode.UNSUPPORTED_EXPONENT),
    ],
)
def test_documented_semantic_rejection_matrix_has_stable_codes(
    text: str,
    code: ErrorCode,
) -> None:
    result = _error(text)

    assert result.code is code
    assert result.recoverable is True
    assert result.source_location is not None
    if code is ErrorCode.UNSUPPORTED_EQUATION:
        assert "当前不支持该方程形式" in result.user_message
        assert "一次方程" not in result.user_message
        assert "圆锥曲线" not in result.user_message


@pytest.mark.parametrize(
    "text",
    [
        "a",
        "x+a",
        "unknown(x)",
        "log(x,a)",
        "x garbage",
        "sin(x)abc",
    ],
)
def test_unknown_functions_variables_parameters_and_tails_are_lexically_rejected(
    text: str,
) -> None:
    result = _error(text)
    expected = ErrorCode.INVALID_INPUT if text == "x garbage" else ErrorCode.UNKNOWN_IDENTIFIER
    assert result.code is expected


@pytest.mark.parametrize(
    "text",
    [
        "x.__class__",
        "().__class__",
        '__import__("os")',
        "eval(x)",
        "exec(x)",
        "compile(x)",
        "ast.parse(x)",
        "ast.literal_eval(x)",
        "open(x)",
        "globals()",
        "locals()",
        "lambda",
        '"x"',
        "b'x'",
        "x[0]",
        "[x]",
        "{'x':1}",
        "{x}",
        "[x for x in y]",
        "sin(x=1)",
    ],
)
def test_code_like_and_python_container_inputs_are_structurally_rejected(
    text: str,
) -> None:
    result = _error(text)
    assert result.recoverable is True
    assert result.code in {
        ErrorCode.UNKNOWN_CHARACTER,
        ErrorCode.UNKNOWN_IDENTIFIER,
        ErrorCode.PARSER_SYNTAX_ERROR,
        ErrorCode.UNSUPPORTED_RELATION,
    }


@pytest.mark.parametrize(
    "text",
    ["x+", "x+1)", "x,,1", "sin((x)", "sin(x)abs", "x@tail"],
)
def test_incomplete_or_illegal_tail_never_becomes_a_success(text: str) -> None:
    assert isinstance(analyze_explicit_function(text), ErrorInfo)


def test_log_base_accepts_positive_numeric_literals_other_than_one() -> None:
    assert isinstance(analyze_explicit_function("log(x,.5)"), ValidatedExplicitExpression)
    assert isinstance(analyze_explicit_function("log(x,1.5)"), ValidatedExplicitExpression)


def test_default_literal_exponent_boundary_is_enforced_by_the_public_entry() -> None:
    inside = DEFAULT_LIMITS.max_absolute_exponent - 1
    exact = DEFAULT_LIMITS.max_absolute_exponent
    over = DEFAULT_LIMITS.max_absolute_exponent + 1

    assert isinstance(analyze_explicit_function(f"x^{inside}"), ValidatedExplicitExpression)
    assert isinstance(analyze_explicit_function(f"x^-{exact}"), ValidatedExplicitExpression)
    result = analyze_explicit_function(f"x^{over}")
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.EXPONENT_OUT_OF_RANGE


def test_default_ast_depth_boundary_is_enforced_by_the_public_entry() -> None:
    exact = "-" * (DEFAULT_LIMITS.max_nesting_depth - 1) + "x"
    over = "-" * DEFAULT_LIMITS.max_nesting_depth + "x"

    assert isinstance(analyze_explicit_function(exact), ValidatedExplicitExpression)
    result = analyze_explicit_function(over)
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.AST_DEPTH_LIMIT_EXCEEDED


def test_default_function_argument_limit_rejects_the_next_argument() -> None:
    text = (
        "log("
        + ",".join("x" for _ in range(DEFAULT_LIMITS.max_function_arguments + 1))
        + ")"
    )

    result = analyze_explicit_function(text)
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.FUNCTION_ARGUMENT_ERROR


@pytest.mark.parametrize(
    "text",
    [
        "9" * (DEFAULT_LIMITS.max_numeric_digits + 1),
        "0." + "1" * (DEFAULT_LIMITS.max_decimal_places + 1),
    ],
)
def test_stage_6_numeric_limits_are_preserved_on_the_public_stage_7_entry(
    text: str,
) -> None:
    result = analyze_explicit_function(text)
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.NUMBER_TOO_LONG


def test_source_locations_always_refer_to_original_input() -> None:
    superscript = _success(" x² ")
    stars = _success("x**2")
    fullwidth = _success("２（x＋１）")
    implicit = _success(" 2 ( x + 1 ) ")
    bars = _success("｜x｜")

    assert superscript.source_span == SourceSpan(1, 3)
    assert stars.source_span == SourceSpan(0, 4)
    assert fullwidth.source_span == SourceSpan(0, 6)
    assert implicit.source_span == SourceSpan(1, 12)
    assert bars.source_span == SourceSpan(0, 3)


@pytest.mark.parametrize("text", ["sin(x", "sin(x  ", "|x", "｜x"])
def test_unclosed_delimiters_use_the_original_eof_zero_width_span(text: str) -> None:
    result = _error(text)

    assert result.code is ErrorCode.DELIMITER_MISMATCH
    assert result.source_location == SourceSpan(len(text), len(text))


def test_extra_right_parenthesis_keeps_its_non_eof_source_span() -> None:
    result = _error("x+1)")
    assert result.source_location == SourceSpan(3, 4)


def test_repeated_failure_is_stable_and_a_later_valid_input_still_succeeds() -> None:
    first = _error("log(x,1)")
    second = _error("log(x,1)")

    assert first == second
    assert _success("sin(x)").free_variables == ("x",)


@pytest.mark.parametrize(
    "text",
    ["privateformula@marker", "x^x", "x^2+y^3=1"],
)
def test_technical_messages_do_not_echo_complete_private_input_or_stack_data(
    text: str,
) -> None:
    result = _error(text)

    assert result.technical_message is not None
    assert text not in result.technical_message
    assert "Traceback" not in result.technical_message
    assert ":\\" not in result.technical_message


def test_stage_7_result_is_an_intermediate_without_a_fabricated_item_id() -> None:
    result = _success("x")

    assert "item_id" not in {field.name for field in fields(result)}
    assert not isinstance(result, PlotItemSpec)


def test_standalone_validator_cannot_construct_the_production_result() -> None:
    result = validate_explicit_candidate(_candidate("x"))

    assert isinstance(result, ExplicitValidation)
    assert not isinstance(result, ValidatedExplicitExpression)


def test_public_validated_result_constructor_rejects_arbitrary_ast_and_version() -> None:
    candidate = _candidate("x")

    with pytest.raises(TypeError, match="validated stage 7 entry"):
        ValidatedExplicitExpression(
            expression=candidate.expression,
            normalized_input="x",
            normalized_span=candidate.normalized_span,
            source_span=candidate.source_span,
            source_form="expression",
            free_variables=(),
            limits_version="forged-v999",
        )


def test_production_validated_result_uses_a_checked_immutable_contract() -> None:
    result = _success("sin(x)")

    assert result.limits_version == DEFAULT_LIMITS.version
    assert isinstance(result.expression, FunctionCallNode)
    assert isinstance(result.expression.arguments, tuple)
    with pytest.raises(FrozenInstanceError):
        result.limits_version = "forged-v999"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.expression.arguments = ()  # type: ignore[misc]


def test_forged_parser_limits_version_is_a_structured_validation_error() -> None:
    candidate = _candidate("x")
    forged = replace(
        candidate,
        metrics=replace(candidate.metrics, limits_version="forged-v999"),
    )

    result = validate_explicit_candidate(forged)
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INVALID_AST
    assert result.recoverable is True


def _candidate(text: str) -> ExplicitFunctionCandidate:
    normalized = normalize_input(text)
    assert isinstance(normalized, NormalizedInput)
    tokens = tokenize(normalized)
    assert isinstance(tokens, tuple)
    split = split_equation(tokens)
    assert not isinstance(split, ErrorInfo)
    parsed = parse_input(split)
    assert isinstance(parsed, ParsedExpressionInput)
    candidate = classify_plot(parsed)
    assert isinstance(candidate, ExplicitFunctionCandidate)
    return candidate


def _unsafe_node(
    node_type: type[RestrictedExpression],
    span: SourceSpan,
    **attributes: object,
) -> RestrictedExpression:
    node = object.__new__(node_type)
    object.__setattr__(node, "normalized_span", span)
    object.__setattr__(node, "source_span", span)
    for name, value in attributes.items():
        object.__setattr__(node, name, value)
    return cast(RestrictedExpression, node)


class _MutablePayloadNumberNode(NumberNode):
    def __init__(
        self,
        normalized_span: SourceSpan,
        source_span: SourceSpan,
        lexeme: str,
        payload: dict[str, object],
    ) -> None:
        super().__init__(normalized_span, source_span, lexeme)
        object.__setattr__(self, "payload", payload)


class _SymbolNodeSubclass(SymbolNode):
    pass


class _ConstantNodeSubclass(ConstantNode):
    pass


class _UnaryOpNodeSubclass(UnaryOpNode):
    pass


class _BinaryOpNodeSubclass(BinaryOpNode):
    pass


class _FunctionCallNodeSubclass(FunctionCallNode):
    pass


def _mutable_number_node(span: SourceSpan) -> _MutablePayloadNumberNode:
    return _MutablePayloadNumberNode(span, span, "1", {"mutable": []})


@pytest.mark.parametrize(
    "expression_factory",
    [
        lambda span, _child: _mutable_number_node(span),
        lambda span, _child: _unsafe_node(
            UnaryOpNode,
            span,
            operator=UnaryOperator.NEGATIVE,
            operand=_mutable_number_node(span),
        ),
        lambda span, child: _unsafe_node(
            BinaryOpNode,
            span,
            operator=BinaryOperator.ADD,
            left=_mutable_number_node(span),
            right=child,
            implicit=False,
        ),
        lambda span, child: _unsafe_node(
            BinaryOpNode,
            span,
            operator=BinaryOperator.ADD,
            left=child,
            right=_mutable_number_node(span),
            implicit=False,
        ),
        lambda span, _child: _unsafe_node(
            FunctionCallNode,
            span,
            name="sin",
            arguments=(_mutable_number_node(span),),
        ),
    ],
    ids=("root", "unary-operand", "binary-left", "binary-right", "function-argument"),
)
def test_validator_rejects_mutable_number_node_subclasses_at_every_position(
    expression_factory: object,
) -> None:
    candidate = _candidate("x")
    expression = expression_factory(candidate.source_span, candidate.expression)  # type: ignore[operator]

    result = validate_explicit_candidate(replace(candidate, expression=expression))

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INVALID_AST


@pytest.mark.parametrize(
    "subclass_expression",
    [
        lambda span: _mutable_number_node(span),
        lambda span: _SymbolNodeSubclass(span, span, "x"),
        lambda span: _ConstantNodeSubclass(span, span, "pi"),
        lambda span: _UnaryOpNodeSubclass(
            span,
            span,
            UnaryOperator.NEGATIVE,
            NumberNode(span, span, "1"),
        ),
        lambda span: _BinaryOpNodeSubclass(
            span,
            span,
            BinaryOperator.ADD,
            NumberNode(span, span, "1"),
            NumberNode(span, span, "1"),
        ),
        lambda span: _FunctionCallNodeSubclass(
            span,
            span,
            "sin",
            (NumberNode(span, span, "1"),),
        ),
    ],
    ids=(
        "number",
        "symbol",
        "constant",
        "unary-operation",
        "binary-operation",
        "function-call",
    ),
)
def test_validator_rejects_all_restricted_ast_node_subclasses(
    subclass_expression: object,
) -> None:
    candidate = _candidate("x")
    expression = subclass_expression(candidate.source_span)  # type: ignore[operator]

    result = validate_explicit_candidate(replace(candidate, expression=expression))

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INVALID_AST


def test_validator_accepts_exact_number_node_and_public_entry_still_succeeds() -> None:
    candidate = _candidate("x")
    expression = NumberNode(candidate.source_span, candidate.source_span, "1")

    validation = validate_explicit_candidate(replace(candidate, expression=expression))

    assert isinstance(validation, ExplicitValidation)
    assert isinstance(analyze_explicit_function("sin(x)+2"), ValidatedExplicitExpression)


@pytest.mark.parametrize("kind", ["number", "symbol", "constant", "function"])
def test_validator_defensively_rejects_ast_names_outside_tokenizer_whitelists(
    kind: str,
) -> None:
    candidate = _candidate("x")
    span = candidate.source_span
    if kind == "number":
        expression = _unsafe_node(NumberNode, span, lexeme="1..2")
    elif kind == "symbol":
        expression = _unsafe_node(
            SymbolNode,
            span,
            name=cast(VariableName, "a"),
        )
    elif kind == "constant":
        expression = _unsafe_node(
            ConstantNode,
            span,
            name=cast(ConstantName, "tau"),
        )
    else:
        expression = _unsafe_node(
            FunctionCallNode,
            span,
            name=cast(FunctionName, "unknown"),
            arguments=(candidate.expression,),
        )
    invalid = replace(candidate, expression=expression)

    result = validate_explicit_candidate(invalid)
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INVALID_AST


def test_validator_defensively_rejects_unknown_child_nodes_without_crashing() -> None:
    candidate = _candidate("x")
    invalid_call = _unsafe_node(
        FunctionCallNode,
        candidate.source_span,
        name="sin",
        arguments=(cast(RestrictedExpression, object()),),
    )

    result = validate_explicit_candidate(replace(candidate, expression=invalid_call))
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INVALID_AST


def test_validated_result_factory_rechecks_ast_variables_and_limits_receipt() -> None:
    candidate = _candidate("x")
    invalid_call = _unsafe_node(
        FunctionCallNode,
        candidate.source_span,
        name="sin",
        arguments=(cast(RestrictedExpression, {"mutable": []}),),
    )
    contract = _issue_validated_expression_contract(
        parser_limits_version=DEFAULT_LIMITS.version,
        active_limits_version=DEFAULT_LIMITS.version,
    )

    with pytest.raises(TypeError):
        _create_validated_explicit_expression(
            expression=invalid_call,
            normalized_input="x",
            normalized_span=candidate.normalized_span,
            source_span=candidate.source_span,
            source_form="expression",
            free_variables=(),
            contract=contract,
        )
    with pytest.raises(ValueError, match="free_variables"):
        _create_validated_explicit_expression(
            expression=candidate.expression,
            normalized_input="x",
            normalized_span=candidate.normalized_span,
            source_span=candidate.source_span,
            source_form="expression",
            free_variables=(),
            contract=contract,
        )
    with pytest.raises(ValueError, match="must match"):
        _issue_validated_expression_contract(
            parser_limits_version="forged-v999",
            active_limits_version=DEFAULT_LIMITS.version,
        )
