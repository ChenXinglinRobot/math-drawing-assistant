"""Stage 13E public package and documentation contract tests."""

from __future__ import annotations

from pathlib import Path

import math_drawing_assistant.engine as public_engine
import math_drawing_assistant.models as public_models
from math_drawing_assistant.engine import analyze_plot_item
from math_drawing_assistant.engine.plot_analyzer import (
    analyze_plot_item as implementation_analyze_plot_item,
)
from math_drawing_assistant.models import (
    AxisOrientation,
    CircleSpec,
    EllipseSpec,
    EquationProvenance,
    ErrorCode,
    ErrorInfo,
    ExplicitFunctionSpec,
    HyperbolaSpec,
    InputSource,
    LineSpec,
    ParabolaOpening,
    ParabolaSpec,
    PlotItemRequest,
    PlotItemSpec,
    PlotKind,
    PrimitiveEquationCoefficients,
)
from math_drawing_assistant.models import plot_specs as implementation_plot_specs


_ROOT = Path(__file__).parents[1]
_DOCUMENT_PATH = _ROOT / "docs" / "supported-formulas.md"

_STAGE_13_MODEL_EXPORTS = frozenset(
    {
        "PrimitiveEquationCoefficients",
        "EquationProvenance",
        "AxisOrientation",
        "ParabolaOpening",
        "LineSpec",
        "CircleSpec",
        "EllipseSpec",
        "HyperbolaSpec",
        "ParabolaSpec",
    },
)

_EXPECTED_MODEL_EXPORTS = frozenset(
    {
        "AspectRequest",
        "AxisOrientation",
        "BinaryOpNode",
        "BinaryOperator",
        "CircleSpec",
        "ConstantName",
        "ConstantNode",
        "DEFAULT_EXPLICIT_SAMPLING_POLICY",
        "DEFAULT_LINE_SAMPLING_POLICY",
        "EllipseSpec",
        "EquationProvenance",
        "ErrorCode",
        "ErrorInfo",
        "ExplicitExpressionSource",
        "ExplicitFunctionSpec",
        "ExplicitRenderItemPlan",
        "ExplicitSamplingPolicy",
        "GeometryRenderItemPlan",
        "GeometrySegmentPlan",
        "FunctionCallNode",
        "FunctionName",
        "HyperbolaSpec",
        "InputSource",
        "LineSpec",
        "LineSamplingPolicy",
        "LineSegmentPlan",
        "NumberNode",
        "ParabolaOpening",
        "ParabolaSpec",
        "PlotItemRequest",
        "PlotItemResult",
        "PlotItemSpec",
        "PlotKind",
        "PlotSceneRequest",
        "PlotSceneResult",
        "PlotSceneSpec",
        "PrimitiveEquationCoefficients",
        "PARAMETERIZED_SAMPLER_CONTRACT_VERSION",
        "ParameterIntervalPlan",
        "ParameterizedRenderMemoryBudget",
        "RENDER_PLAN_CONTRACT_VERSION",
        "RenderMemoryBudget",
        "RenderItemPlan",
        "RenderPlan",
        "RestrictedExpression",
        "ResolvedViewport",
        "ResolvedAspect",
        "SegmentClosure",
        "SourceLocatedNode",
        "SourceSpan",
        "StageTiming",
        "SymbolNode",
        "TaskPhase",
        "UnaryOpNode",
        "UnaryOperator",
        "ValidatedExplicitExpression",
        "VariableName",
        "ViewportMode",
        "ViewportRequest",
        "ViewportSource",
        "validate_approved_render_plan",
    },
)

_EXPECTED_ENGINE_EXPORTS = frozenset(
    {
        "APPROVED_CONSTANTS",
        "APPROVED_FUNCTIONS",
        "APPROVED_VARIABLES",
        "CancellationProbe",
        "DenseOscillationMetrics",
        "EquationInput",
        "ExplicitFunctionCandidate",
        "ExplicitValidation",
        "ExpressionInput",
        "Float64Vector",
        "NUMERIC_EXECUTOR_CONTRACT_VERSION",
        "NormalizedInput",
        "NoVisibleCurveReason",
        "NumericExecutionCost",
        "NumericExecutionResult",
        "NumericValue",
        "ParseMetrics",
        "ParsedEquationInput",
        "ParsedExpressionInput",
        "ParsedInput",
        "PartialDomainMetrics",
        "ParameterizedSamplingDiagnostics",
        "RenderCancelled",
        "RenderOutcome",
        "RenderPlanBuilder",
        "SampledExplicitFunction",
        "SampledCurve",
        "SampledParameterizedCurve",
        "SampledSegmentMetadata",
        "SamplingPrecisionLimitedMetrics",
        "SamplingCancelled",
        "SamplingDiagnostics",
        "SamplingOutcome",
        "SamplingWarning",
        "SamplingWarningCode",
        "SamplingWarningMetrics",
        "SceneRenderExecutor",
        "SourceMap",
        "Token",
        "TokenKind",
        "ViewportResolution",
        "ViewportClippedMetrics",
        "analyze_explicit_function",
        "analyze_plot_item",
        "build_explicit_function_spec",
        "build_explicit_scene_spec",
        "build_single_explicit_render_plan",
        "classify_plot",
        "estimate_numeric_execution_cost",
        "execute_explicit_function",
        "normalize_input",
        "parse_input",
        "render_explicit_png",
        "resolve_single_explicit_viewport",
        "resolve_single_item_viewport",
        "sample_explicit_function",
        "sample_parameterized_curve",
        "split_equation",
        "tokenize",
        "validate_explicit_candidate",
    },
)

_STAGE_13_INTERNAL_ENGINE_NAMES = frozenset(
    {
        "BoundedQuadraticPolynomial",
        "CircleGeometry",
        "EquationCandidate",
        "EquationGeometryError",
        "EquationGeometryResult",
        "EquationPolynomialError",
        "EquationSpecBuilderError",
        "EquationValidationError",
        "EquationValidationFailureKind",
        "ExactLimitComponent",
        "ExactRationalLimitExceeded",
        "ExactRationalZeroDivision",
        "HyperbolaGeometry",
        "LegacyEquationRejectionReason",
        "LineGeometry",
        "ParabolaGeometry",
        "PolynomialFailureKind",
        "ValidatedEquationInput",
        "_validate_validated_equation_input",
        "build_equation_spec",
        "canonicalize_equation",
        "classify_equation_geometry",
        "classify_plot_route",
        "polynomial_from_equation",
        "validate_equation_candidate",
    },
)


def _request(text: str, kind: PlotKind = PlotKind.AUTO) -> PlotItemRequest:
    return PlotItemRequest(
        item_id="public-api-item",
        input_text=text,
        input_source=InputSource.MANUAL,
        requested_plot_kind=kind,
        display_order=0,
        style_key=None,
    )


def _document_section(start_marker: str, end_marker: str) -> str:
    document = _DOCUMENT_PATH.read_text(encoding="utf-8")
    return document.split(start_marker, 1)[1].split(end_marker, 1)[0]


def test_models_package_publishes_the_stage_13_contract_by_identity() -> None:
    assert set(public_models.__all__) == _EXPECTED_MODEL_EXPORTS
    assert len(public_models.__all__) == len(set(public_models.__all__))
    assert _STAGE_13_MODEL_EXPORTS <= set(public_models.__all__)

    public_types = {
        "PrimitiveEquationCoefficients": PrimitiveEquationCoefficients,
        "EquationProvenance": EquationProvenance,
        "AxisOrientation": AxisOrientation,
        "ParabolaOpening": ParabolaOpening,
        "LineSpec": LineSpec,
        "CircleSpec": CircleSpec,
        "EllipseSpec": EllipseSpec,
        "HyperbolaSpec": HyperbolaSpec,
        "ParabolaSpec": ParabolaSpec,
    }
    assert {
        name: getattr(public_models, name) is getattr(implementation_plot_specs, name)
        for name in _STAGE_13_MODEL_EXPORTS
    } == {name: True for name in _STAGE_13_MODEL_EXPORTS}
    assert set(public_types) == _STAGE_13_MODEL_EXPORTS


def test_engine_package_publishes_only_the_stage_13_entry_point() -> None:
    assert set(public_engine.__all__) == _EXPECTED_ENGINE_EXPORTS
    assert len(public_engine.__all__) == len(set(public_engine.__all__))
    assert analyze_plot_item is implementation_analyze_plot_item
    assert public_engine.analyze_plot_item is implementation_analyze_plot_item
    assert not (_STAGE_13_INTERNAL_ENGINE_NAMES & set(public_engine.__all__))
    assert all(
        not hasattr(public_engine, name) for name in _STAGE_13_INTERNAL_ENGINE_NAMES
    )


def test_public_package_initializers_do_not_add_heavy_or_reverse_dependencies() -> None:
    models_source = Path(public_models.__file__).read_text(encoding="utf-8")
    engine_source = Path(public_engine.__file__).read_text(encoding="utf-8")

    assert "math_drawing_assistant.engine" not in models_source
    for source in (models_source, engine_source):
        assert "numpy" not in source.lower()
        assert "pyside" not in source.lower()
        assert "sympy" not in source.lower()


def test_package_entry_points_smoke_the_public_explicit_and_equation_types() -> None:
    cases = (
        ("y=2*x+1", PlotKind.AUTO, ExplicitFunctionSpec),
        ("x=2", PlotKind.AUTO, LineSpec),
        ("x^2+y^2=25", PlotKind.AUTO, CircleSpec),
        ("4*x^2+9*y^2=36", PlotKind.AUTO, EllipseSpec),
        ("4*x^2-9*y^2=36", PlotKind.AUTO, HyperbolaSpec),
        ("x^2=4*y", PlotKind.CONIC_EQUATION, ParabolaSpec),
    )

    for text, kind, expected_type in cases:
        result = analyze_plot_item(_request(text, kind))
        assert type(result) is expected_type
        assert isinstance(result, PlotItemSpec)

    line = analyze_plot_item(_request("y=x+y", PlotKind.AUTO))
    assert type(line) is LineSpec

    rejected = analyze_plot_item(
        _request("y=x+y", PlotKind.EXPLICIT_FUNCTION),
    )
    assert type(rejected) is ErrorInfo
    assert rejected.code is ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED


def test_supported_formulas_records_the_completed_stage_13_contract() -> None:
    document = _DOCUMENT_PATH.read_text(encoding="utf-8")
    status = _document_section(
        "<!-- STAGE_13_STATUS_START -->",
        "<!-- STAGE_13_STATUS_END -->",
    )
    requested_kind_matrix = _document_section(
        "<!-- STAGE_13_REQUESTED_KIND_MATRIX_START -->",
        "<!-- STAGE_13_REQUESTED_KIND_MATRIX_END -->",
    )
    x0_and_precedence = _document_section(
        "<!-- STAGE_13_X0_ERROR_PRECEDENCE_START -->",
        "<!-- STAGE_13_X0_ERROR_PRECEDENCE_END -->",
    )
    error_registry = _document_section(
        "<!-- ERROR_CODE_REGISTRY_START -->",
        "<!-- ERROR_CODE_REGISTRY_END -->",
    )
    limits_index = _document_section(
        "<!-- LIMIT_FIELD_INDEX_START -->",
        "<!-- LIMIT_FIELD_INDEX_END -->",
    )

    assert "文档版本：stage-14b2-exact-line-sampling-v1" in document
    assert "阶段 13A 至 13E 已完成" in status
    assert "analyze_plot_item" in document
    assert "LineSpec | CircleSpec | EllipseSpec | HyperbolaSpec | ParabolaSpec" in document
    assert "未接入 `SceneRenderExecutor`、viewport、sampling、render 或 UI" in status
    assert "阶段 14/15 仍未完成" in status

    assert "消费者尚未实现" not in limits_index
    for row in (
        "| `max_equation_coefficient_numerator_digits`",
        "| `max_equation_coefficient_denominator_digits`",
        "| `max_equation_canonical_coefficient_digits`",
    ):
        assert row in limits_index
    assert "resource_limit_exceeded" in document

    for value in (
        "equation_non_rational_coefficient",
        "equation_non_polynomial",
        "equation_variable_denominator",
        "equation_zero_denominator",
        "equation_degree_exceeded",
        "rotated_conic_not_supported",
        "degenerate_conic",
        "conic_has_no_real_points",
    ):
        assert f"| `{value}`" in error_registry
    assert "消费者待实现" not in error_registry

    assert (
        "| `y=x+y` | `LineSpec` | `explicit_function_y_not_allowed` |"
        " `LineSpec` | `invalid_request` |"
    ) in requested_kind_matrix
    assert "| `x^2=4*y` | `ParabolaSpec` | `unsupported_equation` |" in requested_kind_matrix

    for row in (
        "| `x^0+y=1` | `unsupported_equation`（已实现） |",
        "| `(x+1)^0+y=2` | `unsupported_equation`（已实现） |",
        "| `x^0+y^2=1` | `unsupported_equation`（已实现） |",
        "| `x^3/(x-1)=0` | `equation_degree_exceeded` |",
        "| `x^2/(x-1)=0` | `equation_variable_denominator` |",
        "| `1/(x^3)=0` | `equation_degree_exceeded` |",
    ):
        assert row in x0_and_precedence
