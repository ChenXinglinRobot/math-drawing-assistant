"""Adversarial tests for the sealed stage 13D-2 equation receipt."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
import inspect
from pathlib import Path
import time
from typing import cast

import pytest

import math_drawing_assistant.engine as engine_package
import math_drawing_assistant.engine.equation_validator as validator_module
import math_drawing_assistant.engine.normalizer as normalizer_module
from math_drawing_assistant.config.limits import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.equation_splitter import split_equation
from math_drawing_assistant.engine.normalizer import NormalizedInput, normalize_input
from math_drawing_assistant.engine.parser import ParseMetrics, ParsedEquationInput, parse_input
from math_drawing_assistant.engine.plot_classifier import (
    EquationCandidate,
    LegacyEquationRejectionReason,
    classify_plot,
    classify_plot_route,
)
from math_drawing_assistant.engine.tokenizer import tokenize
from math_drawing_assistant.engine.validators import analyze_explicit_function
from math_drawing_assistant.engine.equation_validator import (
    EquationValidationError,
    EquationValidationFailureKind,
    ValidatedEquationInput,
    _validate_validated_equation_input,
    validate_equation_candidate,
)
from math_drawing_assistant.models.errors import ErrorInfo, SourceSpan
from math_drawing_assistant.models.plot_specs import (
    EquationProvenance,
    ValidatedExplicitExpression,
)
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


def _candidate(
    text: str,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> tuple[EquationCandidate, NormalizedInput]:
    normalized = normalize_input(text, limits=limits)
    assert type(normalized) is NormalizedInput, normalized
    tokens = tokenize(normalized, limits=limits)
    assert type(tokens) is tuple, tokens
    split = split_equation(tokens)
    assert not isinstance(split, ErrorInfo), split
    parsed = parse_input(split, limits=limits)
    assert type(parsed) is ParsedEquationInput, parsed
    candidate = classify_plot_route(parsed)
    assert type(candidate) is EquationCandidate, candidate
    return candidate, normalized


def _receipt(
    text: str = "x^2+y^2=1",
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> ValidatedEquationInput:
    candidate, normalized = _candidate(text, limits=limits)
    return validate_equation_candidate(candidate, normalized, limits=limits)


def _candidate_with_parsed(
    candidate: EquationCandidate,
    parsed: ParsedEquationInput,
) -> EquationCandidate:
    return replace(candidate, parsed_input=parsed)


def _forge_receipt(
    original: ValidatedEquationInput,
    *,
    parsed_input: object | None = None,
    provenance: object | None = None,
    free_variables: object | None = None,
    contract: object | None = None,
) -> ValidatedEquationInput:
    forged = object.__new__(ValidatedEquationInput)
    object.__setattr__(
        forged,
        "parsed_input",
        original.parsed_input if parsed_input is None else parsed_input,
    )
    object.__setattr__(
        forged,
        "provenance",
        original.provenance if provenance is None else provenance,
    )
    object.__setattr__(
        forged,
        "free_variables",
        original.free_variables if free_variables is None else free_variables,
    )
    object.__setattr__(
        forged,
        "_contract",
        original._contract if contract is None else contract,
    )
    return forged


def _unsafe_node(
    node_type: type[RestrictedExpression],
    **attributes: object,
) -> RestrictedExpression:
    node = object.__new__(node_type)
    for name, value in attributes.items():
        object.__setattr__(node, name, value)
    return cast(RestrictedExpression, node)


def _forbid_consumer_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, int]:
    calls = {"tokenize": 0, "split_equation": 0, "parse_input": 0}

    def forbidden(name: str) -> object:
        def fail(*args: object, **kwargs: object) -> object:
            del args, kwargs
            calls[name] += 1
            raise AssertionError(f"consumer called {name}")

        return fail

    for name in calls:
        monkeypatch.setattr(validator_module, name, forbidden(name))
    return calls


@pytest.mark.parametrize(
    ("text", "variables"),
    [
        ("x^2+y^2=1", ("x", "y")),
        ("x^3+y=0", ("x", "y")),
        ("1/(x-y)=0", ("x", "y")),
        ("sin(x)+y=0", ("x", "y")),
        ("log(x,1)+y=0", ("x", "y")),
        ("x=x", ("x",)),
        ("0=0", ()),
        ("pi=x", ("x",)),
    ],
)
def test_complete_safe_equations_are_sealed_without_mathematical_prejudgment(
    text: str,
    variables: tuple[str, ...],
) -> None:
    candidate, normalized = _candidate(text)
    receipt = validate_equation_candidate(candidate, normalized)

    assert type(receipt) is ValidatedEquationInput
    assert receipt.parsed_input is candidate.parsed_input
    assert receipt.parsed_input.left is candidate.parsed_input.left
    assert receipt.parsed_input.right is candidate.parsed_input.right
    assert receipt.parsed_input.metrics is candidate.parsed_input.metrics
    assert receipt.free_variables == variables
    assert receipt.provenance == EquationProvenance(
        normalized_input=normalized.text,
        normalized_span=SourceSpan(0, len(normalized.text)),
        source_span=normalized.source_map.map_normalized_span(
            SourceSpan(0, len(normalized.text)),
        ),
        limits_version=DEFAULT_LIMITS.version,
    )
    assert _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS) is receipt


def test_source_map_drives_equation_provenance_with_spaces_and_many_to_one_input() -> None:
    candidate, normalized = _candidate("  x**2 + y = 1  ")
    receipt = validate_equation_candidate(candidate, normalized)

    assert normalized.text == "x^2+y=1"
    assert receipt.provenance.normalized_span == SourceSpan(0, 7)
    assert receipt.provenance.source_span == SourceSpan(2, 14)
    assert receipt.provenance.source_span == normalized.source_map.map_normalized_span(
        receipt.provenance.normalized_span,
    )


def test_receipt_has_only_the_four_frozen_slotted_hashable_fields() -> None:
    receipt = _receipt()

    assert is_dataclass(ValidatedEquationInput)
    assert ValidatedEquationInput.__dataclass_params__.frozen is True
    assert "__dict__" not in ValidatedEquationInput.__dict__
    assert tuple(field.name for field in fields(ValidatedEquationInput)) == (
        "parsed_input",
        "provenance",
        "free_variables",
        "_contract",
    )
    assert hash(receipt)
    with pytest.raises(FrozenInstanceError):
        receipt.free_variables = ()  # type: ignore[misc]
    forbidden = {
        "candidate",
        "legacy_rejection_reason",
        "legacy_normalized_span",
        "legacy_source_span",
        "normalized_input",
        "limits_version",
        "item_id",
        "requested_plot_kind",
        "plot_kind",
        "coefficients",
        "geometry",
        "spec",
    }
    assert forbidden.isdisjoint(field.name for field in fields(receipt))


def test_legacy_reason_and_spans_are_isolated_from_validation() -> None:
    candidate, normalized = _candidate("x^2+y^2=1")
    baseline = validate_equation_candidate(candidate, normalized)
    altered = replace(
        candidate,
        legacy_rejection_reason=LegacyEquationRejectionReason.Y_PRESENT_ON_EXPLICIT_SIDE,
        legacy_normalized_span=SourceSpan(1, 2),
        legacy_source_span=SourceSpan(2, 3),
    )
    changed = validate_equation_candidate(altered, normalized)

    assert changed.parsed_input is baseline.parsed_input
    assert changed.provenance == baseline.provenance
    assert changed.free_variables == baseline.free_variables


def test_public_and_private_constructors_and_replace_are_closed() -> None:
    receipt = _receipt()
    contract_type = type(receipt._contract)

    with pytest.raises(TypeError):
        ValidatedEquationInput()
    with pytest.raises(TypeError):
        ValidatedEquationInput(  # type: ignore[call-arg]
            parsed_input=receipt.parsed_input,
            provenance=receipt.provenance,
            free_variables=receipt.free_variables,
            _contract=receipt._contract,
        )
    with pytest.raises(TypeError):
        replace(receipt, free_variables=())
    with pytest.raises(TypeError):
        contract_type()
    with pytest.raises(TypeError):
        replace(receipt._contract, limits_version="forged")


def test_missing_contract_fake_seal_and_provenance_alone_are_rejected() -> None:
    receipt = _receipt()
    missing = object.__new__(ValidatedEquationInput)
    object.__setattr__(missing, "parsed_input", receipt.parsed_input)
    object.__setattr__(missing, "provenance", receipt.provenance)
    object.__setattr__(missing, "free_variables", receipt.free_variables)

    with pytest.raises(TypeError):
        _validate_validated_equation_input(missing, limits=DEFAULT_LIMITS)
    with pytest.raises(TypeError):
        _validate_validated_equation_input(receipt.provenance, limits=DEFAULT_LIMITS)

    forged_contract = object.__new__(type(receipt._contract))
    for name in (
        "parsed_input",
        "normalized_input",
        "source_map",
        "provenance",
        "free_variables",
        "limits_version",
    ):
        object.__setattr__(forged_contract, name, getattr(receipt._contract, name))
    object.__setattr__(forged_contract, "_seal", object())
    forged = _forge_receipt(receipt, contract=forged_contract)
    with pytest.raises(TypeError):
        _validate_validated_equation_input(forged, limits=DEFAULT_LIMITS)


@pytest.mark.parametrize("field_name", ["parsed_input", "provenance", "free_variables"])
def test_stolen_contract_cannot_authorize_replaced_receipt_fields(field_name: str) -> None:
    first = _receipt("x^2+y^2=1")
    second = _receipt("x=x")
    replacements: dict[str, object] = {
        "parsed_input": second.parsed_input,
        "provenance": second.provenance,
        "free_variables": second.free_variables,
    }
    forged = _forge_receipt(first, **{field_name: replacements[field_name]})

    with pytest.raises((EquationValidationError, TypeError)):
        _validate_validated_equation_input(forged, limits=DEFAULT_LIMITS)


def test_stolen_seal_cannot_authorize_different_normalized_input_or_source_map() -> None:
    first = _receipt("x^2+y^2=1")
    original_contract = first._contract
    original_normalized = original_contract.normalized_input
    original_map = original_normalized.source_map
    copied_map = type(original_map)(
        original_map.original_text,
        original_map.normalized_text,
        original_map.character_spans,
    )
    copied_normalized = NormalizedInput(original_normalized.text, copied_map)
    forged_contract = object.__new__(type(original_contract))
    for name in (
        "parsed_input",
        "provenance",
        "free_variables",
        "limits_version",
        "_parsed_input_identity",
        "_normalized_input_identity",
        "_source_map_identity",
        "_provenance_identity",
        "_limits_version_snapshot",
        "_seal",
    ):
        object.__setattr__(forged_contract, name, getattr(original_contract, name))
    object.__setattr__(forged_contract, "normalized_input", copied_normalized)
    object.__setattr__(forged_contract, "source_map", copied_map)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(
            _forge_receipt(first, contract=forged_contract),
            limits=DEFAULT_LIMITS,
        )


@pytest.mark.parametrize(
    "invalid",
    [None, object(), "equation"],
)
def test_top_level_types_are_exact_programmer_boundaries(invalid: object) -> None:
    candidate, normalized = _candidate("x=x")
    with pytest.raises(TypeError):
        validate_equation_candidate(invalid, normalized)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        validate_equation_candidate(candidate, invalid)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        validate_equation_candidate(candidate, normalized, limits=invalid)  # type: ignore[arg-type]


class _CandidateSubclass(EquationCandidate):
    pass


class _ParsedEquationSubclass(ParsedEquationInput):
    pass


class _ReceiptSubclass(ValidatedEquationInput):
    pass


def test_candidate_parser_product_and_receipt_subclasses_are_rejected() -> None:
    candidate, normalized = _candidate("x=x")
    candidate_subclass = _CandidateSubclass(
        candidate.parsed_input,
        candidate.legacy_rejection_reason,
        candidate.legacy_normalized_span,
        candidate.legacy_source_span,
    )
    parsed = candidate.parsed_input
    parsed_subclass = _ParsedEquationSubclass(
        parsed.left,
        parsed.right,
        parsed.left_normalized_span,
        parsed.right_normalized_span,
        parsed.left_source_span,
        parsed.right_source_span,
        parsed.metrics,
    )

    with pytest.raises(TypeError):
        validate_equation_candidate(candidate_subclass, normalized)
    with pytest.raises(TypeError):
        validate_equation_candidate(
            replace(candidate, parsed_input=parsed_subclass),
            normalized,
        )
    receipt_subclass = object.__new__(_ReceiptSubclass)
    with pytest.raises(TypeError):
        _validate_validated_equation_input(receipt_subclass, limits=DEFAULT_LIMITS)


@pytest.mark.parametrize(
    "field_name",
    [
        "token_count",
        "ast_node_count",
        "max_ast_depth",
        "max_function_arguments",
        "max_absolute_literal_exponent",
    ],
)
def test_each_parser_metric_is_recomputed_or_replayed(field_name: str) -> None:
    candidate, normalized = _candidate("log(x,2)+y=0")
    metrics = candidate.parsed_input.metrics
    forged_metrics = replace(metrics, **{field_name: getattr(metrics, field_name) + 1})
    forged_parsed = replace(candidate.parsed_input, metrics=forged_metrics)

    with pytest.raises(EquationValidationError) as exception:
        validate_equation_candidate(
            _candidate_with_parsed(candidate, forged_parsed),
            normalized,
        )
    assert exception.value.kind is EquationValidationFailureKind.INVALID_PARSER_METRICS


def test_limits_version_must_match_at_issuance_and_consumption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, normalized = _candidate("x=x")
    forged_metrics = replace(
        candidate.parsed_input.metrics,
        limits_version="forged-v999",
    )
    forged = replace(candidate.parsed_input, metrics=forged_metrics)

    with pytest.raises(EquationValidationError) as issuance:
        validate_equation_candidate(_candidate_with_parsed(candidate, forged), normalized)
    assert issuance.value.kind is EquationValidationFailureKind.LIMITS_VERSION_MISMATCH

    receipt = _receipt("x=x")
    incompatible = replace(DEFAULT_LIMITS, version="incompatible-v999")
    calls = _forbid_consumer_replay(monkeypatch)
    with pytest.raises(EquationValidationError) as consumption:
        _validate_validated_equation_input(receipt, limits=incompatible)
    assert consumption.value.kind is EquationValidationFailureKind.LIMITS_VERSION_MISMATCH
    assert calls == {"tokenize": 0, "split_equation": 0, "parse_input": 0}


def test_same_version_different_active_limits_reject_without_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt("x+x+x=0")
    narrow = replace(DEFAULT_LIMITS, max_ast_nodes=2)
    calls = _forbid_consumer_replay(monkeypatch)

    with pytest.raises(EquationValidationError) as exception:
        _validate_validated_equation_input(receipt, limits=narrow)
    assert (
        exception.value.kind
        is EquationValidationFailureKind.INCOMPATIBLE_LIMITS_CONTRACT
    )
    assert calls == {"tokenize": 0, "split_equation": 0, "parse_input": 0}


@pytest.mark.parametrize(
    "changes",
    [
        {"max_tokens": DEFAULT_LIMITS.max_tokens - 1},
        {"max_nesting_depth": DEFAULT_LIMITS.max_nesting_depth - 1},
        {"max_decimal_places": DEFAULT_LIMITS.max_decimal_places - 1},
        {
            "max_rational_numerator_digits": (
                DEFAULT_LIMITS.max_rational_numerator_digits - 1
            ),
        },
        {
            "max_rational_denominator_digits": (
                DEFAULT_LIMITS.max_rational_denominator_digits - 1
            ),
        },
    ],
)
def test_same_version_input_profile_difference_is_incompatible_without_replay(
    changes: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt("x=x")
    incompatible = replace(DEFAULT_LIMITS, **changes)
    calls = _forbid_consumer_replay(monkeypatch)

    with pytest.raises(EquationValidationError) as exception:
        _validate_validated_equation_input(receipt, limits=incompatible)
    assert (
        exception.value.kind
        is EquationValidationFailureKind.INCOMPATIBLE_LIMITS_CONTRACT
    )
    assert calls == {"tokenize": 0, "split_equation": 0, "parse_input": 0}


def test_exact_active_input_profile_consumes_without_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt("x=x")
    active = replace(DEFAULT_LIMITS)
    calls = _forbid_consumer_replay(monkeypatch)

    assert _validate_validated_equation_input(receipt, limits=active) is receipt
    assert calls == {"tokenize": 0, "split_equation": 0, "parse_input": 0}


def test_private_input_limits_profile_is_frozen_slotted_and_complete() -> None:
    receipt = _receipt("x=x")
    profile = receipt._contract._limits_profile

    assert is_dataclass(profile)
    assert type(profile).__dataclass_params__.frozen is True
    assert "__dict__" not in type(profile).__dict__
    assert tuple(field.name for field in fields(profile)) == (
        "version",
        "max_input_characters",
        "max_tokens",
        "max_ast_nodes",
        "max_nesting_depth",
        "max_numeric_digits",
        "max_decimal_places",
        "max_rational_numerator_digits",
        "max_rational_denominator_digits",
        "max_absolute_exponent",
        "max_function_arguments",
    )
    assert type(profile).__name__ not in validator_module.__all__
    assert "limits_profile" not in {
        field.name for field in fields(ValidatedEquationInput)
    }
    with pytest.raises(FrozenInstanceError):
        profile.max_tokens = profile.max_tokens + 1  # type: ignore[misc]


def test_issuance_replays_once_and_later_consumption_replays_zero_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, normalized = _candidate("1.25+x=2")
    calls = {
        "normalize_input": 0,
        "tokenize": 0,
        "split_equation": 0,
        "parse_input": 0,
    }
    original_normalize = normalizer_module.normalize_input
    original_tokenize = validator_module.tokenize
    original_split = validator_module.split_equation
    original_parse = validator_module.parse_input

    def counted_normalize(*args: object, **kwargs: object) -> object:
        calls["normalize_input"] += 1
        return original_normalize(*args, **kwargs)  # type: ignore[arg-type]

    def counted_tokenize(*args: object, **kwargs: object) -> object:
        calls["tokenize"] += 1
        return original_tokenize(*args, **kwargs)  # type: ignore[arg-type]

    def counted_split(*args: object, **kwargs: object) -> object:
        calls["split_equation"] += 1
        return original_split(*args, **kwargs)  # type: ignore[arg-type]

    def counted_parse(*args: object, **kwargs: object) -> object:
        calls["parse_input"] += 1
        return original_parse(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(normalizer_module, "normalize_input", counted_normalize)
    monkeypatch.setattr(validator_module, "tokenize", counted_tokenize)
    monkeypatch.setattr(validator_module, "split_equation", counted_split)
    monkeypatch.setattr(validator_module, "parse_input", counted_parse)

    receipt = validate_equation_candidate(candidate, normalized)
    issuance = calls.copy()
    assert issuance == {
        "normalize_input": 0,
        "tokenize": 1,
        "split_equation": 1,
        "parse_input": 1,
    }

    assert _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS) is receipt
    first_consumption = {
        name: calls[name] - issuance[name]
        for name in calls
    }
    assert first_consumption == {
        "normalize_input": 0,
        "tokenize": 0,
        "split_equation": 0,
        "parse_input": 0,
    }

    before_second = calls.copy()
    assert _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS) is receipt
    second_consumption = {
        name: calls[name] - before_second[name]
        for name in calls
    }
    assert second_consumption == {
        "normalize_input": 0,
        "tokenize": 0,
        "split_equation": 0,
        "parse_input": 0,
    }


def test_decimal_places_are_recomputed_from_number_lexeme_without_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = replace(DEFAULT_LIMITS, max_decimal_places=2)
    receipt = _receipt("1.25=x", limits=limits)
    assert type(receipt.parsed_input.left) is NumberNode
    object.__setattr__(receipt.parsed_input.left, "lexeme", "1.250")
    calls = _forbid_consumer_replay(monkeypatch)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=limits)
    assert calls == {"tokenize": 0, "split_equation": 0, "parse_input": 0}


def test_parser_metric_snapshot_protects_token_count_without_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt("x=x")
    object.__setattr__(
        receipt.parsed_input.metrics,
        "token_count",
        receipt.parsed_input.metrics.token_count + 1,
    )
    calls = _forbid_consumer_replay(monkeypatch)

    with pytest.raises(EquationValidationError) as exception:
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)
    assert exception.value.kind is EquationValidationFailureKind.INVALID_PARSER_METRICS
    assert calls == {"tokenize": 0, "split_equation": 0, "parse_input": 0}


def test_parser_product_snapshot_rejects_within_limit_lexeme_tampering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt("1=x")
    assert type(receipt.parsed_input.left) is NumberNode
    object.__setattr__(receipt.parsed_input.left, "lexeme", "2")
    calls = _forbid_consumer_replay(monkeypatch)

    with pytest.raises(EquationValidationError) as exception:
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)
    assert (
        exception.value.kind
        is EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH
    )
    assert calls == {"tokenize": 0, "split_equation": 0, "parse_input": 0}


def test_normalized_input_source_map_snapshot_rejects_tampering_without_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt("x=x")
    object.__setattr__(
        receipt._contract.normalized_input.source_map,
        "original_text",
        "y=y",
    )
    calls = _forbid_consumer_replay(monkeypatch)

    with pytest.raises(EquationValidationError) as exception:
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)
    assert (
        exception.value.kind
        is EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH
    )
    assert calls == {"tokenize": 0, "split_equation": 0, "parse_input": 0}


@pytest.mark.parametrize(
    "field_name",
    [
        "left",
        "right",
        "metrics",
        "left_normalized_span",
        "right_normalized_span",
        "left_source_span",
        "right_source_span",
    ],
)
def test_parsed_input_equal_value_field_replacement_is_rejected(
    field_name: str,
) -> None:
    receipt = _receipt("x+1=2")
    parsed = receipt.parsed_input
    original = getattr(parsed, field_name)
    if field_name in {"left", "right"}:
        replacement = replace(original)
    elif type(original) is ParseMetrics:
        replacement = replace(original)
    else:
        assert type(original) is SourceSpan
        replacement = SourceSpan(original.start, original.end)
    assert replacement == original
    assert replacement is not original
    object.__setattr__(parsed, field_name, replacement)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)


def test_number_root_equal_value_identity_replacement_is_rejected() -> None:
    receipt = _receipt("1=x")
    original = receipt.parsed_input.left
    assert type(original) is NumberNode
    replacement = replace(original)
    assert replacement == original and replacement is not original
    object.__setattr__(receipt.parsed_input, "left", replacement)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)


@pytest.mark.parametrize(
    ("text", "parent_type", "child_name"),
    [
        ("-1=0", UnaryOpNode, "operand"),
        ("x+1=0", BinaryOpNode, "left"),
        ("x+1=0", BinaryOpNode, "right"),
    ],
)
def test_equal_value_child_identity_replacement_is_rejected(
    text: str,
    parent_type: type[RestrictedExpression],
    child_name: str,
) -> None:
    receipt = _receipt(text)
    parent = receipt.parsed_input.left
    assert type(parent) is parent_type
    original = getattr(parent, child_name)
    replacement = replace(original)
    assert replacement == original and replacement is not original
    object.__setattr__(parent, child_name, replacement)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)


def test_function_argument_equal_value_node_replacement_is_rejected() -> None:
    receipt = _receipt("sin(x)=0")
    function = receipt.parsed_input.left
    assert type(function) is FunctionCallNode
    original_argument = function.arguments[0]
    replacement = replace(original_argument)
    new_arguments = (replacement,)
    assert replacement == original_argument and replacement is not original_argument
    object.__setattr__(function, "arguments", new_arguments)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)


def test_function_arguments_equal_value_tuple_replacement_is_rejected() -> None:
    receipt = _receipt("log(x,2)=0")
    function = receipt.parsed_input.left
    assert type(function) is FunctionCallNode
    original = function.arguments
    replacement = tuple([*original])
    assert replacement == original and replacement is not original
    object.__setattr__(function, "arguments", replacement)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)


@pytest.mark.parametrize("span_name", ["normalized_span", "source_span"])
def test_ast_equal_value_span_identity_replacement_is_rejected(
    span_name: str,
) -> None:
    receipt = _receipt("x=0")
    node = receipt.parsed_input.left
    original = getattr(node, span_name)
    replacement = SourceSpan(original.start, original.end)
    assert replacement == original and replacement is not original
    object.__setattr__(node, span_name, replacement)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)


@pytest.mark.parametrize(
    ("text", "attribute", "replacement"),
    [
        ("1=0", "lexeme", "2"),
        ("x=0", "name", "y"),
        ("pi=0", "name", "E"),
        ("-1=0", "operator", UnaryOperator.POSITIVE),
        ("x+1=0", "operator", BinaryOperator.SUBTRACT),
        ("sin(x)=0", "name", "cos"),
    ],
)
def test_each_ast_node_payload_mutation_is_rejected(
    text: str,
    attribute: str,
    replacement: object,
) -> None:
    receipt = _receipt(text)
    object.__setattr__(receipt.parsed_input.left, attribute, replacement)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)


def test_binary_implicit_payload_mutation_is_rejected() -> None:
    receipt = _receipt("2x=0")
    binary = receipt.parsed_input.left
    assert type(binary) is BinaryOpNode and binary.implicit is True
    object.__setattr__(binary, "implicit", False)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)


def test_binary_edge_order_mutation_is_rejected() -> None:
    receipt = _receipt("x+y=0")
    binary = receipt.parsed_input.left
    assert type(binary) is BinaryOpNode
    original_left, original_right = binary.left, binary.right
    object.__setattr__(binary, "left", original_right)
    object.__setattr__(binary, "right", original_left)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)


@pytest.mark.parametrize(
    "attack",
    [
        "source_map",
        "character_spans_tuple",
        "character_span_element",
        "normalized_text_field",
        "original_text_field",
        "source_map_normalized_text_field",
        "character_span_value",
    ],
)
def test_normalized_input_and_source_map_identity_or_value_attack_is_rejected(
    attack: str,
) -> None:
    receipt = _receipt("x=x")
    normalized = receipt._contract.normalized_input
    source_map = normalized.source_map
    if attack == "source_map":
        replacement_map = type(source_map)(
            source_map.original_text,
            source_map.normalized_text,
            source_map.character_spans,
        )
        assert replacement_map == source_map and replacement_map is not source_map
        object.__setattr__(normalized, "source_map", replacement_map)
    elif attack == "character_spans_tuple":
        replacement_spans = tuple([*source_map.character_spans])
        assert replacement_spans is not source_map.character_spans
        object.__setattr__(source_map, "character_spans", replacement_spans)
    elif attack == "character_span_element":
        spans = list(source_map.character_spans)
        original = spans[0]
        spans[0] = SourceSpan(original.start, original.end)
        assert spans[0] == original and spans[0] is not original
        object.__setattr__(source_map, "character_spans", tuple(spans))
    elif attack == "normalized_text_field":
        object.__setattr__(normalized, "text", "y=y")
    elif attack == "original_text_field":
        object.__setattr__(source_map, "original_text", "y=y")
    elif attack == "source_map_normalized_text_field":
        object.__setattr__(source_map, "normalized_text", "y=y")
    else:
        object.__setattr__(source_map.character_spans[0], "end", 2)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)


@pytest.mark.parametrize(
    "attack",
    [
        "equal_provenance",
        "equal_normalized_span",
        "equal_source_span",
        "normalized_input_value",
        "normalized_span_value",
        "source_span_value",
        "limits_version_value",
    ],
)
def test_provenance_identity_and_each_value_attack_is_rejected(attack: str) -> None:
    receipt = _receipt("x=x")
    provenance = receipt.provenance
    if attack == "equal_provenance":
        replacement = replace(provenance)
        assert replacement == provenance and replacement is not provenance
        object.__setattr__(receipt, "provenance", replacement)
    elif attack == "equal_normalized_span":
        span = provenance.normalized_span
        object.__setattr__(
            provenance,
            "normalized_span",
            SourceSpan(span.start, span.end),
        )
    elif attack == "equal_source_span":
        span = provenance.source_span
        object.__setattr__(
            provenance,
            "source_span",
            SourceSpan(span.start, span.end),
        )
    elif attack == "normalized_input_value":
        object.__setattr__(provenance, "normalized_input", "y=y")
    elif attack == "normalized_span_value":
        object.__setattr__(provenance, "normalized_span", SourceSpan(0, 2))
    elif attack == "source_span_value":
        object.__setattr__(provenance, "source_span", SourceSpan(0, 2))
    else:
        object.__setattr__(provenance, "limits_version", "other-limits")

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)


def test_private_typed_snapshots_bind_references_identities_and_values() -> None:
    receipt = _receipt("log(-x,2)=0")
    contract = receipt._contract
    parsed_snapshot = contract._parsed_input_snapshot
    normalized_snapshot = contract._normalized_input_snapshot
    provenance_snapshot = contract._provenance_snapshot

    assert parsed_snapshot.parsed_input is receipt.parsed_input
    assert parsed_snapshot.identity == id(receipt.parsed_input)
    assert parsed_snapshot.left is receipt.parsed_input.left
    assert parsed_snapshot.left_identity == id(receipt.parsed_input.left)
    assert parsed_snapshot.right is receipt.parsed_input.right
    assert parsed_snapshot.right_identity == id(receipt.parsed_input.right)
    assert parsed_snapshot.metrics.metrics is receipt.parsed_input.metrics
    assert parsed_snapshot.metrics.identity == id(receipt.parsed_input.metrics)
    for span_snapshot, span in (
        (parsed_snapshot.left_normalized_span, receipt.parsed_input.left_normalized_span),
        (parsed_snapshot.right_normalized_span, receipt.parsed_input.right_normalized_span),
        (parsed_snapshot.left_source_span, receipt.parsed_input.left_source_span),
        (parsed_snapshot.right_source_span, receipt.parsed_input.right_source_span),
    ):
        assert span_snapshot.span is span
        assert span_snapshot.identity == id(span)
        assert (span_snapshot.start, span_snapshot.end) == (span.start, span.end)

    function_occurrence = parsed_snapshot.left_ast.occurrences[0]
    function = receipt.parsed_input.left
    assert type(function) is FunctionCallNode
    assert function_occurrence.node is function
    assert function_occurrence.identity == id(function)
    assert function_occurrence.children == function.arguments
    assert function_occurrence.child_count == len(function.arguments)
    assert all(
        snapshotted is current
        for snapshotted, current in zip(
            function_occurrence.children,
            function.arguments,
            strict=True,
        )
    )
    assert function_occurrence.arguments is function.arguments
    assert function_occurrence.arguments_identity == id(function.arguments)
    assert function_occurrence.arguments_length == len(function.arguments)

    normalized = contract.normalized_input
    source_map = normalized.source_map
    assert normalized_snapshot.normalized_input is normalized
    assert normalized_snapshot.identity == id(normalized)
    assert normalized_snapshot.source_map is source_map
    assert normalized_snapshot.source_map_identity == id(source_map)
    source_snapshot = normalized_snapshot.source_map_snapshot
    assert source_snapshot.character_spans is source_map.character_spans
    assert source_snapshot.character_spans_identity == id(source_map.character_spans)
    assert source_snapshot.character_spans_length == len(source_map.character_spans)
    assert all(
        snapshot.span is span and snapshot.identity == id(span)
        for snapshot, span in zip(
            source_snapshot.character_span_snapshots,
            source_map.character_spans,
            strict=True,
        )
    )

    assert provenance_snapshot.provenance is receipt.provenance
    assert provenance_snapshot.identity == id(receipt.provenance)
    assert provenance_snapshot.normalized_span.span is receipt.provenance.normalized_span
    assert provenance_snapshot.source_span.span is receipt.provenance.source_span


@pytest.mark.parametrize(
    "matching_pair",
    [
        "receipt_and_snapshot",
        "receipt_and_expected",
        "snapshot_and_expected",
    ],
)
def test_provenance_three_way_comparison_rejects_when_only_two_sides_match(
    matching_pair: str,
) -> None:
    receipt = _receipt("x=x")
    contract = receipt._contract
    if matching_pair == "receipt_and_snapshot":
        object.__setattr__(contract.normalized_input, "text", "y=y")
        object.__setattr__(contract.source_map, "normalized_text", "y=y")
    elif matching_pair == "receipt_and_expected":
        object.__setattr__(
            contract._provenance_snapshot,
            "normalized_input",
            "signed-snapshot-only",
        )
    else:
        replacement = replace(receipt.provenance, normalized_input="receipt-only")
        object.__setattr__(receipt, "provenance", replacement)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=DEFAULT_LIMITS)


@pytest.mark.parametrize("signed", [False, True])
@pytest.mark.parametrize("side", ["numerator", "denominator"])
def test_rational_literal_digit_limits_follow_signed_integer_ast_rule(
    signed: bool,
    side: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = replace(
        DEFAULT_LIMITS,
        max_rational_numerator_digits=2,
        max_rational_denominator_digits=2,
    )
    text = "-12/+34=x" if signed else "12/34=x"
    receipt = _receipt(text, limits=limits)
    divide = receipt.parsed_input.left
    assert type(divide) is BinaryOpNode
    assert divide.operator is BinaryOperator.DIVIDE
    selected = divide.left if side == "numerator" else divide.right
    if signed:
        assert type(selected) is UnaryOpNode
        selected = selected.operand
    assert type(selected) is NumberNode
    object.__setattr__(selected, "lexeme", "123")
    calls = _forbid_consumer_replay(monkeypatch)

    with pytest.raises(EquationValidationError):
        _validate_validated_equation_input(receipt, limits=limits)
    assert calls == {"tokenize": 0, "split_equation": 0, "parse_input": 0}


def test_non_literal_division_is_not_treated_as_a_rational_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = replace(
        DEFAULT_LIMITS,
        max_rational_numerator_digits=1,
        max_rational_denominator_digits=1,
    )
    receipt = _receipt("(12+34)/(56+78)=x", limits=limits)
    calls = _forbid_consumer_replay(monkeypatch)

    assert _validate_validated_equation_input(receipt, limits=limits) is receipt
    assert calls == {"tokenize": 0, "split_equation": 0, "parse_input": 0}


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("left_normalized_span", SourceSpan(1, 1)),
        ("left_normalized_span", SourceSpan(0, 2)),
        ("right_normalized_span", SourceSpan(1, 3)),
        ("left_source_span", SourceSpan(0, 2)),
        ("right_source_span", SourceSpan(1, 3)),
    ],
)
def test_side_span_order_root_and_source_map_mismatches_are_rejected(
    field_name: str,
    replacement: SourceSpan,
) -> None:
    candidate, normalized = _candidate("x=1")
    forged_parsed = replace(candidate.parsed_input, **{field_name: replacement})

    with pytest.raises(EquationValidationError) as exception:
        validate_equation_candidate(
            _candidate_with_parsed(candidate, forged_parsed),
            normalized,
        )
    assert exception.value.kind is EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH


def test_candidate_from_one_formula_cannot_use_another_normalized_input() -> None:
    candidate, _ = _candidate("x=x")
    _, other = _candidate("0=0")

    with pytest.raises(EquationValidationError) as exception:
        validate_equation_candidate(candidate, other)
    assert exception.value.kind is EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH


class _NumberSubclass(NumberNode):
    pass


class _SymbolSubclass(SymbolNode):
    pass


class _ConstantSubclass(ConstantNode):
    pass


class _UnarySubclass(UnaryOpNode):
    pass


class _BinarySubclass(BinaryOpNode):
    pass


class _FunctionSubclass(FunctionCallNode):
    pass


@pytest.mark.parametrize(
    "factory",
    [
        lambda span: _NumberSubclass(span, span, "1"),
        lambda span: _SymbolSubclass(span, span, "x"),
        lambda span: _ConstantSubclass(span, span, "pi"),
        lambda span: _UnarySubclass(
            span,
            span,
            UnaryOperator.NEGATIVE,
            NumberNode(span, span, "1"),
        ),
        lambda span: _BinarySubclass(
            span,
            span,
            BinaryOperator.ADD,
            NumberNode(span, span, "1"),
            NumberNode(span, span, "1"),
        ),
        lambda span: _FunctionSubclass(
            span,
            span,
            "sin",
            (NumberNode(span, span, "1"),),
        ),
    ],
)
def test_all_six_restricted_node_subclasses_are_rejected(factory: object) -> None:
    candidate, normalized = _candidate("x=1")
    span = candidate.parsed_input.left_normalized_span
    forged_left = factory(span)  # type: ignore[operator]
    forged_parsed = replace(candidate.parsed_input, left=forged_left)

    with pytest.raises(EquationValidationError) as exception:
        validate_equation_candidate(
            _candidate_with_parsed(candidate, forged_parsed),
            normalized,
        )
    assert exception.value.kind is EquationValidationFailureKind.INVALID_RESTRICTED_AST


@pytest.mark.parametrize(
    ("node_type", "attributes"),
    [
        (NumberNode, {"lexeme": "1..2"}),
        (SymbolNode, {"name": "z"}),
        (ConstantNode, {"name": "tau"}),
        (
            UnaryOpNode,
            {"operator": object(), "operand": object()},
        ),
        (
            BinaryOpNode,
            {
                "operator": BinaryOperator.ADD,
                "left": object(),
                "right": object(),
                "implicit": True,
            },
        ),
        (FunctionCallNode, {"name": "unknown", "arguments": (object(),)}),
    ],
)
def test_malformed_closed_node_payloads_are_rejected(
    node_type: type[RestrictedExpression],
    attributes: dict[str, object],
) -> None:
    candidate, normalized = _candidate("x=1")
    span = candidate.parsed_input.left_normalized_span
    source_span = normalized.source_map.map_normalized_span(span)
    forged_left = _unsafe_node(
        node_type,
        normalized_span=span,
        source_span=source_span,
        **attributes,
    )
    forged_parsed = replace(candidate.parsed_input, left=forged_left)

    with pytest.raises(EquationValidationError) as exception:
        validate_equation_candidate(
            _candidate_with_parsed(candidate, forged_parsed),
            normalized,
        )
    assert exception.value.kind is EquationValidationFailureKind.INVALID_RESTRICTED_AST


def test_cycle_and_shared_node_graphs_are_rejected_with_a_time_boundary() -> None:
    candidate, normalized = _candidate("x+x=1")
    root = candidate.parsed_input.left
    assert type(root) is BinaryOpNode
    cyclic = _unsafe_node(
        BinaryOpNode,
        normalized_span=root.normalized_span,
        source_span=root.source_span,
        operator=BinaryOperator.ADD,
        left=cast(RestrictedExpression, object()),
        right=root.right,
        implicit=False,
    )
    object.__setattr__(cyclic, "left", cyclic)
    shared = _unsafe_node(
        BinaryOpNode,
        normalized_span=root.normalized_span,
        source_span=root.source_span,
        operator=BinaryOperator.ADD,
        left=root.left,
        right=root.left,
        implicit=False,
    )

    started = time.monotonic()
    for forged_left in (cyclic, shared):
        forged_parsed = replace(candidate.parsed_input, left=forged_left)
        with pytest.raises(EquationValidationError):
            validate_equation_candidate(
                _candidate_with_parsed(candidate, forged_parsed),
                normalized,
            )
    assert time.monotonic() - started < 1.0


def test_error_contract_is_typed_operand_free_and_uses_only_trusted_spans() -> None:
    error = EquationValidationError(
        EquationValidationFailureKind.INVALID_RESTRICTED_AST,
        SourceSpan(0, 1),
        SourceSpan(2, 3),
    )

    assert isinstance(error, ValueError)
    assert EquationValidationError.__slots__ == (
        "kind",
        "normalized_span",
        "source_span",
    )
    assert error.__dict__ == {}
    for forbidden in ("candidate", "operand", "ast", "input_text", "traceback"):
        assert not hasattr(error, forbidden)


def test_static_import_call_and_factory_boundary_is_narrow() -> None:
    path = Path(validator_module.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert imports.isdisjoint(
        {
            "math_drawing_assistant.engine.equation_polynomial",
            "math_drawing_assistant.engine.equation_classifier",
            "math_drawing_assistant.engine.spec_builder",
            "sympy",
            "numpy",
            "matplotlib",
            "PySide6",
        },
    )
    loaded = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert loaded.isdisjoint(
        {
            "canonicalize_equation",
            "classify_equation_geometry",
            "PrimitiveEquationCoefficients",
            "requested_plot_kind",
            "classify_plot",
            "validate_explicit_candidate",
            "eval",
            "exec",
            "compile",
            "parse",
            "literal_eval",
        },
    )
    object_new_receipts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "object"
        and node.func.attr == "__new__"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "ValidatedEquationInput"
    ]
    assert len(object_new_receipts) == 1
    assert "ValidatedEquationInput(" not in source
    assert "from typing import Any" not in source
    assert "dict[str, object]" not in source


def test_public_surface_and_layering_are_exact() -> None:
    assert validator_module.__all__ == [
        "EquationValidationFailureKind",
        "EquationValidationError",
        "ValidatedEquationInput",
        "validate_equation_candidate",
    ]
    assert list(EquationValidationFailureKind) == [
        EquationValidationFailureKind.INVALID_RESTRICTED_AST,
        EquationValidationFailureKind.INVALID_PARSER_METRICS,
        EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        EquationValidationFailureKind.LIMITS_VERSION_MISMATCH,
        EquationValidationFailureKind.INCOMPATIBLE_LIMITS_CONTRACT,
    ]
    assert not hasattr(engine_package, "ValidatedEquationInput")
    assert not hasattr(engine_package, "validate_equation_candidate")
    assert "ErrorInfo" not in inspect.signature(validate_equation_candidate).return_annotation


def test_legacy_m1_entries_and_validated_explicit_receipt_are_unchanged() -> None:
    candidate, _ = _candidate("x=x")
    legacy = classify_plot(candidate.parsed_input)
    assert type(legacy) is ErrorInfo
    assert inspect.signature(classify_plot).parameters.keys() == {"parsed_input"}
    explicit = analyze_explicit_function("sin(x)")
    assert type(explicit) is ValidatedExplicitExpression
    with pytest.raises(TypeError):
        ValidatedExplicitExpression()


def test_factory_immediately_uses_the_same_consumer_revalidation_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, normalized = _candidate("x=x")
    original = validator_module._validate_validated_equation_input
    calls: list[object] = []

    def spy(value: object, *, limits: ApplicationLimits) -> ValidatedEquationInput:
        calls.append(value)
        return original(value, limits=limits)

    monkeypatch.setattr(validator_module, "_validate_validated_equation_input", spy)
    result = validator_module.validate_equation_candidate(candidate, normalized)
    assert calls == [result]
