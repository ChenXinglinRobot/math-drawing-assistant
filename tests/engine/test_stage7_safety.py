"""Fixed-seed robustness and production-boundary checks for stage 7."""

from __future__ import annotations

from pathlib import Path
import random
import re

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import analyze_explicit_function
from math_drawing_assistant.models import ErrorInfo, ValidatedExplicitExpression


MUTATION_SEED = 20260721
MUTATION_SAMPLE_COUNT = 90
MIXED_FUZZ_SEED = 20260722
MIXED_FUZZ_SAMPLE_COUNT = 600


def _mutation_samples() -> tuple[str, ...]:
    generator = random.Random(MUTATION_SEED)
    rules = (
        lambda: "sin(x" + " " * generator.randrange(0, 3),
        lambda: "x" + ")" * generator.randrange(1, 4),
        lambda: "log(x,2," + str(generator.randrange(2, 10)) + ")",
        lambda: "x" + generator.choice(("@tail", ";tail", "[0]")),
        lambda: generator.choice(("unknown(x)", "a+x", "log(x,a)")),
        lambda: generator.choice(("2pi", "2sin(x)", "x(x+1)")),
        lambda: (
            "(" * (DEFAULT_LIMITS.max_nesting_depth + 1)
            + "x"
            + ")" * (DEFAULT_LIMITS.max_nesting_depth + 1)
        ),
        lambda: generator.choice(("sin(,x)", "log(,10)", "sqrt()")),
        lambda: generator.choice(("x,,1", "sin(x,,1)", "log(x,,2)")),
        lambda: generator.choice(("||x||", "|x", "|x+|")),
    )
    return tuple(rules[index % len(rules)]() for index in range(MUTATION_SAMPLE_COUNT))


def _mixed_samples() -> tuple[str, ...]:
    generator = random.Random(MIXED_FUZZ_SEED)
    valid_seeds = (
        "x",
        "x^2",
        "2x",
        "sin(x)",
        "log(x,2)",
        "|x|",
        "y=x",
        "x=y",
        "pi",
        "2^x",
    )
    samples = [valid_seeds[index % len(valid_seeds)] for index in range(50)]
    alphabet = (
        "xy0123456789+-*/^(),|= "
        "Ａｘ１２３（）＝＋－＊／，｜"
        "−×·÷²³≤≥≠"
        "\n\r\t;:@[]{}_'\""
        "abcdefghijklmnopqrstuvwxyz"
    )
    samples.extend(
        "".join(generator.choice(alphabet) for _ in range(generator.randrange(0, 96)))
        for _ in range(MIXED_FUZZ_SAMPLE_COUNT - len(samples))
    )
    return tuple(samples)


def test_guaranteed_invalid_mutations_are_stable_structured_rejections() -> None:
    samples = _mutation_samples()
    assert len(samples) == MUTATION_SAMPLE_COUNT
    assert len(set(samples)) == 31

    for sample in samples:
        first = analyze_explicit_function(sample)
        second = analyze_explicit_function(sample)
        assert isinstance(first, ErrorInfo), sample
        assert second == first
        assert first.recoverable is True


def test_bounded_mixed_fuzz_is_deterministic_and_never_leaks_an_exception() -> None:
    samples = _mixed_samples()
    assert len(samples) == MIXED_FUZZ_SAMPLE_COUNT
    assert len(set(samples)) == 556
    success_count = 0
    rejection_count = 0

    for sample in samples:
        first = analyze_explicit_function(sample)
        second = analyze_explicit_function(sample)
        assert second == first
        if isinstance(first, ValidatedExplicitExpression):
            success_count += 1
        else:
            assert isinstance(first, ErrorInfo)
            rejection_count += 1

    assert success_count >= 50
    assert success_count + rejection_count == MIXED_FUZZ_SAMPLE_COUNT
    assert isinstance(analyze_explicit_function("sin(x)"), ValidatedExplicitExpression)


def test_engine_has_no_forbidden_execution_or_general_math_parser_calls() -> None:
    engine_root = Path(__file__).parents[2] / "math_drawing_assistant" / "engine"
    engine_paths = tuple(engine_root.glob("*.py"))
    assert engine_paths
    assert "numeric_executor.py" in {path.name for path in engine_paths}

    stage_6_and_7_module_paths = tuple(
        engine_root / module_name
        for module_name in (
            "normalizer.py",
            "source_map.py",
            "tokenizer.py",
            "equation_splitter.py",
            "parser.py",
            "plot_classifier.py",
            "validators.py",
        )
    )
    assert all(path.is_file() for path in stage_6_and_7_module_paths)

    call_pattern = re.compile(
        r"\b(?:eval|exec|compile|ast\s*\.\s*(?:parse|literal_eval)|sympify|"
        r"parse_expr|parse_latex|solve|expand|simplify|factor|lambdify)\s*\(",
    )
    import_pattern = re.compile(
        r"^\s*(?:from|import)\s+(?:sympy|numpy|matplotlib|PySide6)\b",
        re.MULTILINE,
    )

    for path in engine_paths:
        source = path.read_text(encoding="utf-8")
        assert call_pattern.search(source) is None, path

    for path in stage_6_and_7_module_paths:
        source = path.read_text(encoding="utf-8")
        assert import_pattern.search(source) is None, path


def test_validated_result_has_one_engine_construction_boundary() -> None:
    engine_root = Path(__file__).parents[2] / "math_drawing_assistant" / "engine"
    factory_files = []
    direct_construction_files = []
    for path in engine_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "_create_validated_explicit_expression(" in source:
            factory_files.append(path.name)
        if "ValidatedExplicitExpression(" in source:
            direct_construction_files.append(path.name)

    assert factory_files == ["validators.py"]
    assert direct_construction_files == []


def test_production_entry_orders_all_stage_boundaries_before_result_creation() -> None:
    validators_path = (
        Path(__file__).parents[2]
        / "math_drawing_assistant"
        / "engine"
        / "validators.py"
    )
    source = validators_path.read_text(encoding="utf-8")
    entry = source.split("def analyze_explicit_function", 1)[1].split(
        "def validate_explicit_candidate",
        1,
    )[0]
    ordered_markers = (
        "normalize_input(",
        "tokenize(",
        "split_equation(",
        "parse_input(",
        "classify_plot(",
        "validate_explicit_candidate(",
        "_create_validated_explicit_expression(",
    )

    positions = tuple(entry.index(marker) for marker in ordered_markers)
    assert positions == tuple(sorted(positions))


def test_models_never_import_engine_and_ast_has_no_untyped_payloads() -> None:
    models_root = Path(__file__).parents[2] / "math_drawing_assistant" / "models"
    for path in models_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "math_drawing_assistant.engine" not in source
        assert "dict[str, object]" not in source
        assert "from typing import Any" not in source
