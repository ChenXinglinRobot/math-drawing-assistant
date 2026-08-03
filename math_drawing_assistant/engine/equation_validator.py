"""Sealed validation receipt for complete parsed equation inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, TypeAlias, TypeGuard

from math_drawing_assistant.config.limits import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.equation_splitter import split_equation
from math_drawing_assistant.engine.normalizer import NormalizedInput
from math_drawing_assistant.engine.parser import (
    ParseMetrics,
    ParsedEquationInput,
    parse_input,
)
from math_drawing_assistant.engine.plot_classifier import EquationCandidate
from math_drawing_assistant.engine.source_map import SourceMap
from math_drawing_assistant.engine.tokenizer import tokenize
from math_drawing_assistant.models.errors import ErrorInfo, SourceSpan
from math_drawing_assistant.models.plot_specs import EquationProvenance
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


EquationFreeVariables: TypeAlias = tuple[Literal["x", "y"], ...]
_AstLimitMetrics: TypeAlias = tuple[int, int, int, int, int, int, int, int]
_LimitsProfileValues: TypeAlias = tuple[
    str,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
]

_EXACT_NODE_TYPES = frozenset(
    {
        NumberNode,
        SymbolNode,
        ConstantNode,
        UnaryOpNode,
        BinaryOpNode,
        FunctionCallNode,
    },
)
_SEAL = object()


class EquationValidationFailureKind(str, Enum):
    """Closed safety failures produced before an equation receipt is issued."""

    INVALID_RESTRICTED_AST = "invalid_restricted_ast"
    INVALID_PARSER_METRICS = "invalid_parser_metrics"
    PARSER_PROVENANCE_MISMATCH = "parser_provenance_mismatch"
    LIMITS_VERSION_MISMATCH = "limits_version_mismatch"
    INCOMPATIBLE_LIMITS_CONTRACT = "incompatible_limits_contract"


class EquationValidationError(ValueError):
    """Small typed validation failure without AST operands or input text."""

    __slots__ = ("kind", "normalized_span", "source_span")

    kind: EquationValidationFailureKind
    normalized_span: SourceSpan | None
    source_span: SourceSpan | None

    def __init__(
        self,
        kind: EquationValidationFailureKind,
        normalized_span: SourceSpan | None = None,
        source_span: SourceSpan | None = None,
    ) -> None:
        if type(kind) is not EquationValidationFailureKind:
            raise TypeError("kind must be an exact EquationValidationFailureKind.")
        if normalized_span is not None and type(normalized_span) is not SourceSpan:
            raise TypeError("normalized_span must be an exact SourceSpan or None.")
        if source_span is not None and type(source_span) is not SourceSpan:
            raise TypeError("source_span must be an exact SourceSpan or None.")
        self.kind = kind
        self.normalized_span = normalized_span
        self.source_span = source_span
        super().__init__(f"equation validation failed ({kind.value})")


@dataclass(frozen=True, slots=True)
class _InputLimitsProfile:
    """Exact private snapshot of every input/parser limit used for issuance."""

    version: str
    max_input_characters: int
    max_tokens: int
    max_ast_nodes: int
    max_nesting_depth: int
    max_numeric_digits: int
    max_decimal_places: int
    max_rational_numerator_digits: int
    max_rational_denominator_digits: int
    max_absolute_exponent: int
    max_function_arguments: int


@dataclass(frozen=True, slots=True)
class _SpanSnapshot:
    span: SourceSpan
    identity: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _MetricsSnapshot:
    metrics: ParseMetrics
    identity: int
    token_count: int
    ast_node_count: int
    max_ast_depth: int
    max_function_arguments: int
    max_absolute_literal_exponent: int
    limits_version: str


@dataclass(frozen=True, slots=True)
class _NumberPayloadSnapshot:
    lexeme: str


@dataclass(frozen=True, slots=True)
class _SymbolPayloadSnapshot:
    name: str


@dataclass(frozen=True, slots=True)
class _ConstantPayloadSnapshot:
    name: str


@dataclass(frozen=True, slots=True)
class _UnaryPayloadSnapshot:
    operator: UnaryOperator


@dataclass(frozen=True, slots=True)
class _BinaryPayloadSnapshot:
    operator: BinaryOperator
    implicit: bool


@dataclass(frozen=True, slots=True)
class _FunctionPayloadSnapshot:
    name: str


_NodePayloadSnapshot: TypeAlias = (
    _NumberPayloadSnapshot
    | _SymbolPayloadSnapshot
    | _ConstantPayloadSnapshot
    | _UnaryPayloadSnapshot
    | _BinaryPayloadSnapshot
    | _FunctionPayloadSnapshot
)


@dataclass(frozen=True, slots=True)
class _AstOccurrenceSnapshot:
    node: RestrictedExpression
    identity: int
    node_type: type[RestrictedExpression]
    normalized_span: _SpanSnapshot
    source_span: _SpanSnapshot
    payload: _NodePayloadSnapshot
    children: tuple[RestrictedExpression, ...]
    child_identities: tuple[int, ...]
    child_count: int
    arguments: tuple[RestrictedExpression, ...] | None
    arguments_identity: int | None
    arguments_length: int | None


@dataclass(frozen=True, slots=True)
class _AstGraphSnapshot:
    occurrences: tuple[_AstOccurrenceSnapshot, ...]


@dataclass(frozen=True, slots=True)
class _ParsedInputSnapshot:
    parsed_input: ParsedEquationInput
    identity: int
    left: RestrictedExpression
    left_identity: int
    right: RestrictedExpression
    right_identity: int
    metrics: _MetricsSnapshot
    left_normalized_span: _SpanSnapshot
    right_normalized_span: _SpanSnapshot
    left_source_span: _SpanSnapshot
    right_source_span: _SpanSnapshot
    left_ast: _AstGraphSnapshot
    right_ast: _AstGraphSnapshot
    free_variables: EquationFreeVariables


@dataclass(frozen=True, slots=True)
class _SourceMapSnapshot:
    source_map: SourceMap
    identity: int
    original_text: str
    normalized_text: str
    character_spans: tuple[SourceSpan, ...]
    character_spans_identity: int
    character_spans_length: int
    character_span_snapshots: tuple[_SpanSnapshot, ...]


@dataclass(frozen=True, slots=True)
class _NormalizedInputSnapshot:
    normalized_input: NormalizedInput
    identity: int
    text: str
    source_map: SourceMap
    source_map_identity: int
    source_map_snapshot: _SourceMapSnapshot


@dataclass(frozen=True, slots=True)
class _ProvenanceSnapshot:
    provenance: EquationProvenance
    identity: int
    normalized_input: str
    normalized_span: _SpanSnapshot
    source_span: _SpanSnapshot
    limits_version: str


@dataclass(frozen=True, slots=True, init=False)
class _ValidatedEquationContract:
    """Private identity and version evidence bound by the issuing module."""

    parsed_input: ParsedEquationInput
    normalized_input: NormalizedInput
    source_map: SourceMap
    provenance: EquationProvenance
    free_variables: EquationFreeVariables
    limits_version: str
    _limits_profile: _InputLimitsProfile = field(repr=False)
    _parsed_input_identity: int = field(repr=False)
    _normalized_input_identity: int = field(repr=False)
    _source_map_identity: int = field(repr=False)
    _provenance_identity: int = field(repr=False)
    _limits_profile_identity: int = field(repr=False)
    _limits_version_snapshot: str = field(repr=False)
    _limits_profile_snapshot: _LimitsProfileValues = field(repr=False)
    _normalized_input_snapshot: _NormalizedInputSnapshot = field(repr=False)
    _parsed_input_snapshot: _ParsedInputSnapshot = field(repr=False)
    _provenance_snapshot: _ProvenanceSnapshot = field(repr=False)
    _seal: object = field(repr=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError("Validated equation contracts are issued internally.")


@dataclass(frozen=True, slots=True, init=False)
class ValidatedEquationInput:
    """A sealed complete-equation receipt retaining the parser product identity."""

    parsed_input: ParsedEquationInput
    provenance: EquationProvenance
    free_variables: EquationFreeVariables
    _contract: _ValidatedEquationContract = field(repr=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError("ValidatedEquationInput is created by equation validation.")


def validate_equation_candidate(
    candidate: EquationCandidate,
    normalized_input: NormalizedInput,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> ValidatedEquationInput:
    """Validate and seal one complete parser-produced equation candidate."""

    if type(candidate) is not EquationCandidate:
        raise TypeError("candidate must be an exact EquationCandidate.")
    if type(normalized_input) is not NormalizedInput:
        raise TypeError("normalized_input must be an exact NormalizedInput.")
    if type(limits) is not ApplicationLimits:
        raise TypeError("limits must be an exact ApplicationLimits.")
    if type(normalized_input.source_map) is not SourceMap:
        raise TypeError("normalized_input.source_map must be an exact SourceMap.")
    if type(candidate.parsed_input) is not ParsedEquationInput:
        raise TypeError("candidate.parsed_input must be an exact ParsedEquationInput.")
    EquationCandidate.__post_init__(candidate)

    provenance, free_variables = _validate_parser_product(
        candidate.parsed_input,
        normalized_input,
        limits=limits,
        replay=True,
    )
    contract = _issue_contract(
        parsed_input=candidate.parsed_input,
        normalized_input=normalized_input,
        provenance=provenance,
        free_variables=free_variables,
        limits=limits,
    )
    return _create_receipt(
        parsed_input=candidate.parsed_input,
        provenance=provenance,
        free_variables=free_variables,
        contract=contract,
        limits=limits,
    )


def _validate_validated_equation_input(
    value: object,
    *,
    limits: ApplicationLimits,
) -> ValidatedEquationInput:
    """Revalidate every receipt binding before a later stage consumes it."""

    if type(value) is not ValidatedEquationInput:
        raise TypeError("value must be an exact ValidatedEquationInput.")
    if type(limits) is not ApplicationLimits:
        raise TypeError("limits must be an exact ApplicationLimits.")
    _validate_limits(limits)

    contract = getattr(value, "_contract", None)
    if type(contract) is not _ValidatedEquationContract:
        raise TypeError("validated equation input is missing its issued contract.")
    _validate_contract(contract)
    if getattr(value, "parsed_input", None) is not contract.parsed_input:
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if getattr(value, "provenance", None) is not contract.provenance:
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    free_variables = getattr(value, "free_variables", None)
    if type(free_variables) is not tuple:
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_RESTRICTED_AST,
        )
    if free_variables != contract.free_variables:
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_RESTRICTED_AST,
        )
    if contract.limits_version != limits.version:
        raise EquationValidationError(
            EquationValidationFailureKind.LIMITS_VERSION_MISMATCH,
        )

    active_profile = _input_limits_profile(limits)
    if active_profile != contract._limits_profile:
        raise EquationValidationError(
            EquationValidationFailureKind.INCOMPATIBLE_LIMITS_CONTRACT,
        )

    expected_provenance, expected_variables = _validate_parser_product(
        contract.parsed_input,
        contract.normalized_input,
        limits=limits,
        replay=False,
    )
    current_normalized_snapshot = _normalized_input_snapshot(
        contract.normalized_input,
    )
    if not _normalized_input_snapshot_matches(
        current_normalized_snapshot,
        contract._normalized_input_snapshot,
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    current_parsed_snapshot = _parsed_input_snapshot(
        contract.parsed_input,
        expected_variables,
        limits=limits,
    )
    if not _metrics_snapshot_matches(
        current_parsed_snapshot.metrics,
        contract._parsed_input_snapshot.metrics,
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_PARSER_METRICS,
        )
    if not _parsed_input_snapshot_matches(
        current_parsed_snapshot,
        contract._parsed_input_snapshot,
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    current_provenance_snapshot = _provenance_snapshot(value.provenance)
    if not _provenance_snapshot_matches_current(
        current_provenance_snapshot,
        contract._provenance_snapshot,
    ) or not _provenance_snapshot_matches_expected(
        contract._provenance_snapshot,
        expected_provenance,
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if expected_variables != free_variables:
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_RESTRICTED_AST,
        )
    return value


def _validate_parser_product(
    parsed_input: ParsedEquationInput,
    normalized_input: NormalizedInput,
    *,
    limits: ApplicationLimits,
    replay: bool,
) -> tuple[EquationProvenance, EquationFreeVariables]:
    _validate_limits(limits)
    _validate_normalized_input(normalized_input, limits=limits)
    if type(parsed_input) is not ParsedEquationInput:
        raise TypeError("parsed_input must be an exact ParsedEquationInput.")
    if type(parsed_input.metrics) is not ParseMetrics:
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_PARSER_METRICS,
        )

    metrics = parsed_input.metrics
    _validate_metrics_scalars(metrics)
    if metrics.limits_version != limits.version:
        raise EquationValidationError(
            EquationValidationFailureKind.LIMITS_VERSION_MISMATCH,
        )

    equation_span, equation_source_span = _validate_equation_spans(
        parsed_input,
        normalized_input,
    )
    ast_limits, free_variables = _validate_ast_graph(
        parsed_input,
        normalized_input.source_map,
        limits=limits,
    )
    (
        ast_node_count,
        max_ast_depth,
        max_function_arguments,
        max_absolute_literal_exponent,
        max_numeric_digits,
        max_decimal_places,
        max_rational_numerator_digits,
        max_rational_denominator_digits,
    ) = ast_limits
    if (
        metrics.ast_node_count,
        metrics.max_ast_depth,
        metrics.max_function_arguments,
        metrics.max_absolute_literal_exponent,
    ) != (
        ast_node_count,
        max_ast_depth,
        max_function_arguments,
        max_absolute_literal_exponent,
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_PARSER_METRICS,
            equation_span,
            equation_source_span,
        )
    try:
        limits.validate_input_complexity(
            character_count=len(normalized_input.source_map.original_text),
            token_count=metrics.token_count,
            ast_node_count=metrics.ast_node_count,
            nesting_depth=metrics.max_ast_depth,
            numeric_digits=max_numeric_digits,
            decimal_places=max_decimal_places,
            rational_numerator_digits=max_rational_numerator_digits,
            rational_denominator_digits=max_rational_denominator_digits,
            absolute_exponent=metrics.max_absolute_literal_exponent,
            function_arguments=metrics.max_function_arguments,
        )
    except (TypeError, ValueError):
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_PARSER_METRICS,
            equation_span,
            equation_source_span,
        ) from None

    if replay:
        replayed = _replay_parser(normalized_input, limits=limits)
        if replayed.metrics != parsed_input.metrics:
            raise EquationValidationError(
                EquationValidationFailureKind.INVALID_PARSER_METRICS,
                equation_span,
                equation_source_span,
            )
        if (
            replayed.left != parsed_input.left
            or replayed.right != parsed_input.right
            or replayed.left_normalized_span != parsed_input.left_normalized_span
            or replayed.right_normalized_span != parsed_input.right_normalized_span
            or replayed.left_source_span != parsed_input.left_source_span
            or replayed.right_source_span != parsed_input.right_source_span
        ):
            raise EquationValidationError(
                EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
                equation_span,
                equation_source_span,
            )

    provenance = EquationProvenance(
        normalized_input=normalized_input.text,
        normalized_span=equation_span,
        source_span=equation_source_span,
        limits_version=limits.version,
    )
    try:
        EquationProvenance.__post_init__(provenance)
    except (TypeError, ValueError):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        ) from None
    return provenance, free_variables


def _validate_limits(limits: ApplicationLimits) -> None:
    try:
        ApplicationLimits.__post_init__(limits)
    except (TypeError, ValueError):
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_PARSER_METRICS,
        ) from None


def _validate_normalized_input(
    normalized_input: NormalizedInput,
    *,
    limits: ApplicationLimits,
) -> None:
    source_map = normalized_input.source_map
    if type(source_map) is not SourceMap:
        raise TypeError("normalized_input.source_map must be an exact SourceMap.")
    if type(normalized_input.text) is not str:
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if type(source_map.original_text) is not str:
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if len(source_map.original_text) > limits.max_input_characters:
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if len(normalized_input.text) > 2 * limits.max_input_characters:
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if type(source_map.character_spans) is not tuple:
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if len(source_map.character_spans) != len(normalized_input.text):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    for span in source_map.character_spans:
        if type(span) is not SourceSpan:
            raise EquationValidationError(
                EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
            )
        try:
            SourceSpan.__post_init__(span)
        except (TypeError, ValueError):
            raise EquationValidationError(
                EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
            ) from None
    try:
        SourceMap.__post_init__(source_map)
        NormalizedInput.__post_init__(normalized_input)
    except (TypeError, ValueError):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        ) from None


def _validate_metrics_scalars(metrics: ParseMetrics) -> None:
    integer_fields = (
        metrics.token_count,
        metrics.ast_node_count,
        metrics.max_ast_depth,
        metrics.max_function_arguments,
        metrics.max_absolute_literal_exponent,
    )
    if any(type(value) is not int or value < 0 for value in integer_fields):
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_PARSER_METRICS,
        )
    if type(metrics.limits_version) is not str or not metrics.limits_version:
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_PARSER_METRICS,
        )


def _validate_equation_spans(
    parsed_input: ParsedEquationInput,
    normalized_input: NormalizedInput,
) -> tuple[SourceSpan, SourceSpan]:
    span_pairs = (
        (parsed_input.left_normalized_span, parsed_input.left_source_span),
        (parsed_input.right_normalized_span, parsed_input.right_source_span),
    )
    for normalized_span, source_span in span_pairs:
        if type(normalized_span) is not SourceSpan or type(source_span) is not SourceSpan:
            raise EquationValidationError(
                EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
            )
        try:
            SourceSpan.__post_init__(normalized_span)
            SourceSpan.__post_init__(source_span)
        except (TypeError, ValueError):
            raise EquationValidationError(
                EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
            ) from None
        if normalized_span.start == normalized_span.end:
            raise EquationValidationError(
                EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
            )

    left = parsed_input.left_normalized_span
    right = parsed_input.right_normalized_span
    text = normalized_input.text
    if (
        left.start != 0
        or right.end != len(text)
        or left.end >= right.start
        or text[left.end : right.start] != "="
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if (
        _exact_node(parsed_input.left)
        and parsed_input.left.normalized_span != left
    ) or (
        _exact_node(parsed_input.right)
        and parsed_input.right.normalized_span != right
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )

    source_map = normalized_input.source_map
    try:
        expected_left_source = source_map.map_normalized_span(left)
        expected_right_source = source_map.map_normalized_span(right)
    except (IndexError, TypeError, ValueError):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        ) from None
    if (
        parsed_input.left_source_span != expected_left_source
        or parsed_input.right_source_span != expected_right_source
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )

    equation_span = SourceSpan(left.start, right.end)
    equation_source_span = source_map.map_normalized_span(equation_span)
    return equation_span, equation_source_span


def _validate_ast_graph(
    parsed_input: ParsedEquationInput,
    source_map: SourceMap,
    *,
    limits: ApplicationLimits,
) -> tuple[_AstLimitMetrics, EquationFreeVariables]:
    pending: list[tuple[object, SourceSpan, bool]] = [
        (parsed_input.right, parsed_input.right_normalized_span, False),
        (parsed_input.left, parsed_input.left_normalized_span, False),
    ]
    visited: set[int] = set()
    depths: dict[int, int] = {}
    variables: set[str] = set()
    max_arguments = 0
    max_exponent = 0
    max_numeric_digits = 0
    max_decimal_places = 0
    max_rational_numerator_digits = 0
    max_rational_denominator_digits = 0

    while pending:
        value, side_span, exiting = pending.pop()
        if not exiting:
            if not _exact_node(value):
                raise EquationValidationError(
                    EquationValidationFailureKind.INVALID_RESTRICTED_AST,
                )
            node = value
            identity = id(node)
            if identity in visited:
                raise EquationValidationError(
                    EquationValidationFailureKind.INVALID_RESTRICTED_AST,
                    *_trusted_node_spans(node, source_map),
                )
            visited.add(identity)
            if len(visited) > limits.max_ast_nodes:
                raise EquationValidationError(
                    EquationValidationFailureKind.INVALID_RESTRICTED_AST,
                )
            _validate_node_shallow(node, side_span, source_map, limits=limits)
            pending.append((node, side_span, True))
            children = _node_children(node)
            _validate_child_spans(node, children)
            pending.extend((child, side_span, False) for child in reversed(children))
            if type(node) is SymbolNode:
                variables.add(node.name)
            if type(node) is FunctionCallNode:
                max_arguments = max(max_arguments, len(node.arguments))
            if type(node) is NumberNode:
                numeric_digits, decimal_places = _number_lexeme_limits(node.lexeme)
                max_numeric_digits = max(max_numeric_digits, numeric_digits)
                max_decimal_places = max(max_decimal_places, decimal_places)
            continue

        node = value
        if not _exact_node(node):
            raise EquationValidationError(
                EquationValidationFailureKind.INVALID_RESTRICTED_AST,
            )
        children = _node_children(node)
        depth = 1 + max((depths[id(child)] for child in children), default=0)
        if depth > limits.max_nesting_depth:
            raise EquationValidationError(
                EquationValidationFailureKind.INVALID_RESTRICTED_AST,
                *_trusted_node_spans(node, source_map),
            )
        depths[id(node)] = depth
        if type(node) is BinaryOpNode and node.operator is BinaryOperator.POWER:
            max_exponent = max(
                max_exponent,
                _direct_literal_exponent(node.right, limits),
            )
        if type(node) is BinaryOpNode and node.operator is BinaryOperator.DIVIDE:
            numerator = _signed_integer_literal(node.left)
            if numerator is not None:
                max_rational_numerator_digits = max(
                    max_rational_numerator_digits,
                    _ascii_digit_count(numerator.lexeme),
                )
            denominator = _signed_integer_literal(node.right)
            if denominator is not None:
                max_rational_denominator_digits = max(
                    max_rational_denominator_digits,
                    _ascii_digit_count(denominator.lexeme),
                )

    root_depth = max(depths[id(parsed_input.left)], depths[id(parsed_input.right)])
    free_variables: EquationFreeVariables = tuple(
        variable for variable in ("x", "y") if variable in variables
    )
    return (
        (
            len(visited),
            root_depth,
            max_arguments,
            max_exponent,
            max_numeric_digits,
            max_decimal_places,
            max_rational_numerator_digits,
            max_rational_denominator_digits,
        ),
        free_variables,
    )


def _validate_node_shallow(
    node: RestrictedExpression,
    side_span: SourceSpan,
    source_map: SourceMap,
    *,
    limits: ApplicationLimits,
) -> None:
    if type(node.normalized_span) is not SourceSpan or type(node.source_span) is not SourceSpan:
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_RESTRICTED_AST,
        )
    try:
        SourceSpan.__post_init__(node.normalized_span)
        SourceSpan.__post_init__(node.source_span)
    except (TypeError, ValueError):
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_RESTRICTED_AST,
        ) from None
    if (
        node.normalized_span.start < side_span.start
        or node.normalized_span.end > side_span.end
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_RESTRICTED_AST,
            *_trusted_node_spans(node, source_map),
        )
    try:
        expected_source = source_map.map_normalized_span(node.normalized_span)
    except (IndexError, TypeError, ValueError):
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_RESTRICTED_AST,
        ) from None
    if node.source_span != expected_source:
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_RESTRICTED_AST,
            node.normalized_span,
            None,
        )
    if type(node) is NumberNode and (
        type(node.lexeme) is not str
        or len(node.lexeme) > limits.max_numeric_digits + 1
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_RESTRICTED_AST,
            node.normalized_span,
            node.source_span,
        )
    if type(node) in {SymbolNode, ConstantNode, FunctionCallNode}:
        if type(node.name) is not str or len(node.name) > limits.max_input_characters:
            raise EquationValidationError(
                EquationValidationFailureKind.INVALID_RESTRICTED_AST,
                node.normalized_span,
                node.source_span,
            )
    if type(node) is FunctionCallNode:
        if type(node.arguments) is not tuple:
            raise EquationValidationError(
                EquationValidationFailureKind.INVALID_RESTRICTED_AST,
                node.normalized_span,
                node.source_span,
            )
        if len(node.arguments) > limits.max_function_arguments:
            raise EquationValidationError(
                EquationValidationFailureKind.INVALID_RESTRICTED_AST,
                node.normalized_span,
                node.source_span,
            )
    try:
        type(node).__post_init__(node)
    except (TypeError, ValueError):
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_RESTRICTED_AST,
            node.normalized_span,
            node.source_span,
        ) from None


def _validate_child_spans(
    parent: RestrictedExpression,
    children: tuple[RestrictedExpression, ...],
) -> None:
    previous: RestrictedExpression | None = None
    for child in children:
        if not _exact_node(child):
            raise EquationValidationError(
                EquationValidationFailureKind.INVALID_RESTRICTED_AST,
            )
        if (
            type(child.normalized_span) is not SourceSpan
            or type(child.source_span) is not SourceSpan
        ):
            raise EquationValidationError(
                EquationValidationFailureKind.INVALID_RESTRICTED_AST,
            )
        if (
            child.normalized_span.start < parent.normalized_span.start
            or child.normalized_span.end > parent.normalized_span.end
            or child.source_span.start < parent.source_span.start
            or child.source_span.end > parent.source_span.end
        ):
            raise EquationValidationError(
                EquationValidationFailureKind.INVALID_RESTRICTED_AST,
            )
        if previous is not None and (
            previous.normalized_span.end > child.normalized_span.start
            or previous.source_span.end > child.source_span.start
        ):
            raise EquationValidationError(
                EquationValidationFailureKind.INVALID_RESTRICTED_AST,
            )
        previous = child


def _node_children(node: RestrictedExpression) -> tuple[RestrictedExpression, ...]:
    if type(node) is UnaryOpNode:
        return (node.operand,)
    if type(node) is BinaryOpNode:
        return (node.left, node.right)
    if type(node) is FunctionCallNode:
        return node.arguments
    return ()


def _ascii_digit_count(lexeme: str) -> int:
    return sum(character.isascii() and character.isdigit() for character in lexeme)


def _number_lexeme_limits(lexeme: str) -> tuple[int, int]:
    """Recompute tokenizer numeric counts from one validated NUMBER lexeme."""

    dot = lexeme.find(".")
    decimal_places = (
        _ascii_digit_count(lexeme[dot + 1 :])
        if dot >= 0
        else 0
    )
    return _ascii_digit_count(lexeme), decimal_places


def _signed_integer_literal(expression: RestrictedExpression) -> NumberNode | None:
    """Mirror the parser's signed-integer-literal rule without tokenizing."""

    if type(expression) is NumberNode and "." not in expression.lexeme:
        return expression
    if (
        type(expression) is UnaryOpNode
        and expression.operator in {UnaryOperator.POSITIVE, UnaryOperator.NEGATIVE}
        and type(expression.operand) is NumberNode
        and "." not in expression.operand.lexeme
    ):
        return expression.operand
    return None


def _direct_literal_exponent(
    expression: RestrictedExpression,
    limits: ApplicationLimits,
) -> int:
    literal: NumberNode | None = None
    if type(expression) is NumberNode:
        literal = expression
    elif type(expression) is UnaryOpNode and type(expression.operand) is NumberNode:
        literal = expression.operand
    if literal is None or "." in literal.lexeme:
        return 0
    significant = literal.lexeme.lstrip("0")
    if not significant:
        return 0
    maximum = str(limits.max_absolute_exponent)
    if len(significant) > len(maximum) or (
        len(significant) == len(maximum) and significant > maximum
    ):
        return limits.max_absolute_exponent + 1
    return int(significant)


def _input_limits_profile(limits: ApplicationLimits) -> _InputLimitsProfile:
    return _InputLimitsProfile(
        version=limits.version,
        max_input_characters=limits.max_input_characters,
        max_tokens=limits.max_tokens,
        max_ast_nodes=limits.max_ast_nodes,
        max_nesting_depth=limits.max_nesting_depth,
        max_numeric_digits=limits.max_numeric_digits,
        max_decimal_places=limits.max_decimal_places,
        max_rational_numerator_digits=limits.max_rational_numerator_digits,
        max_rational_denominator_digits=limits.max_rational_denominator_digits,
        max_absolute_exponent=limits.max_absolute_exponent,
        max_function_arguments=limits.max_function_arguments,
    )


def _profile_snapshot(profile: _InputLimitsProfile) -> _LimitsProfileValues:
    return (
        profile.version,
        profile.max_input_characters,
        profile.max_tokens,
        profile.max_ast_nodes,
        profile.max_nesting_depth,
        profile.max_numeric_digits,
        profile.max_decimal_places,
        profile.max_rational_numerator_digits,
        profile.max_rational_denominator_digits,
        profile.max_absolute_exponent,
        profile.max_function_arguments,
    )


def _span_snapshot(span: SourceSpan) -> _SpanSnapshot:
    return _SpanSnapshot(span, id(span), span.start, span.end)


def _span_snapshot_matches(
    current: _SpanSnapshot,
    issued: _SpanSnapshot,
) -> bool:
    return (
        current.span is issued.span
        and current.identity == issued.identity
        and current.identity == id(current.span)
        and current.start == issued.start
        and current.end == issued.end
    )


def _metrics_snapshot(metrics: ParseMetrics) -> _MetricsSnapshot:
    return _MetricsSnapshot(
        metrics=metrics,
        identity=id(metrics),
        token_count=metrics.token_count,
        ast_node_count=metrics.ast_node_count,
        max_ast_depth=metrics.max_ast_depth,
        max_function_arguments=metrics.max_function_arguments,
        max_absolute_literal_exponent=metrics.max_absolute_literal_exponent,
        limits_version=metrics.limits_version,
    )


def _metrics_snapshot_matches(
    current: _MetricsSnapshot,
    issued: _MetricsSnapshot,
) -> bool:
    return (
        current.metrics is issued.metrics
        and current.identity == issued.identity
        and current.identity == id(current.metrics)
        and current.token_count == issued.token_count
        and current.ast_node_count == issued.ast_node_count
        and current.max_ast_depth == issued.max_ast_depth
        and current.max_function_arguments == issued.max_function_arguments
        and current.max_absolute_literal_exponent
        == issued.max_absolute_literal_exponent
        and current.limits_version == issued.limits_version
    )


def _source_map_snapshot(source_map: SourceMap) -> _SourceMapSnapshot:
    spans = source_map.character_spans
    return _SourceMapSnapshot(
        source_map=source_map,
        identity=id(source_map),
        original_text=source_map.original_text,
        normalized_text=source_map.normalized_text,
        character_spans=spans,
        character_spans_identity=id(spans),
        character_spans_length=len(spans),
        character_span_snapshots=tuple(_span_snapshot(span) for span in spans),
    )


def _source_map_snapshot_matches(
    current: _SourceMapSnapshot,
    issued: _SourceMapSnapshot,
) -> bool:
    return (
        current.source_map is issued.source_map
        and current.identity == issued.identity
        and current.identity == id(current.source_map)
        and current.original_text == issued.original_text
        and current.normalized_text == issued.normalized_text
        and current.character_spans is issued.character_spans
        and current.character_spans_identity == issued.character_spans_identity
        and current.character_spans_identity == id(current.character_spans)
        and current.character_spans_length == issued.character_spans_length
        and current.character_spans_length == len(current.character_spans)
        and len(current.character_span_snapshots)
        == len(issued.character_span_snapshots)
        and all(
            _span_snapshot_matches(current_span, issued_span)
            for current_span, issued_span in zip(
                current.character_span_snapshots,
                issued.character_span_snapshots,
                strict=True,
            )
        )
    )


def _normalized_input_snapshot(
    normalized_input: NormalizedInput,
) -> _NormalizedInputSnapshot:
    source_map = normalized_input.source_map
    return _NormalizedInputSnapshot(
        normalized_input=normalized_input,
        identity=id(normalized_input),
        text=normalized_input.text,
        source_map=source_map,
        source_map_identity=id(source_map),
        source_map_snapshot=_source_map_snapshot(source_map),
    )


def _normalized_input_snapshot_matches(
    current: _NormalizedInputSnapshot,
    issued: _NormalizedInputSnapshot,
) -> bool:
    return (
        current.normalized_input is issued.normalized_input
        and current.identity == issued.identity
        and current.identity == id(current.normalized_input)
        and current.text == issued.text
        and current.source_map is issued.source_map
        and current.source_map_identity == issued.source_map_identity
        and current.source_map_identity == id(current.source_map)
        and _source_map_snapshot_matches(
            current.source_map_snapshot,
            issued.source_map_snapshot,
        )
    )


def _node_payload_snapshot(node: RestrictedExpression) -> _NodePayloadSnapshot:
    if type(node) is NumberNode:
        return _NumberPayloadSnapshot(node.lexeme)
    if type(node) is SymbolNode:
        return _SymbolPayloadSnapshot(node.name)
    if type(node) is ConstantNode:
        return _ConstantPayloadSnapshot(node.name)
    if type(node) is UnaryOpNode:
        return _UnaryPayloadSnapshot(node.operator)
    if type(node) is BinaryOpNode:
        return _BinaryPayloadSnapshot(node.operator, node.implicit)
    if type(node) is FunctionCallNode:
        return _FunctionPayloadSnapshot(node.name)
    raise EquationValidationError(
        EquationValidationFailureKind.INVALID_RESTRICTED_AST,
    )


def _ast_snapshot(
    expression: RestrictedExpression,
    *,
    max_nodes: int,
) -> _AstGraphSnapshot:
    occurrences: list[_AstOccurrenceSnapshot] = []
    pending = [expression]
    visited: set[int] = set()
    while pending:
        node = pending.pop()
        identity = id(node)
        if identity in visited or len(visited) >= max_nodes or not _exact_node(node):
            raise EquationValidationError(
                EquationValidationFailureKind.INVALID_RESTRICTED_AST,
            )
        visited.add(identity)
        children = _node_children(node)
        arguments = node.arguments if type(node) is FunctionCallNode else None
        occurrences.append(
            _AstOccurrenceSnapshot(
                node=node,
                identity=identity,
                node_type=type(node),
                normalized_span=_span_snapshot(node.normalized_span),
                source_span=_span_snapshot(node.source_span),
                payload=_node_payload_snapshot(node),
                children=children,
                child_identities=tuple(id(child) for child in children),
                child_count=len(children),
                arguments=arguments,
                arguments_identity=id(arguments) if arguments is not None else None,
                arguments_length=len(arguments) if arguments is not None else None,
            ),
        )
        pending.extend(reversed(children))
    return _AstGraphSnapshot(tuple(occurrences))


def _ast_snapshot_matches(
    current: _AstGraphSnapshot,
    issued: _AstGraphSnapshot,
) -> bool:
    if len(current.occurrences) != len(issued.occurrences):
        return False
    for current_node, issued_node in zip(
        current.occurrences,
        issued.occurrences,
        strict=True,
    ):
        if (
            current_node.node is not issued_node.node
            or current_node.identity != issued_node.identity
            or current_node.identity != id(current_node.node)
            or current_node.node_type is not issued_node.node_type
            or not _span_snapshot_matches(
                current_node.normalized_span,
                issued_node.normalized_span,
            )
            or not _span_snapshot_matches(
                current_node.source_span,
                issued_node.source_span,
            )
            or current_node.payload != issued_node.payload
            or len(current_node.children) != len(issued_node.children)
            or current_node.child_identities != issued_node.child_identities
            or current_node.child_count != issued_node.child_count
            or current_node.child_count != len(current_node.children)
            or any(
                current_child is not issued_child
                for current_child, issued_child in zip(
                    current_node.children,
                    issued_node.children,
                    strict=True,
                )
            )
            or current_node.arguments is not issued_node.arguments
            or current_node.arguments_identity != issued_node.arguments_identity
            or current_node.arguments_length != issued_node.arguments_length
            or (
                current_node.arguments is not None
                and (
                    current_node.arguments_identity != id(current_node.arguments)
                    or current_node.arguments_length != len(current_node.arguments)
                )
            )
        ):
            return False
    return True


def _parsed_input_snapshot(
    parsed_input: ParsedEquationInput,
    free_variables: EquationFreeVariables,
    *,
    limits: ApplicationLimits,
) -> _ParsedInputSnapshot:
    return _ParsedInputSnapshot(
        parsed_input=parsed_input,
        identity=id(parsed_input),
        left=parsed_input.left,
        left_identity=id(parsed_input.left),
        right=parsed_input.right,
        right_identity=id(parsed_input.right),
        metrics=_metrics_snapshot(parsed_input.metrics),
        left_normalized_span=_span_snapshot(parsed_input.left_normalized_span),
        right_normalized_span=_span_snapshot(parsed_input.right_normalized_span),
        left_source_span=_span_snapshot(parsed_input.left_source_span),
        right_source_span=_span_snapshot(parsed_input.right_source_span),
        left_ast=_ast_snapshot(parsed_input.left, max_nodes=limits.max_ast_nodes),
        right_ast=_ast_snapshot(parsed_input.right, max_nodes=limits.max_ast_nodes),
        free_variables=free_variables,
    )


def _parsed_input_snapshot_matches(
    current: _ParsedInputSnapshot,
    issued: _ParsedInputSnapshot,
) -> bool:
    return (
        current.parsed_input is issued.parsed_input
        and current.identity == issued.identity
        and current.identity == id(current.parsed_input)
        and current.left is issued.left
        and current.left_identity == issued.left_identity
        and current.left_identity == id(current.left)
        and current.right is issued.right
        and current.right_identity == issued.right_identity
        and current.right_identity == id(current.right)
        and _metrics_snapshot_matches(current.metrics, issued.metrics)
        and _span_snapshot_matches(
            current.left_normalized_span,
            issued.left_normalized_span,
        )
        and _span_snapshot_matches(
            current.right_normalized_span,
            issued.right_normalized_span,
        )
        and _span_snapshot_matches(current.left_source_span, issued.left_source_span)
        and _span_snapshot_matches(
            current.right_source_span,
            issued.right_source_span,
        )
        and _ast_snapshot_matches(current.left_ast, issued.left_ast)
        and _ast_snapshot_matches(current.right_ast, issued.right_ast)
        and current.free_variables == issued.free_variables
    )


def _provenance_snapshot(provenance: EquationProvenance) -> _ProvenanceSnapshot:
    return _ProvenanceSnapshot(
        provenance=provenance,
        identity=id(provenance),
        normalized_input=provenance.normalized_input,
        normalized_span=_span_snapshot(provenance.normalized_span),
        source_span=_span_snapshot(provenance.source_span),
        limits_version=provenance.limits_version,
    )


def _provenance_snapshot_matches_current(
    current: _ProvenanceSnapshot,
    issued: _ProvenanceSnapshot,
) -> bool:
    return (
        current.provenance is issued.provenance
        and current.identity == issued.identity
        and current.identity == id(current.provenance)
        and current.normalized_input == issued.normalized_input
        and _span_snapshot_matches(current.normalized_span, issued.normalized_span)
        and _span_snapshot_matches(current.source_span, issued.source_span)
        and current.limits_version == issued.limits_version
    )


def _provenance_snapshot_matches_expected(
    issued: _ProvenanceSnapshot,
    expected: EquationProvenance,
) -> bool:
    return (
        expected.normalized_input == issued.normalized_input
        and expected.normalized_span.start == issued.normalized_span.start
        and expected.normalized_span.end == issued.normalized_span.end
        and expected.source_span.start == issued.source_span.start
        and expected.source_span.end == issued.source_span.end
        and expected.limits_version == issued.limits_version
    )


def _replay_parser(
    normalized_input: NormalizedInput,
    *,
    limits: ApplicationLimits,
) -> ParsedEquationInput:
    tokens = tokenize(normalized_input, limits=limits)
    if isinstance(tokens, ErrorInfo):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    split = split_equation(tokens)
    if isinstance(split, ErrorInfo):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    parsed = parse_input(split, limits=limits)
    if isinstance(parsed, ErrorInfo) or type(parsed) is not ParsedEquationInput:
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    return parsed


def _issue_contract(
    *,
    parsed_input: ParsedEquationInput,
    normalized_input: NormalizedInput,
    provenance: EquationProvenance,
    free_variables: EquationFreeVariables,
    limits: ApplicationLimits,
) -> _ValidatedEquationContract:
    profile = _input_limits_profile(limits)
    contract = object.__new__(_ValidatedEquationContract)
    object.__setattr__(contract, "parsed_input", parsed_input)
    object.__setattr__(contract, "normalized_input", normalized_input)
    object.__setattr__(contract, "source_map", normalized_input.source_map)
    object.__setattr__(contract, "provenance", provenance)
    object.__setattr__(contract, "free_variables", free_variables)
    object.__setattr__(contract, "limits_version", profile.version)
    object.__setattr__(contract, "_limits_profile", profile)
    object.__setattr__(contract, "_parsed_input_identity", id(parsed_input))
    object.__setattr__(contract, "_normalized_input_identity", id(normalized_input))
    object.__setattr__(contract, "_source_map_identity", id(normalized_input.source_map))
    object.__setattr__(contract, "_provenance_identity", id(provenance))
    object.__setattr__(contract, "_limits_profile_identity", id(profile))
    object.__setattr__(contract, "_limits_version_snapshot", profile.version)
    object.__setattr__(contract, "_limits_profile_snapshot", _profile_snapshot(profile))
    object.__setattr__(
        contract,
        "_normalized_input_snapshot",
        _normalized_input_snapshot(normalized_input),
    )
    object.__setattr__(
        contract,
        "_parsed_input_snapshot",
        _parsed_input_snapshot(
            parsed_input,
            free_variables,
            limits=limits,
        ),
    )
    object.__setattr__(
        contract,
        "_provenance_snapshot",
        _provenance_snapshot(provenance),
    )
    object.__setattr__(contract, "_seal", _SEAL)
    _validate_contract(contract)
    return contract


def _validate_contract(contract: _ValidatedEquationContract) -> None:
    if type(contract) is not _ValidatedEquationContract:
        raise TypeError("contract must be an exact _ValidatedEquationContract.")
    if getattr(contract, "_seal", None) is not _SEAL:
        raise TypeError("validated equation contract has an invalid seal.")
    parsed_input = getattr(contract, "parsed_input", None)
    normalized_input = getattr(contract, "normalized_input", None)
    source_map = getattr(contract, "source_map", None)
    provenance = getattr(contract, "provenance", None)
    free_variables = getattr(contract, "free_variables", None)
    limits_version = getattr(contract, "limits_version", None)
    limits_profile = getattr(contract, "_limits_profile", None)
    if type(parsed_input) is not ParsedEquationInput:
        raise TypeError("validated equation contract has an invalid parser product.")
    if id(parsed_input) != getattr(contract, "_parsed_input_identity", None):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if type(normalized_input) is not NormalizedInput:
        raise TypeError("validated equation contract has an invalid normalized input.")
    if id(normalized_input) != getattr(
        contract,
        "_normalized_input_identity",
        None,
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if type(source_map) is not SourceMap:
        raise TypeError("validated equation contract has an invalid source map.")
    if id(source_map) != getattr(contract, "_source_map_identity", None):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if normalized_input.source_map is not source_map:
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if type(provenance) is not EquationProvenance:
        raise TypeError("validated equation contract has invalid provenance.")
    if id(provenance) != getattr(contract, "_provenance_identity", None):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    if type(free_variables) is not tuple or free_variables not in {
        (),
        ("x",),
        ("y",),
        ("x", "y"),
    }:
        raise EquationValidationError(
            EquationValidationFailureKind.INVALID_RESTRICTED_AST,
        )
    if type(limits_profile) is not _InputLimitsProfile:
        raise EquationValidationError(
            EquationValidationFailureKind.INCOMPATIBLE_LIMITS_CONTRACT,
        )
    if id(limits_profile) != getattr(contract, "_limits_profile_identity", None):
        raise EquationValidationError(
            EquationValidationFailureKind.INCOMPATIBLE_LIMITS_CONTRACT,
        )
    try:
        profile_snapshot = _profile_snapshot(limits_profile)
    except (AttributeError, TypeError):
        raise EquationValidationError(
            EquationValidationFailureKind.INCOMPATIBLE_LIMITS_CONTRACT,
        ) from None
    if profile_snapshot != getattr(contract, "_limits_profile_snapshot", None):
        raise EquationValidationError(
            EquationValidationFailureKind.INCOMPATIBLE_LIMITS_CONTRACT,
        )
    if type(limits_version) is not str or not limits_version:
        raise EquationValidationError(
            EquationValidationFailureKind.LIMITS_VERSION_MISMATCH,
        )
    if limits_version != getattr(contract, "_limits_version_snapshot", None):
        raise EquationValidationError(
            EquationValidationFailureKind.LIMITS_VERSION_MISMATCH,
        )
    if limits_profile.version != limits_version:
        raise EquationValidationError(
            EquationValidationFailureKind.LIMITS_VERSION_MISMATCH,
        )
    normalized_snapshot = getattr(contract, "_normalized_input_snapshot", None)
    parsed_snapshot = getattr(contract, "_parsed_input_snapshot", None)
    provenance_snapshot = getattr(contract, "_provenance_snapshot", None)
    if (
        type(normalized_snapshot) is not _NormalizedInputSnapshot
        or normalized_snapshot.normalized_input is not normalized_input
        or normalized_snapshot.identity != id(normalized_input)
        or normalized_snapshot.source_map is not source_map
        or normalized_snapshot.source_map_identity != id(source_map)
        or type(parsed_snapshot) is not _ParsedInputSnapshot
        or parsed_snapshot.parsed_input is not parsed_input
        or parsed_snapshot.identity != id(parsed_input)
        or parsed_snapshot.free_variables != free_variables
        or type(provenance_snapshot) is not _ProvenanceSnapshot
        or provenance_snapshot.provenance is not provenance
        or provenance_snapshot.identity != id(provenance)
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )
    try:
        EquationProvenance.__post_init__(provenance)
    except (TypeError, ValueError):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        ) from None
    if (
        provenance.normalized_input != normalized_input.text
        or provenance.limits_version != limits_version
    ):
        raise EquationValidationError(
            EquationValidationFailureKind.PARSER_PROVENANCE_MISMATCH,
        )


def _create_receipt(
    *,
    parsed_input: ParsedEquationInput,
    provenance: EquationProvenance,
    free_variables: EquationFreeVariables,
    contract: _ValidatedEquationContract,
    limits: ApplicationLimits,
) -> ValidatedEquationInput:
    _validate_contract(contract)
    result = object.__new__(ValidatedEquationInput)
    object.__setattr__(result, "parsed_input", parsed_input)
    object.__setattr__(result, "provenance", provenance)
    object.__setattr__(result, "free_variables", free_variables)
    object.__setattr__(result, "_contract", contract)
    return _validate_validated_equation_input(result, limits=limits)


def _exact_node(value: object) -> TypeGuard[RestrictedExpression]:
    return type(value) in _EXACT_NODE_TYPES


def _trusted_node_spans(
    node: RestrictedExpression,
    source_map: SourceMap,
) -> tuple[SourceSpan | None, SourceSpan | None]:
    if type(node.normalized_span) is not SourceSpan:
        return None, None
    try:
        SourceSpan.__post_init__(node.normalized_span)
        expected = source_map.map_normalized_span(node.normalized_span)
    except (IndexError, TypeError, ValueError):
        return None, None
    if type(node.source_span) is SourceSpan and node.source_span == expected:
        return node.normalized_span, node.source_span
    return node.normalized_span, None


__all__ = [
    "EquationValidationFailureKind",
    "EquationValidationError",
    "ValidatedEquationInput",
    "validate_equation_candidate",
]
