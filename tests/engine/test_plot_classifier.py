"""Narrow M1 classification tests without algebraic solving or rearrangement."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, is_dataclass
import inspect
from pathlib import Path
import typing

import pytest

import math_drawing_assistant.engine as engine_package
import math_drawing_assistant.engine.plot_classifier as plot_classifier_module
from math_drawing_assistant.engine import (
    ExplicitFunctionCandidate,
    NormalizedInput,
    ParsedEquationInput,
    ParsedExpressionInput,
    classify_plot,
    normalize_input,
    parse_input,
    split_equation,
    tokenize,
)
from math_drawing_assistant.engine.plot_classifier import (
    EquationCandidate,
    LegacyEquationRejectionReason,
    classify_plot_route,
)
from math_drawing_assistant.models import (
    BinaryOpNode,
    ConstantNode,
    ErrorCode,
    ErrorInfo,
    FunctionCallNode,
    NumberNode,
    PlotKind,
    SourceSpan,
    SymbolNode,
)


def _parsed(text: str) -> ParsedExpressionInput | ParsedEquationInput:
    normalized = normalize_input(text)
    assert isinstance(normalized, NormalizedInput), normalized
    tokens = tokenize(normalized)
    assert isinstance(tokens, tuple), tokens
    split = split_equation(tokens)
    assert not isinstance(split, ErrorInfo), split
    parsed = parse_input(split)
    assert isinstance(parsed, (ParsedExpressionInput, ParsedEquationInput)), parsed
    return parsed


@pytest.mark.parametrize("text", ["x", "x^2", "sin(x)", "2", "pi"])
def test_expression_inputs_are_explicit_function_candidates(text: str) -> None:
    result = classify_plot(_parsed(text))

    assert isinstance(result, ExplicitFunctionCandidate)
    assert result.plot_kind is PlotKind.EXPLICIT_FUNCTION
    assert result.source_form == "expression"


@pytest.mark.parametrize(
    ("text", "source_form", "node_type"),
    [
        ("y=x", "y_equals", SymbolNode),
        ("x=y", "equals_y", SymbolNode),
        ("y=x^2", "y_equals", BinaryOpNode),
        ("x^2=y", "equals_y", BinaryOpNode),
        ("y=2", "y_equals", NumberNode),
        ("2=y", "equals_y", NumberNode),
    ],
)
def test_only_direct_isolated_y_equations_are_swapped_or_selected(
    text: str,
    source_form: str,
    node_type: type[object],
) -> None:
    result = classify_plot(_parsed(text))

    assert isinstance(result, ExplicitFunctionCandidate)
    assert result.source_form == source_form
    assert isinstance(result.expression, node_type)


@pytest.mark.parametrize("text", ["y=y", "y=x+y", "x+y=y"])
def test_direct_y_forms_reject_y_on_the_expression_side(text: str) -> None:
    result = classify_plot(_parsed(text))

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED
    assert result.source_location is not None


@pytest.mark.parametrize(
    "text",
    [
        "y+1=x+2",
        "x+y=1",
        "x=2",
        "x^2+y^2=25",
        "y^2=8*x",
        "x^2+y^3=1",
        "y^2=x^3",
        "x^3+y^3=1",
        "sin(x)+y=1",
    ],
)
def test_non_direct_equations_get_one_neutral_stage_error(text: str) -> None:
    result = classify_plot(_parsed(text))

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.UNSUPPORTED_EQUATION
    assert "当前不支持该方程形式" in result.user_message
    assert "一般一次方程" not in result.user_message
    assert "圆锥曲线" not in result.user_message
    assert result.source_location == SourceSpan(0, len(text))
    assert result.recoverable is True


def test_classifier_does_not_mutate_or_rebuild_the_selected_ast() -> None:
    parsed = _parsed("x^2=y")
    assert isinstance(parsed, ParsedEquationInput)

    result = classify_plot(parsed)

    assert isinstance(result, ExplicitFunctionCandidate)
    assert result.expression is parsed.left
    assert result.metrics is parsed.metrics


_LEGACY_DIRECT_ORACLE = (
    ("x", "expression", "expression", SymbolNode, SourceSpan(0, 1)),
    ("x^2", "expression", "expression", BinaryOpNode, SourceSpan(0, 3)),
    (
        "sin(x)",
        "expression",
        "expression",
        FunctionCallNode,
        SourceSpan(0, 6),
    ),
    ("2", "expression", "expression", NumberNode, SourceSpan(0, 1)),
    ("pi", "expression", "expression", ConstantNode, SourceSpan(0, 2)),
    ("x+y", "expression", "expression", BinaryOpNode, SourceSpan(0, 3)),
    ("y=x", "y_equals", "right", SymbolNode, SourceSpan(2, 3)),
    ("x=y", "equals_y", "left", SymbolNode, SourceSpan(0, 1)),
    ("y=x^2", "y_equals", "right", BinaryOpNode, SourceSpan(2, 5)),
    ("x^2=y", "equals_y", "left", BinaryOpNode, SourceSpan(0, 3)),
    ("y=2", "y_equals", "right", NumberNode, SourceSpan(2, 3)),
    ("2=y", "equals_y", "left", NumberNode, SourceSpan(0, 1)),
    (
        "y=sin(x)",
        "y_equals",
        "right",
        FunctionCallNode,
        SourceSpan(2, 8),
    ),
    (
        "sin(x)=y",
        "equals_y",
        "left",
        FunctionCallNode,
        SourceSpan(0, 6),
    ),
)


@pytest.mark.parametrize(
    ("text", "source_form", "expression_field", "node_type", "span"),
    _LEGACY_DIRECT_ORACLE,
)
def test_legacy_direct_candidate_frozen_oracle(
    text: str,
    source_form: str,
    expression_field: str,
    node_type: type[object],
    span: SourceSpan,
) -> None:
    parsed = _parsed(text)
    result = classify_plot(parsed)

    assert type(result) is ExplicitFunctionCandidate
    assert result.plot_kind is PlotKind.EXPLICIT_FUNCTION
    assert result.source_form == source_form
    assert result.expression is getattr(parsed, expression_field)
    assert type(result.expression) is node_type
    assert result.normalized_span == span
    assert result.source_span == span
    assert result.metrics is parsed.metrics


_LEGACY_Y_PRESENT_ORACLE = (
    ("y=y", SourceSpan(2, 3)),
    ("y=x+y", SourceSpan(4, 5)),
    ("x+y=y", SourceSpan(2, 3)),
    ("y=sin(y)", SourceSpan(6, 7)),
    ("sin(y)=y", SourceSpan(4, 5)),
    ("y=y+y", SourceSpan(2, 3)),
    ("y=sin(y)+y", SourceSpan(6, 7)),
    (" y = x + y ", SourceSpan(9, 10)),
)


@pytest.mark.parametrize(("text", "source_location"), _LEGACY_Y_PRESENT_ORACLE)
def test_legacy_y_present_error_frozen_oracle(
    text: str,
    source_location: SourceSpan,
) -> None:
    result = classify_plot(_parsed(text))

    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED
    assert result.user_message == "显函数右侧只能使用自变量 x，不能再次使用 y。"
    assert result.technical_message == "y appears outside the direct isolated equation side"
    assert result.item_id is None
    assert result.field_name == "input_text"
    assert result.source_location == source_location
    assert result.recoverable is True


_LEGACY_OTHER_ORACLE = (
    ("x=2", SourceSpan(0, 3)),
    ("y+1=x+2", SourceSpan(0, 7)),
    ("x+y=1", SourceSpan(0, 5)),
    ("2*y=x+2*y", SourceSpan(0, 9)),
    ("x^2+y^2=25", SourceSpan(0, 10)),
    ("x*y=1", SourceSpan(0, 5)),
    ("1/x+y=1", SourceSpan(0, 7)),
    ("0=0", SourceSpan(0, 3)),
    ("1=1", SourceSpan(0, 3)),
    ("x^3+y^2=1", SourceSpan(0, 9)),
    ("y^2=8*x", SourceSpan(0, 7)),
    ("x^2+y^3=1", SourceSpan(0, 9)),
    ("y^2=x^3", SourceSpan(0, 7)),
    ("x^3+y^3=1", SourceSpan(0, 9)),
    ("sin(x)+y=1", SourceSpan(0, 10)),
    (" x + y = 1 ", SourceSpan(1, 10)),
)


@pytest.mark.parametrize(("text", "source_location"), _LEGACY_OTHER_ORACLE)
def test_legacy_other_error_frozen_oracle(
    text: str,
    source_location: SourceSpan,
) -> None:
    result = classify_plot(_parsed(text))

    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.UNSUPPORTED_EQUATION
    assert result.user_message == (
        "当前不支持该方程形式，请暂时改写为 y=... 的显函数形式。"
    )
    assert result.technical_message == (
        "equation is outside the stage 7 direct-y explicit forms"
    )
    assert result.item_id is None
    assert result.field_name == "input_text"
    assert result.source_location == source_location
    assert result.recoverable is True


def test_new_module_names_and_enum_contract_are_exact() -> None:
    assert plot_classifier_module.__all__ == [
        "ExplicitFunctionCandidate",
        "classify_plot",
        "LegacyEquationRejectionReason",
        "EquationCandidate",
        "classify_plot_route",
    ]
    assert list(LegacyEquationRejectionReason) == [
        LegacyEquationRejectionReason.Y_PRESENT_ON_EXPLICIT_SIDE,
        LegacyEquationRejectionReason.OTHER_NON_DIRECT_EQUATION,
    ]
    assert [member.name for member in LegacyEquationRejectionReason] == [
        "Y_PRESENT_ON_EXPLICIT_SIDE",
        "OTHER_NON_DIRECT_EQUATION",
    ]
    assert [member.value for member in LegacyEquationRejectionReason] == [
        "y_present_on_explicit_side",
        "other_non_direct_equation",
    ]
    assert not hasattr(engine_package, "LegacyEquationRejectionReason")
    assert not hasattr(engine_package, "EquationCandidate")
    assert not hasattr(engine_package, "classify_plot_route")


def test_equation_candidate_is_frozen_slotted_hashable_and_keeps_identity() -> None:
    parsed = _parsed("x=2")
    assert isinstance(parsed, ParsedEquationInput)
    candidate = classify_plot_route(parsed)

    assert type(candidate) is EquationCandidate
    assert is_dataclass(EquationCandidate)
    assert EquationCandidate.__dataclass_params__.frozen is True
    assert "__dict__" not in EquationCandidate.__dict__
    assert not hasattr(candidate, "__dict__")
    assert tuple(field.name for field in fields(EquationCandidate)) == (
        "parsed_input",
        "legacy_rejection_reason",
        "legacy_normalized_span",
        "legacy_source_span",
    )
    assert candidate.parsed_input is parsed
    assert candidate.parsed_input.left is parsed.left
    assert candidate.parsed_input.right is parsed.right
    assert candidate.parsed_input.metrics is parsed.metrics
    assert hash(candidate) == hash(candidate)
    with pytest.raises(FrozenInstanceError):
        candidate.parsed_input = parsed  # type: ignore[misc]


class _SpanLike:
    start = 0
    end = 1


class _SourceSpanSubclass(SourceSpan):
    pass


@pytest.mark.parametrize("invalid_parsed", [None, object(), "x"])
def test_equation_candidate_rejects_non_equation_parser_products(
    invalid_parsed: object,
) -> None:
    with pytest.raises(TypeError):
        EquationCandidate(
            parsed_input=invalid_parsed,  # type: ignore[arg-type]
            legacy_rejection_reason=(
                LegacyEquationRejectionReason.OTHER_NON_DIRECT_EQUATION
            ),
            legacy_normalized_span=SourceSpan(0, 1),
            legacy_source_span=SourceSpan(0, 1),
        )


def test_equation_candidate_rejects_parsed_expression_input() -> None:
    parsed = _parsed("x")
    assert isinstance(parsed, ParsedExpressionInput)
    with pytest.raises(TypeError):
        EquationCandidate(
            parsed_input=parsed,  # type: ignore[arg-type]
            legacy_rejection_reason=(
                LegacyEquationRejectionReason.OTHER_NON_DIRECT_EQUATION
            ),
            legacy_normalized_span=SourceSpan(0, 1),
            legacy_source_span=SourceSpan(0, 1),
        )


@pytest.mark.parametrize("invalid_reason", [None, "other_non_direct_equation", object()])
def test_equation_candidate_requires_exact_reason(invalid_reason: object) -> None:
    parsed = _parsed("x=2")
    assert isinstance(parsed, ParsedEquationInput)
    with pytest.raises(TypeError):
        EquationCandidate(
            parsed_input=parsed,
            legacy_rejection_reason=invalid_reason,  # type: ignore[arg-type]
            legacy_normalized_span=SourceSpan(0, 3),
            legacy_source_span=SourceSpan(0, 3),
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_span"),
    [
        ("legacy_normalized_span", None),
        ("legacy_normalized_span", _SpanLike()),
        ("legacy_normalized_span", _SourceSpanSubclass(0, 3)),
        ("legacy_source_span", None),
        ("legacy_source_span", _SpanLike()),
        ("legacy_source_span", _SourceSpanSubclass(0, 3)),
    ],
)
def test_equation_candidate_requires_exact_source_spans(
    field_name: str,
    invalid_span: object,
) -> None:
    parsed = _parsed("x=2")
    assert isinstance(parsed, ParsedEquationInput)
    values = {
        "parsed_input": parsed,
        "legacy_rejection_reason": (
            LegacyEquationRejectionReason.OTHER_NON_DIRECT_EQUATION
        ),
        "legacy_normalized_span": SourceSpan(0, 3),
        "legacy_source_span": SourceSpan(0, 3),
    }
    values[field_name] = invalid_span
    with pytest.raises(TypeError):
        EquationCandidate(**values)  # type: ignore[arg-type]


def test_equation_candidate_contains_no_later_stage_fields() -> None:
    assert {field.name for field in fields(EquationCandidate)}.isdisjoint(
        {
            "error",
            "code",
            "item_id",
            "requested_plot_kind",
            "limits",
            "seal",
            "receipt",
            "coefficients",
            "geometry",
            "plot_kind",
            "spec",
        },
    )


@pytest.mark.parametrize(
    ("text", "source_form", "expression_field", "node_type", "span"),
    _LEGACY_DIRECT_ORACLE,
)
def test_route_direct_candidate_matches_the_independent_frozen_oracle(
    text: str,
    source_form: str,
    expression_field: str,
    node_type: type[object],
    span: SourceSpan,
) -> None:
    parsed = _parsed(text)
    result = classify_plot_route(parsed)

    assert type(result) is ExplicitFunctionCandidate
    assert result.plot_kind is PlotKind.EXPLICIT_FUNCTION
    assert result.source_form == source_form
    assert result.expression is getattr(parsed, expression_field)
    assert type(result.expression) is node_type
    assert result.normalized_span == span
    assert result.source_span == span
    assert result.metrics is parsed.metrics


_Y_PRESENT_ROUTE_ORACLE = (
    ("y=y", SourceSpan(2, 3), SourceSpan(2, 3)),
    ("y=x+y", SourceSpan(4, 5), SourceSpan(4, 5)),
    ("x+y=y", SourceSpan(2, 3), SourceSpan(2, 3)),
    ("y=sin(y)", SourceSpan(6, 7), SourceSpan(6, 7)),
    ("sin(y)=y", SourceSpan(4, 5), SourceSpan(4, 5)),
    ("y=y+y", SourceSpan(2, 3), SourceSpan(2, 3)),
    ("y=sin(y)+y", SourceSpan(6, 7), SourceSpan(6, 7)),
    (" y = x + y ", SourceSpan(4, 5), SourceSpan(9, 10)),
)


@pytest.mark.parametrize(
    ("text", "normalized_span", "source_span"),
    _Y_PRESENT_ROUTE_ORACLE,
)
def test_route_y_present_uses_first_y_node_and_exact_spans(
    text: str,
    normalized_span: SourceSpan,
    source_span: SourceSpan,
) -> None:
    parsed = _parsed(text)
    assert isinstance(parsed, ParsedEquationInput)
    result = classify_plot_route(parsed)

    assert type(result) is EquationCandidate
    assert result.parsed_input is parsed
    assert result.legacy_rejection_reason is (
        LegacyEquationRejectionReason.Y_PRESENT_ON_EXPLICIT_SIDE
    )
    assert result.legacy_normalized_span == normalized_span
    assert result.legacy_source_span == source_span


_OTHER_ROUTE_ORACLE = (
    ("x=2", SourceSpan(0, 3), SourceSpan(0, 3)),
    ("y+1=x+2", SourceSpan(0, 7), SourceSpan(0, 7)),
    ("x+y=1", SourceSpan(0, 5), SourceSpan(0, 5)),
    ("2*y=x+2*y", SourceSpan(0, 9), SourceSpan(0, 9)),
    ("x^2+y^2=25", SourceSpan(0, 10), SourceSpan(0, 10)),
    ("x*y=1", SourceSpan(0, 5), SourceSpan(0, 5)),
    ("1/x+y=1", SourceSpan(0, 7), SourceSpan(0, 7)),
    ("0=0", SourceSpan(0, 3), SourceSpan(0, 3)),
    ("1=1", SourceSpan(0, 3), SourceSpan(0, 3)),
    ("x^3+y^2=1", SourceSpan(0, 9), SourceSpan(0, 9)),
    ("y^2=8*x", SourceSpan(0, 7), SourceSpan(0, 7)),
    ("x^2+y^3=1", SourceSpan(0, 9), SourceSpan(0, 9)),
    ("y^2=x^3", SourceSpan(0, 7), SourceSpan(0, 7)),
    ("x^3+y^3=1", SourceSpan(0, 9), SourceSpan(0, 9)),
    ("sin(x)+y=1", SourceSpan(0, 10), SourceSpan(0, 10)),
    (" x + y = 1 ", SourceSpan(0, 5), SourceSpan(1, 10)),
)


@pytest.mark.parametrize(
    ("text", "normalized_span", "source_span"),
    _OTHER_ROUTE_ORACLE,
)
def test_route_all_safe_non_direct_equations_are_structural_candidates(
    text: str,
    normalized_span: SourceSpan,
    source_span: SourceSpan,
) -> None:
    parsed = _parsed(text)
    assert isinstance(parsed, ParsedEquationInput)
    result = classify_plot_route(parsed)

    assert type(result) is EquationCandidate
    assert result.parsed_input is parsed
    assert result.legacy_rejection_reason is (
        LegacyEquationRejectionReason.OTHER_NON_DIRECT_EQUATION
    )
    assert result.legacy_normalized_span == normalized_span
    assert result.legacy_source_span == source_span
    assert not isinstance(result, ErrorInfo)


@pytest.mark.parametrize("entry", [classify_plot, classify_plot_route])
@pytest.mark.parametrize("invalid", [None, object(), "x", SourceSpan(0, 1)])
def test_both_classifier_entries_keep_the_programmer_type_boundary(
    entry: object,
    invalid: object,
) -> None:
    with pytest.raises(
        TypeError,
        match=r"^parsed_input must be a parsed expression or equation\.$",
    ):
        entry(invalid)  # type: ignore[operator]


class _ParsedExpressionInputSubclass(ParsedExpressionInput):
    pass


class _ParsedEquationInputSubclass(ParsedEquationInput):
    pass


def test_benign_parser_product_subclasses_keep_isinstance_compatibility() -> None:
    expression = _parsed("x")
    assert isinstance(expression, ParsedExpressionInput)
    expression_subclass = _ParsedExpressionInputSubclass(
        expression.expression,
        expression.normalized_span,
        expression.source_span,
        expression.metrics,
    )
    assert type(classify_plot_route(expression_subclass)) is ExplicitFunctionCandidate
    assert type(classify_plot(expression_subclass)) is ExplicitFunctionCandidate

    equation = _parsed("x=2")
    assert isinstance(equation, ParsedEquationInput)
    equation_subclass = _ParsedEquationInputSubclass(
        equation.left,
        equation.right,
        equation.left_normalized_span,
        equation.right_normalized_span,
        equation.left_source_span,
        equation.right_source_span,
        equation.metrics,
    )
    routed = classify_plot_route(equation_subclass)
    assert type(routed) is EquationCandidate
    assert routed.parsed_input is equation_subclass
    assert type(classify_plot(equation_subclass)) is ErrorInfo


def test_classifier_signatures_annotations_and_resolved_hints_are_frozen() -> None:
    legacy_signature = inspect.signature(classify_plot)
    assert str(legacy_signature) == (
        "(parsed_input: 'ParsedInput') -> "
        "'ExplicitFunctionCandidate | ErrorInfo'"
    )
    assert classify_plot.__annotations__ == {
        "parsed_input": "ParsedInput",
        "return": "ExplicitFunctionCandidate | ErrorInfo",
    }
    legacy_parameter = tuple(legacy_signature.parameters.values())
    assert len(legacy_parameter) == 1
    assert legacy_parameter[0].name == "parsed_input"
    assert legacy_parameter[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert legacy_parameter[0].default is inspect.Parameter.empty
    assert legacy_parameter[0].annotation == "ParsedInput"
    assert legacy_signature.return_annotation == "ExplicitFunctionCandidate | ErrorInfo"
    assert typing.get_type_hints(classify_plot) == {
        "parsed_input": ParsedExpressionInput | ParsedEquationInput,
        "return": ExplicitFunctionCandidate | ErrorInfo,
    }

    route_signature = inspect.signature(classify_plot_route)
    assert str(route_signature) == (
        "(parsed_input: 'ParsedInput') -> "
        "'ExplicitFunctionCandidate | EquationCandidate'"
    )
    assert classify_plot_route.__annotations__ == {
        "parsed_input": "ParsedInput",
        "return": "ExplicitFunctionCandidate | EquationCandidate",
    }
    route_parameter = tuple(route_signature.parameters.values())
    assert len(route_parameter) == 1
    assert route_parameter[0].name == "parsed_input"
    assert route_parameter[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert route_parameter[0].default is inspect.Parameter.empty
    assert route_parameter[0].annotation == "ParsedInput"
    assert route_signature.return_annotation == (
        "ExplicitFunctionCandidate | EquationCandidate"
    )
    assert typing.get_type_hints(classify_plot_route) == {
        "parsed_input": ParsedExpressionInput | ParsedEquationInput,
        "return": ExplicitFunctionCandidate | EquationCandidate,
    }


def _forbidden_route_call(*args: object, **kwargs: object) -> object:
    raise AssertionError("legacy fallback was called by classify_plot_route")


def test_route_behavior_does_not_call_legacy_wrapper_or_error_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plot_classifier_module, "classify_plot", _forbidden_route_call)
    monkeypatch.setattr(plot_classifier_module, "_error", _forbidden_route_call)
    monkeypatch.setattr(plot_classifier_module, "_y_error", _forbidden_route_call)

    for text, *_ in _LEGACY_DIRECT_ORACLE:
        assert type(plot_classifier_module.classify_plot_route(_parsed(text))) is (
            ExplicitFunctionCandidate
        )
    for text, *_ in _Y_PRESENT_ROUTE_ORACLE:
        result = plot_classifier_module.classify_plot_route(_parsed(text))
        assert type(result) is EquationCandidate
        assert result.legacy_rejection_reason is (
            LegacyEquationRejectionReason.Y_PRESENT_ON_EXPLICIT_SIDE
        )
    for text, *_ in _OTHER_ROUTE_ORACLE:
        result = plot_classifier_module.classify_plot_route(_parsed(text))
        assert type(result) is EquationCandidate
        assert result.legacy_rejection_reason is (
            LegacyEquationRejectionReason.OTHER_NON_DIRECT_EQUATION
        )


def _plot_classifier_function_nodes() -> dict[str, ast.FunctionDef]:
    source_path = Path(inspect.getsourcefile(classify_plot_route) or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and isinstance(node, ast.FunctionDef)
    }


def _route_reachable_private_helpers() -> tuple[ast.FunctionDef, ...]:
    functions = _plot_classifier_function_nodes()
    pending = ["classify_plot_route"]
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        for call in (node for node in ast.walk(functions[name]) if isinstance(node, ast.Call)):
            if isinstance(call.func, ast.Name):
                called = call.func.id
                if called.startswith("_") and called in functions and called not in visited:
                    pending.append(called)
    return tuple(functions[name] for name in sorted(visited))


def _loaded_names(nodes: tuple[ast.AST, ...]) -> set[str]:
    names: set[str] = set()
    for root in nodes:
        for node in ast.walk(root):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
    return names


def test_route_direct_body_has_no_legacy_fallback_reference() -> None:
    route_node = _plot_classifier_function_nodes()["classify_plot_route"]
    body_names = _loaded_names(tuple(route_node.body))
    assert body_names.isdisjoint(
        {
            "classify_plot",
            "ErrorInfo",
            "ErrorCode",
            "recoverable",
            "_error",
            "_y_error",
        },
    )


def test_route_reachable_helper_subgraph_has_no_legacy_fallback_or_bypass() -> None:
    reachable = _route_reachable_private_helpers()
    assert {node.name for node in reachable} == {
        "classify_plot_route",
        "_first_symbol_node",
        "_is_symbol",
    }
    names = _loaded_names(tuple(reachable))
    assert names.isdisjoint(
        {
            "classify_plot",
            "ErrorInfo",
            "ErrorCode",
            "recoverable",
            "_error",
            "_y_error",
            "getattr",
            "globals",
            "locals",
            "vars",
            "eval",
            "exec",
        },
    )
    forbidden_messages = {
        "显函数右侧只能使用自变量 x，不能再次使用 y。",
        "y appears outside the direct isolated equation side",
        "当前不支持该方程形式，请暂时改写为 y=... 的显函数形式。",
        "equation is outside the stage 7 direct-y explicit forms",
    }
    constants = {
        node.value
        for root in reachable
        for node in ast.walk(root)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert constants.isdisjoint(forbidden_messages)


def test_legacy_wrapper_calls_route_exactly_once_per_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_route = plot_classifier_module.classify_plot_route
    calls: list[object] = []

    def spy(parsed_input: object) -> object:
        calls.append(parsed_input)
        return original_route(parsed_input)  # type: ignore[arg-type]

    monkeypatch.setattr(plot_classifier_module, "classify_plot_route", spy)
    for text in ("x", "y=x+y", "x=2"):
        parsed = _parsed(text)
        before = len(calls)
        classify_plot(parsed)
        assert calls[before:] == [parsed]


def test_route_module_has_no_later_stage_imports_or_calls() -> None:
    source_path = Path(inspect.getsourcefile(classify_plot_route) or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert imported_modules.isdisjoint(
        {
            "fractions",
            "decimal",
            "numpy",
            "matplotlib",
            "sympy",
            "PySide6",
            "math_drawing_assistant.engine.equation_polynomial",
            "math_drawing_assistant.engine.equation_classifier",
            "math_drawing_assistant.engine.equation_validator",
            "math_drawing_assistant.engine.plot_analyzer",
            "math_drawing_assistant.engine.spec_builder",
        },
    )
    loaded = _loaded_names(tuple(tree.body))
    assert loaded.isdisjoint(
        {
            "PlotItemRequest",
            "ApplicationLimits",
            "ValidatedEquationInput",
            "PrimitiveEquationCoefficients",
            "EquationGeometryResult",
            "LineSpec",
            "CircleSpec",
            "EllipseSpec",
            "HyperbolaSpec",
            "ParabolaSpec",
            "Fraction",
            "Decimal",
            "requested_plot_kind",
            "item_id",
            "canonicalize_equation",
            "classify_equation_geometry",
            "solve",
            "expand",
            "simplify",
            "factor",
        },
    )
