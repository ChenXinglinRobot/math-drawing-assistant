"""Fixed-seed robustness and architecture checks for the stage 6 front end."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from inspect import Signature, signature
from pathlib import Path
import random

import pytest

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    EquationInput,
    ExpressionInput,
    NormalizedInput,
    Token,
    normalize_input,
    split_equation,
    tokenize,
)
from math_drawing_assistant.models import ErrorInfo


def _run_frontend(text: str) -> ExpressionInput | EquationInput | ErrorInfo:
    normalized = normalize_input(text)
    if isinstance(normalized, ErrorInfo):
        return normalized
    tokens = tokenize(normalized)
    if isinstance(tokens, ErrorInfo):
        return tokens
    return split_equation(tokens)


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "=x",
        "x=",
        "x=y=1",
        "x>1",
        "x<=1",
        "x≤1",
        "x≠1",
        "x\ny",
        "x;y",
        "unknown(x)",
        "sin(x)@tail",
        "x+",
        "x^",
        "sin(",
        ")x",
        "|x",
    ],
)
def test_required_invalid_inputs_return_structured_errors(text: str) -> None:
    assert isinstance(_run_frontend(text), ErrorInfo)


def test_character_limit_bounds_work_before_any_later_stage() -> None:
    at_limit = " " * (DEFAULT_LIMITS.max_input_characters - 1) + "x"
    over_limit = at_limit + "x"

    assert isinstance(_run_frontend(at_limit), ExpressionInput)
    assert isinstance(_run_frontend(over_limit), ErrorInfo)


def test_fixed_seed_mixed_inputs_never_leak_uncaught_exceptions_or_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    generator = random.Random(20260721)
    alphabet = (
        "xy0123456789+-*/^(),|= "
        "Ａｘ１２３（）＝＋－＊／，｜"
        "−×·÷²³≤≥≠"
        "\n\r\t;:@[]{}_'\""
        "abcdefghijklmnopqrstuvwxyz"
    )

    samples = [
        "".join(generator.choice(alphabet) for _ in range(generator.randrange(0, 180)))
        for _ in range(500)
    ]
    samples.extend(
        [
            "9" * (DEFAULT_LIMITS.max_numeric_digits + 1),
            "(" * (DEFAULT_LIMITS.max_nesting_depth + 1) + "x",
            "x=" * (DEFAULT_LIMITS.max_tokens + 1),
            "x" * (DEFAULT_LIMITS.max_input_characters + 1),
        ],
    )

    for sample in samples:
        result = _run_frontend(sample)
        assert isinstance(result, (ExpressionInput, EquationInput, ErrorInfo))
        if isinstance(result, ErrorInfo) and result.technical_message is not None:
            if len(sample) > 16:
                assert sample not in result.technical_message

    assert not caplog.records


def test_stage_6_modules_have_no_forbidden_dependencies_or_execution_calls() -> None:
    root = Path(__file__).parents[2] / "math_drawing_assistant" / "engine"
    module_paths = tuple(root.glob("*.py"))
    assert module_paths

    stage_6_module_paths = tuple(
        root / module_name
        for module_name in (
            "normalizer.py",
            "source_map.py",
            "tokenizer.py",
            "equation_splitter.py",
        )
    )
    assert all(path.is_file() for path in stage_6_module_paths)

    forbidden_imports = ("PySide6", "sympy", "numpy", "matplotlib")
    forbidden_calls = ("eval(", "exec(", "sympify(", "parse_expr(", "solve(")
    for path in stage_6_module_paths:
        source = path.read_text(encoding="utf-8")
        for marker in forbidden_imports:
            assert marker not in source

    for path in module_paths:
        source = path.read_text(encoding="utf-8")
        for marker in forbidden_calls:
            assert marker not in source


def test_public_stage_6_data_contracts_are_frozen_slotted_and_typed() -> None:
    examples = (
        normalize_input("x"),
        _run_frontend("x"),
        _run_frontend("x=y"),
    )
    normalized = examples[0]
    assert isinstance(normalized, NormalizedInput)
    tokens = tokenize(normalized)
    assert isinstance(tokens, tuple)

    contract_types = {
        type(normalized),
        type(normalized.source_map),
        Token,
        type(examples[1]),
        type(examples[2]),
    }
    for contract_type in contract_types:
        assert is_dataclass(contract_type)
        assert contract_type.__dataclass_params__.frozen is True
        assert "__dict__" not in contract_type.__dict__
        for field in fields(contract_type):
            assert field.type is not None

    for public_function in (normalize_input, tokenize, split_equation):
        function_signature = signature(public_function)
        assert function_signature.return_annotation is not Signature.empty
        for parameter in function_signature.parameters.values():
            assert parameter.annotation is not Signature.empty


def test_frontend_outputs_do_not_construct_ast_or_execute_math() -> None:
    result = _run_frontend("2(x+1)=y")

    assert isinstance(result, EquationInput)
    assert tuple(token.lexeme for token in result.left_tokens) == (
        "2",
        "(",
        "x",
        "+",
        "1",
        ")",
    )
    assert tuple(token.lexeme for token in result.right_tokens) == ("y",)
