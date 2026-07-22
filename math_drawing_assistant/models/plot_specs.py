"""Minimal typed boundary for validated plot specifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias, runtime_checkable

from math_drawing_assistant.models.errors import SourceSpan
from math_drawing_assistant.models.restricted_ast import (
    RestrictedExpression,
    _validate_restricted_expression,
)
from math_drawing_assistant.models.state import PlotKind


ExplicitExpressionSource: TypeAlias = Literal[
    "expression",
    "y_equals",
    "equals_y",
]

_VALIDATION_CONTRACT_SEAL = object()


@dataclass(frozen=True, slots=True)
class _ValidatedExpressionContract:
    """Internal receipt proving parser and active limits versions matched."""

    limits_version: str
    _seal: object

    def __post_init__(self) -> None:
        if self._seal is not _VALIDATION_CONTRACT_SEAL:
            raise TypeError("Validated expression contracts are issued internally.")
        if type(self.limits_version) is not str or not self.limits_version:
            raise ValueError("limits_version must be a non-empty string.")


def _issue_validated_expression_contract(
    *,
    parser_limits_version: str,
    active_limits_version: str,
) -> _ValidatedExpressionContract:
    if type(parser_limits_version) is not str or not parser_limits_version:
        raise ValueError("parser_limits_version must be a non-empty string.")
    if type(active_limits_version) is not str or not active_limits_version:
        raise ValueError("active_limits_version must be a non-empty string.")
    if parser_limits_version != active_limits_version:
        raise ValueError("Parser and active limits versions must match.")
    return _ValidatedExpressionContract(
        limits_version=active_limits_version,
        _seal=_VALIDATION_CONTRACT_SEAL,
    )


@dataclass(frozen=True, slots=True, init=False)
class ValidatedExplicitExpression:
    """A controlled stage 7 result, before a caller injects an item identity."""

    expression: RestrictedExpression
    normalized_input: str
    normalized_span: SourceSpan
    source_span: SourceSpan
    source_form: ExplicitExpressionSource
    free_variables: tuple[Literal["x"], ...]
    limits_version: str

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "ValidatedExplicitExpression is created by the validated stage 7 entry.",
        )

    @property
    def plot_kind(self) -> PlotKind:
        """Return the only plot kind delivered by stage 7."""

        return PlotKind.EXPLICIT_FUNCTION


def _create_validated_explicit_expression(
    *,
    expression: RestrictedExpression,
    normalized_input: str,
    normalized_span: SourceSpan,
    source_span: SourceSpan,
    source_form: ExplicitExpressionSource,
    free_variables: tuple[Literal["x"], ...],
    contract: _ValidatedExpressionContract,
) -> ValidatedExplicitExpression:
    if type(contract) is not _ValidatedExpressionContract:
        raise TypeError("contract must be an issued validated expression contract.")
    contract.__post_init__()
    variables = _validate_restricted_expression(expression)
    if "y" in variables:
        raise ValueError("A validated explicit expression must not contain y.")
    expected_free_variables: tuple[Literal["x"], ...] = (
        ("x",) if "x" in variables else ()
    )
    if type(free_variables) is not tuple or free_variables != expected_free_variables:
        raise ValueError("free_variables must match the restricted AST.")
    if type(normalized_input) is not str or not normalized_input:
        raise ValueError("normalized_input must be a non-empty string.")
    if type(normalized_span) is not SourceSpan:
        raise TypeError("normalized_span must be a SourceSpan.")
    if type(source_span) is not SourceSpan:
        raise TypeError("source_span must be a SourceSpan.")
    if expression.normalized_span != normalized_span:
        raise ValueError("normalized_span must match the expression root.")
    if expression.source_span != source_span:
        raise ValueError("source_span must match the expression root.")
    if source_form not in {"expression", "y_equals", "equals_y"}:
        raise ValueError("source_form must be a published explicit source form.")

    result = object.__new__(ValidatedExplicitExpression)
    object.__setattr__(result, "expression", expression)
    object.__setattr__(result, "normalized_input", normalized_input)
    object.__setattr__(result, "normalized_span", normalized_span)
    object.__setattr__(result, "source_span", source_span)
    object.__setattr__(result, "source_form", source_form)
    object.__setattr__(result, "free_variables", free_variables)
    object.__setattr__(result, "limits_version", contract.limits_version)
    return result


@runtime_checkable
class PlotItemSpec(Protocol):
    """Contract fulfilled by future validated, immutable item specifications."""

    @property
    def item_id(self) -> str:
        """Return the item identity inherited from its request."""

    @property
    def plot_kind(self) -> PlotKind:
        """Return the classified plot kind."""


@dataclass(frozen=True, slots=True)
class PlotSceneSpec:
    """Validated snapshot of all items in a scene."""

    items: tuple[PlotItemSpec, ...]

    def __post_init__(self) -> None:
        item_snapshot = tuple(self.items)
        if not item_snapshot:
            raise ValueError("PlotSceneSpec.items must not be empty.")
        if not all(isinstance(item, PlotItemSpec) for item in item_snapshot):
            raise TypeError("items must satisfy the PlotItemSpec contract.")

        item_ids = tuple(item.item_id for item in item_snapshot)
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("PlotSceneSpec item_id values must be unique.")
        object.__setattr__(self, "items", item_snapshot)
