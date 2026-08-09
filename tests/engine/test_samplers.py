"""Stage 8C-2 tests for approved explicit sampling and diagnostics."""

from __future__ import annotations

from dataclasses import fields
import gc
import inspect
from math import log, pi
from pathlib import Path
import weakref

import numpy as np
import pytest

from math_drawing_assistant.engine import (
    DenseOscillationMetrics,
    PartialDomainMetrics,
    RenderPlanBuilder,
    SampledExplicitFunction,
    SamplingCancelled,
    SamplingWarningCode,
    analyze_explicit_function,
    build_explicit_scene_spec,
    build_single_explicit_render_plan,
    sample_explicit_function,
)
from math_drawing_assistant.engine import samplers
from math_drawing_assistant.engine import numeric_executor
from math_drawing_assistant.engine.numeric_executor import (
    NumericExecutionCost,
    NumericExecutionResult,
)
from math_drawing_assistant.models import (
    AspectRequest,
    ErrorCode,
    ErrorInfo,
    InputSource,
    PlotItemRequest,
    PlotKind,
    RenderPlan,
    ResolvedAspect,
    ResolvedViewport,
    ValidatedExplicitExpression,
    ViewportSource,
)
from math_drawing_assistant.models import render_plan as render_plan_model


def _plan(
    text: str = "x",
    *,
    x_bounds: tuple[float, float] = (-10, 10),
    y_bounds: tuple[float, float] = (-10, 10),
    image_width: int = 320,
    image_height: int = 240,
    item_id: str = "sample-item",
) -> RenderPlan:
    validated = analyze_explicit_function(text)
    assert isinstance(validated, ValidatedExplicitExpression), validated
    item_request = PlotItemRequest(
        item_id=item_id,
        input_text=text,
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.EXPLICIT_FUNCTION,
        display_order=0,
    )
    scene = build_explicit_scene_spec(item_request, validated)
    viewport = ResolvedViewport(
        x_min=x_bounds[0],
        x_max=x_bounds[1],
        y_min=y_bounds[0],
        y_max=y_bounds[1],
        aspect=ResolvedAspect.AUTO,
        source=ViewportSource.MANUAL,
    )
    result = build_single_explicit_render_plan(
        scene,
        viewport,
        image_width=image_width,
        image_height=image_height,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )
    assert isinstance(result, RenderPlan), result
    return result


def _sample(*args: object, **kwargs: object) -> SampledExplicitFunction:
    outcome = sample_explicit_function(*args, **kwargs)  # type: ignore[arg-type]
    assert isinstance(outcome, SampledExplicitFunction), outcome
    return outcome


def _ordinary_sampled_copy(
    sampled: SampledExplicitFunction,
) -> SampledExplicitFunction:
    return SampledExplicitFunction(
        item_id=sampled.item_id,
        x=sampled.x,
        y=sampled.y,
        segment_ranges=sampled.segment_ranges,
        finite_sample_count=sampled.finite_sample_count,
        nonfinite_sample_count=sampled.nonfinite_sample_count,
        isolated_finite_count=sampled.isolated_finite_count,
        discontinuity_break_count=sampled.discontinuity_break_count,
        visible_segment_count=sampled.visible_segment_count,
        warnings=sampled.warnings,
        diagnostics=sampled.diagnostics,
    )


def _vector_result(plan: RenderPlan, values: np.ndarray) -> NumericExecutionResult:
    assert plan.item_plan is not None
    values = np.array(values, dtype=np.float64, copy=True)
    values.setflags(write=False)
    return NumericExecutionResult(
        value=values,
        cost=NumericExecutionCost(plan.item_plan.max_live_float64_vectors),
    )


def _forged_numeric_result(
    value: object,
    cost: object,
) -> NumericExecutionResult:
    result = object.__new__(NumericExecutionResult)
    object.__setattr__(result, "value", value)
    object.__setattr__(result, "cost", cost)
    return result


def _plan_state(plan: RenderPlan) -> tuple[tuple[object, ...], tuple[object, ...]]:
    spec = plan.scene_spec.items[0]
    references = (
        plan.scene_spec,
        spec,
        spec.validated_expression,
        plan.resolved_viewport,
        plan.item_plan,
        plan.memory_budget,
    )
    values = (
        spec.item_id,
        spec.normalized_input,
        plan.resolved_viewport.x_min,
        plan.resolved_viewport.x_max,
        plan.resolved_viewport.y_min,
        plan.resolved_viewport.y_max,
        plan.image_width,
        plan.image_height,
        plan.dpi,
    )
    return references, values


def _assert_plan_state(
    plan: RenderPlan,
    before: tuple[tuple[object, ...], tuple[object, ...]],
) -> None:
    current_references, current_values = _plan_state(plan)
    before_references, before_values = before
    assert all(
        current is original
        for current, original in zip(current_references, before_references, strict=True)
    )
    assert current_values == before_values


class _CancelOnCall:
    def __init__(self, call_number: int) -> None:
        self.call_number = call_number
        self.calls = 0

    def is_cancelled(self) -> bool:
        self.calls += 1
        return self.calls == self.call_number


def test_sampler_api_consumes_only_plan_and_optional_cancellation_probe() -> None:
    signature = inspect.signature(sample_explicit_function)
    assert tuple(signature.parameters) == ("plan", "cancellation_probe")
    assert signature.parameters["cancellation_probe"].kind is inspect.Parameter.KEYWORD_ONLY


def test_formal_success_has_an_exact_plan_contract_but_ordinary_construction_does_not() -> None:
    plan = _plan("x^2")
    sampled = _sample(plan)
    ordinary = _ordinary_sampled_copy(sampled)

    assert samplers._sampled_explicit_function_matches_approved_plan(sampled, plan)
    assert sampled._plan_contract_snapshot is not None
    assert ordinary._plan_contract_snapshot is None
    assert not samplers._sampled_explicit_function_matches_approved_plan(
        ordinary,
        plan,
    )
    assert not hasattr(sampled, "__dict__")


def test_sampled_contract_is_not_a_public_constructor_parameter() -> None:
    signature = inspect.signature(SampledExplicitFunction)
    assert tuple(signature.parameters) == (
        "item_id",
        "x",
        "y",
        "segment_ranges",
        "finite_sample_count",
        "nonfinite_sample_count",
        "isolated_finite_count",
        "discontinuity_break_count",
        "visible_segment_count",
        "warnings",
        "diagnostics",
    )
    contract_field = next(
        field
        for field in fields(SampledExplicitFunction)
        if field.name == "_plan_contract_snapshot"
    )
    assert contract_field.init is False


def test_sampled_contract_distinguishes_viewport_scene_and_memory_budget() -> None:
    plan = _plan("x")
    sampled = _sample(plan)
    different_viewport = _plan("x", x_bounds=(-9, 10))
    different_scene = _plan("x^2")
    different_memory = _plan("x", image_height=241)

    assert plan.item_plan is not None
    assert different_viewport.item_plan is not None
    assert different_scene.item_plan is not None
    assert different_memory.item_plan is not None
    assert {
        plan.item_plan.sample_count,
        different_viewport.item_plan.sample_count,
        different_scene.item_plan.sample_count,
        different_memory.item_plan.sample_count,
    } == {640}
    assert {
        plan.item_plan.item_id,
        different_viewport.item_plan.item_id,
        different_scene.item_plan.item_id,
        different_memory.item_plan.item_id,
    } == {"sample-item"}
    assert plan.memory_budget != different_memory.memory_budget
    for other_plan in (different_viewport, different_scene, different_memory):
        assert not samplers._sampled_explicit_function_matches_approved_plan(
            sampled,
            other_plan,
        )


def test_sampled_contract_binds_version_and_every_memory_component() -> None:
    plan = _plan()
    sampled = _sample(plan)
    stored_snapshot = sampled._plan_contract_snapshot
    assert type(stored_snapshot) is render_plan_model._RenderPlanApprovalSnapshot

    version_tampered = _plan()
    object.__setattr__(
        version_tampered,
        "sampling_policy_version",
        "different-policy-version",
    )
    assert stored_snapshot != render_plan_model._approval_snapshot_from_plan(
        version_tampered,
    )

    budget_tampered = _plan()
    assert budget_tampered.memory_budget is not None
    object.__setattr__(
        budget_tampered.memory_budget,
        "artist_data_bytes",
        budget_tampered.memory_budget.artist_data_bytes + 1,
    )
    assert stored_snapshot != render_plan_model._approval_snapshot_from_plan(
        budget_tampered,
    )


def test_sampler_reuses_the_model_snapshot_instead_of_copying_its_field_list() -> None:
    source = Path(samplers.__file__).read_text(encoding="utf-8")

    assert "_snapshot_approved_render_plan(" in source
    assert "_RenderPlanApprovalSnapshot(" not in source
    assert "_RenderMemoryBudgetSnapshot(" not in source
    assert "_ResolvedViewportSnapshot(" not in source


def test_unapproved_plan_is_rejected_before_allocation_or_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = _plan()
    ordinary = RenderPlan(
        scene_spec=approved.scene_spec,
        resolved_viewport=approved.resolved_viewport,
        image_width=approved.image_width,
        image_height=approved.image_height,
        dpi=approved.dpi,
        plan_version=approved.plan_version,
        limits_version=approved.limits_version,
        show_grid=approved.show_grid,
        show_legend=approved.show_legend,
        sampling_policy_version=approved.sampling_policy_version,
        numeric_executor_contract_version=approved.numeric_executor_contract_version,
        item_plan=approved.item_plan,
        memory_budget=approved.memory_budget,
    )

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("unapproved plans must fail before sampling work")

    monkeypatch.setattr(samplers.np, "linspace", forbidden)
    monkeypatch.setattr(samplers.np, "empty", forbidden)
    monkeypatch.setattr(samplers, "execute_explicit_function", forbidden)
    outcome = sample_explicit_function(ordinary)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR


@pytest.mark.parametrize(
    "tamper",
    ["version", "item_plan", "numeric_liveness", "memory_budget"],
)
def test_approval_version_and_nested_field_tampering_fail_before_allocation(
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    plan = _plan()
    assert plan.item_plan is not None and plan.memory_budget is not None
    if tamper == "version":
        object.__setattr__(plan, "sampling_policy_version", "tampered")
    elif tamper == "item_plan":
        object.__setattr__(
            plan.item_plan,
            "sample_count",
            plan.item_plan.sample_count + 1,
        )
    elif tamper == "numeric_liveness":
        object.__setattr__(
            plan.item_plan,
            "max_live_float64_vectors",
            plan.item_plan.max_live_float64_vectors + 1,
        )
        object.__setattr__(
            plan.memory_budget,
            "executor_extra_batch_bytes",
            plan.memory_budget.executor_extra_batch_bytes
            + plan.item_plan.batch_size * 8,
        )
    else:
        object.__setattr__(
            plan.memory_budget,
            "final_x_bytes",
            plan.memory_budget.final_x_bytes + 8,
        )

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("tampered plans must fail before np.linspace")

    monkeypatch.setattr(samplers.np, "linspace", forbidden)
    monkeypatch.setattr(samplers.np, "empty", forbidden)
    monkeypatch.setattr(samplers, "execute_explicit_function", forbidden)
    outcome = sample_explicit_function(plan)
    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR


def test_sampler_does_not_reinvoke_cost_estimator_or_render_plan_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan("x^2")

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("approved sampling must not re-prove the render budget")

    monkeypatch.setattr(
        numeric_executor,
        "estimate_numeric_execution_cost",
        forbidden,
    )
    monkeypatch.setattr(RenderPlanBuilder, "build", forbidden)

    sampled = _sample(plan)
    assert sampled.segment_ranges.tolist() == [[0, 640]]


@pytest.mark.parametrize("text", ["x", "x^2"])
def test_basic_explicit_functions_fill_the_formal_arrays(text: str) -> None:
    sampled = _sample(_plan(text))
    expected = sampled.x if text == "x" else sampled.x**2

    assert np.allclose(sampled.y, expected)
    assert sampled.segment_ranges.tolist() == [[0, sampled.x.shape[0]]]
    assert sampled.finite_sample_count == sampled.x.shape[0]
    assert sampled.nonfinite_sample_count == 0


def test_finite_scalar_fills_owned_y_without_a_broadcast_result() -> None:
    sampled = _sample(_plan("2"))

    assert np.all(sampled.y == 2.0)
    assert sampled.y.flags.owndata
    assert sampled.y.base is None
    assert sampled.segment_ranges.tolist() == [[0, sampled.x.shape[0]]]


def test_nonfinite_scalar_returns_unified_no_visible_error() -> None:
    outcome = sample_explicit_function(_plan("1/0"))

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.NO_VISIBLE_CURVE
    assert outcome.technical_message == "reason=NO_FINITE_SAMPLES"
    assert outcome.recoverable is True


@pytest.mark.parametrize("text", ["sqrt(x)", "ln(x)", "lg(x)", "log(x,10)"])
def test_partial_domains_produce_one_typed_warning_and_drawable_segment(
    text: str,
) -> None:
    sampled = _sample(_plan(text))

    assert sampled.finite_sample_count > 0
    assert sampled.nonfinite_sample_count > 0
    assert sampled.segment_ranges.shape[0] == 1
    assert [warning.code for warning in sampled.warnings] == [
        SamplingWarningCode.PARTIAL_DOMAIN_OMITTED,
    ]
    assert type(sampled.warnings[0].metrics) is PartialDomainMetrics


def test_only_an_isolated_finite_point_has_no_drawable_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()

    def isolated(spec: object, x: np.ndarray, **kwargs: object) -> NumericExecutionResult:
        values = np.full(x.shape, np.nan, dtype=np.float64)
        values[x.shape[0] // 2] = 0.0
        return _vector_result(plan, values)

    monkeypatch.setattr(samplers, "execute_explicit_function", isolated)
    outcome = sample_explicit_function(plan)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.NO_VISIBLE_CURVE
    assert outcome.technical_message == "reason=NO_DRAWABLE_SEGMENT"


def test_curve_wholly_outside_manual_y_viewport_is_not_success() -> None:
    outcome = sample_explicit_function(_plan("100", y_bounds=(-1, 1)))

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.NO_VISIBLE_CURVE
    assert outcome.technical_message == "reason=OUTSIDE_VIEWPORT"


def test_continuous_pair_crossing_the_viewport_is_visible() -> None:
    sampled = _sample(
        _plan("100000*x", x_bounds=(-1, 1), y_bounds=(-1, 1), image_width=800),
    )

    assert sampled.visible_segment_count == 1
    assert sampled.segment_ranges.shape == (1, 2)
    assert sampled.discontinuity_break_count == 0


def test_finite_pair_broken_as_discontinuous_does_not_make_segments_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan("x", y_bounds=(-1, 1))

    def separated_outside_bands(
        spec: object,
        x: np.ndarray,
        **kwargs: object,
    ) -> NumericExecutionResult:
        values = np.full(x.shape, -100.0, dtype=np.float64)
        values[x.shape[0] // 2 :] = 100.0
        return _vector_result(plan, values)

    monkeypatch.setattr(
        samplers,
        "execute_explicit_function",
        separated_outside_bands,
    )
    outcome = sample_explicit_function(plan)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.NO_VISIBLE_CURVE
    assert outcome.technical_message == "reason=OUTSIDE_VIEWPORT"


@pytest.mark.parametrize("nonfinite", [np.nan, np.inf, -np.inf])
def test_nonfinite_samples_force_segment_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    nonfinite: float,
) -> None:
    plan = _plan("x")

    def interrupted(
        spec: object,
        x: np.ndarray,
        **kwargs: object,
    ) -> NumericExecutionResult:
        values = np.zeros(x.shape, dtype=np.float64)
        values[x.shape[0] // 2] = nonfinite
        return _vector_result(plan, values)

    monkeypatch.setattr(samplers, "execute_explicit_function", interrupted)
    sampled = _sample(plan)

    assert sampled.segment_ranges.shape == (2, 2)
    assert sampled.nonfinite_sample_count == 1
    assert sampled.diagnostics.nonfinite_boundary_break_count == 2


def test_nonfinite_break_between_opposite_outside_bands_is_not_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan("x", y_bounds=(-1, 1))

    def interrupted_outside_bands(
        spec: object,
        x: np.ndarray,
        **kwargs: object,
    ) -> NumericExecutionResult:
        midpoint = x.shape[0] // 2
        values = np.full(x.shape, -100.0, dtype=np.float64)
        values[midpoint] = np.nan
        values[midpoint + 1 :] = 100.0
        return _vector_result(plan, values)

    monkeypatch.setattr(
        samplers,
        "execute_explicit_function",
        interrupted_outside_bands,
    )
    outcome = sample_explicit_function(plan)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.NO_VISIBLE_CURVE
    assert outcome.technical_message == "reason=OUTSIDE_VIEWPORT"


def test_one_over_x_breaks_without_sampling_the_pole() -> None:
    sampled = _sample(
        _plan("1/x", x_bounds=(-1, 1), y_bounds=(-10, 10), image_width=800),
    )

    assert not np.any(sampled.x == 0.0)
    assert sampled.segment_ranges.shape == (2, 2)
    assert sampled.diagnostics.finite_discontinuity_break_count == 1
    left_stop = int(sampled.segment_ranges[0, 1])
    right_start = int(sampled.segment_ranges[1, 0])
    assert left_stop == right_start
    assert sampled.y[left_stop - 1] < -10
    assert sampled.y[right_start] > 10


def test_tangent_breaks_at_unsampled_asymptotes() -> None:
    sampled = _sample(
        _plan("tan(x)", x_bounds=(-2, 2), y_bounds=(-10, 10), image_width=800),
    )

    assert not np.any(sampled.x == -pi / 2)
    assert not np.any(sampled.x == pi / 2)
    assert sampled.segment_ranges.shape == (3, 2)
    assert sampled.diagnostics.finite_discontinuity_break_count == 2


def test_edge_exp_with_only_one_sided_jump_evidence_remains_visible() -> None:
    sample_count = 640
    x_max = log(100.0)
    plan = _plan(
        "exp(x)",
        x_bounds=(x_max - 6_390.0, x_max),
        y_bounds=(0.5, 1.5),
        image_width=320,
    )
    assert plan.item_plan is not None
    assert plan.item_plan.sample_count == sample_count

    sampled = _sample(plan)

    assert sampled.y[-2] == pytest.approx(100.0 * np.exp(-10.0))
    assert sampled.y[-1] == pytest.approx(100.0)
    assert sampled.segment_ranges.tolist() == [[0, sample_count]]
    assert sampled.visible_segment_count == 1
    assert sampled.diagnostics.finite_discontinuity_break_count == 0


@pytest.mark.parametrize(
    ("text", "x_bounds", "y_bounds"),
    [
        ("100000*x", (-1, 1), (-10, 10)),
        ("x^3", (-10, 10), (-10, 10)),
        ("exp(x)", (-10, 10), (-10, 10)),
    ],
)
def test_continuous_steep_functions_are_not_split(
    text: str,
    x_bounds: tuple[float, float],
    y_bounds: tuple[float, float],
) -> None:
    sampled = _sample(
        _plan(text, x_bounds=x_bounds, y_bounds=y_bounds, image_width=800),
    )

    assert sampled.segment_ranges.tolist() == [[0, sampled.x.shape[0]]]
    assert sampled.diagnostics.finite_discontinuity_break_count == 0


def test_segment_ranges_are_owned_read_only_ordered_half_open_and_drawable() -> None:
    sampled = _sample(
        _plan("tan(x)", x_bounds=(-2, 2), y_bounds=(-10, 10), image_width=800),
    )

    assert sampled.segment_ranges.dtype == np.dtype(np.int64)
    assert sampled.segment_ranges.flags.owndata
    assert not sampled.segment_ranges.flags.writeable
    previous_stop = 0
    for start, stop in sampled.segment_ranges.tolist():
        assert previous_stop <= start < stop <= sampled.x.shape[0]
        assert stop - start >= 2
        previous_stop = stop


def test_segment_capacity_failure_is_typed_and_never_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()

    def many_segments(
        spec: object,
        x: np.ndarray,
        **kwargs: object,
    ) -> NumericExecutionResult:
        values = np.full(x.shape, np.nan, dtype=np.float64)
        for start in range(0, x.shape[0], 3):
            values[start : start + 2] = 0.0
        return _vector_result(plan, values)

    monkeypatch.setattr(samplers, "execute_explicit_function", many_segments)
    outcome = sample_explicit_function(plan)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert outcome.field_name == "max_segment_count"


def test_executor_batch_never_exceeds_plan_and_receives_x_slice_views(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(image_width=3000)
    assert plan.item_plan is not None
    assert plan.item_plan.sample_count == 6000
    assert plan.item_plan.batch_size == 4096
    original = samplers.execute_explicit_function
    lengths: list[int] = []
    batch_inputs: list[np.ndarray] = []

    def recording(spec: object, x: np.ndarray, **kwargs: object) -> object:
        lengths.append(x.shape[0])
        batch_inputs.append(x)
        return original(spec, x, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(samplers, "execute_explicit_function", recording)
    sampled = _sample(plan)

    assert lengths == [4096, 1904]
    assert 0 < lengths[-1] < plan.item_plan.batch_size
    assert max(lengths) <= plan.item_plan.batch_size
    assert sum(lengths) == plan.item_plan.sample_count
    assert all(not batch.flags.owndata for batch in batch_inputs)
    assert all(not batch.flags.writeable for batch in batch_inputs)
    assert all(np.shares_memory(batch, sampled.x) for batch in batch_inputs)
    original_first_x = float(sampled.x[0])
    with pytest.raises(ValueError):
        batch_inputs[0][0] = 113.0
    assert sampled.x[0] == original_first_x


def test_cancellation_after_first_real_batch_skips_short_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(image_width=3000)
    original = samplers.execute_explicit_function
    lengths: list[int] = []

    def recording(spec: object, x: np.ndarray, **kwargs: object) -> object:
        lengths.append(x.shape[0])
        return original(spec, x, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(samplers, "execute_explicit_function", recording)
    outcome = sample_explicit_function(plan, cancellation_probe=_CancelOnCall(3))

    assert isinstance(outcome, SamplingCancelled)
    assert lengths == [4096]


def test_diagnostic_loop_cancellation_occurs_after_entry_and_before_freezing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan("x^2")
    original_scan = samplers._scan_visibility_and_oscillation

    class DiagnosticProbe:
        in_diagnostics = False
        diagnostic_polls = 0

        def is_cancelled(self) -> bool:
            if self.in_diagnostics:
                self.diagnostic_polls += 1
                return self.diagnostic_polls == 1
            return False

    probe = DiagnosticProbe()
    entered = False

    def recording_scan(*args: object, **kwargs: object) -> object:
        nonlocal entered
        entered = True
        probe.in_diagnostics = True
        return original_scan(*args, **kwargs)  # type: ignore[arg-type]

    def forbidden_result(*args: object, **kwargs: object) -> object:
        raise AssertionError("diagnostic cancellation must precede final freezing")

    monkeypatch.setattr(samplers, "_scan_visibility_and_oscillation", recording_scan)
    monkeypatch.setattr(samplers, "SampledExplicitFunction", forbidden_result)
    outcome = sample_explicit_function(plan, cancellation_probe=probe)

    assert entered is True
    assert probe.diagnostic_polls == 1
    assert isinstance(outcome, SamplingCancelled)


def test_plan_and_viewport_snapshots_are_not_modified() -> None:
    plan = _plan("x^2")
    references = (
        plan.scene_spec,
        plan.resolved_viewport,
        plan.item_plan,
        plan.memory_budget,
    )
    viewport_values = (
        plan.resolved_viewport.x_min,
        plan.resolved_viewport.x_max,
        plan.resolved_viewport.y_min,
        plan.resolved_viewport.y_max,
    )

    _sample(plan)

    assert references == (
        plan.scene_spec,
        plan.resolved_viewport,
        plan.item_plan,
        plan.memory_budget,
    )
    assert viewport_values == (
        plan.resolved_viewport.x_min,
        plan.resolved_viewport.x_max,
        plan.resolved_viewport.y_min,
        plan.resolved_viewport.y_max,
    )


def test_returned_arrays_are_float64_or_int64_owned_and_read_only() -> None:
    plan = _plan("x^2")
    sampled = _sample(plan)

    assert samplers._sampled_explicit_function_matches_approved_plan(sampled, plan)
    for vector in (sampled.x, sampled.y):
        assert vector.dtype == np.dtype(np.float64)
        assert vector.shape == (sampled.x.shape[0],)
        assert vector.flags.owndata
        assert vector.base is None
        assert not vector.flags.writeable
        with pytest.raises(ValueError):
            vector[0] = 1.0
    assert sampled.segment_ranges.dtype == np.dtype(np.int64)
    assert sampled.segment_ranges.shape[1] == 2
    assert sampled.segment_ranges.flags.owndata
    assert sampled.segment_ranges.base is None
    assert not sampled.segment_ranges.flags.writeable


def test_executor_batch_outputs_are_not_retained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(image_width=4096)
    original = samplers.execute_explicit_function
    output_refs: list[weakref.ReferenceType[np.ndarray]] = []

    def tracking(spec: object, x: np.ndarray, **kwargs: object) -> object:
        result = original(spec, x, **kwargs)  # type: ignore[arg-type]
        if isinstance(result, NumericExecutionResult) and isinstance(
            result.value,
            np.ndarray,
        ):
            output_refs.append(weakref.ref(result.value))
        return result

    monkeypatch.setattr(samplers, "execute_explicit_function", tracking)
    _sample(plan)
    gc.collect()

    assert len(output_refs) == 2
    assert all(reference() is None for reference in output_refs)


def test_executor_error_is_returned_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    error = ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="executor failed",
        technical_message="typed executor contract failure",
        recoverable=False,
    )
    monkeypatch.setattr(samplers, "execute_explicit_function", lambda *a, **k: error)

    assert sample_explicit_function(plan) is error


@pytest.mark.parametrize(
    ("failure", "technical_message"),
    [
        ("dtype", "numeric executor result contract mismatch"),
        ("shape", "numeric executor vector ownership mismatch"),
        ("ownership", "numeric executor vector ownership mismatch"),
        ("reported_cost", "numeric executor cost mismatch"),
    ],
)
def test_executor_invalid_vector_or_cost_contract_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    technical_message: str,
) -> None:
    plan = _plan()
    assert plan.item_plan is not None
    approved_cost = NumericExecutionCost(
        plan.item_plan.max_live_float64_vectors,
    )

    def invalid_result(
        spec: object,
        x: np.ndarray,
        **kwargs: object,
    ) -> NumericExecutionResult:
        if failure == "dtype":
            value = np.zeros(x.shape, dtype=np.float32)
            value.setflags(write=False)
            return _forged_numeric_result(value, approved_cost)
        if failure == "shape":
            value = np.zeros(x.shape[0] - 1, dtype=np.float64)
            value.setflags(write=False)
            return NumericExecutionResult(value=value, cost=approved_cost)
        if failure == "ownership":
            owner = np.zeros(x.shape[0] + 1, dtype=np.float64)
            value = owner[: x.shape[0]]
            value.setflags(write=False)
            return NumericExecutionResult(value=value, cost=approved_cost)
        return NumericExecutionResult(
            value=0.0,
            cost=NumericExecutionCost(
                plan.item_plan.max_live_float64_vectors + 1,
            ),
        )

    monkeypatch.setattr(samplers, "execute_explicit_function", invalid_result)
    outcome = sample_explicit_function(plan)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.technical_message == technical_message


@pytest.mark.parametrize(
    ("cancel_on", "executor_calls"),
    [
        (2, 0),  # before the first batch
        (3, 1),  # after the executor returns
        (4, 1),  # during segmentation
        (10, 1),  # immediately before freezing the result
    ],
)
def test_cancellation_checkpoints_never_return_partial_samples(
    monkeypatch: pytest.MonkeyPatch,
    cancel_on: int,
    executor_calls: int,
) -> None:
    plan = _plan()
    original = samplers.execute_explicit_function
    calls = 0

    def recording(spec: object, x: np.ndarray, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return original(spec, x, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(samplers, "execute_explicit_function", recording)
    outcome = sample_explicit_function(
        plan,
        cancellation_probe=_CancelOnCall(cancel_on),
    )

    assert isinstance(outcome, SamplingCancelled)
    assert outcome.item_id == "sample-item"
    assert calls == executor_calls


def test_cancellation_after_approval_precedes_first_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("pre-allocation cancellation must avoid np.linspace")

    monkeypatch.setattr(samplers.np, "linspace", forbidden)
    outcome = sample_explicit_function(
        plan,
        cancellation_probe=_CancelOnCall(1),
    )
    assert isinstance(outcome, SamplingCancelled)


def test_error_and_cancellation_outcomes_do_not_carry_success_contracts() -> None:
    error = sample_explicit_function(_plan("1/0"))
    cancelled = sample_explicit_function(
        _plan(),
        cancellation_probe=_CancelOnCall(1),
    )

    assert isinstance(error, ErrorInfo)
    assert isinstance(cancelled, SamplingCancelled)
    assert not hasattr(error, "_plan_contract_snapshot")
    assert not hasattr(cancelled, "_plan_contract_snapshot")


def test_allocation_memory_error_is_sanitized_resource_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    before = _plan_state(plan)

    def fail_allocation(*args: object, **kwargs: object) -> object:
        raise MemoryError("secret allocator detail")

    monkeypatch.setattr(samplers.np, "linspace", fail_allocation)
    outcome = sample_explicit_function(plan)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert outcome.recoverable is True
    assert "secret" not in (outcome.technical_message or "")
    _assert_plan_state(plan, before)


def test_approval_snapshot_memory_error_is_sanitized_before_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    before = _plan_state(plan)

    def fail_snapshot(*args: object, **kwargs: object) -> object:
        raise MemoryError("secret snapshot allocator detail")

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("approval failure must precede sampling allocations")

    monkeypatch.setattr(render_plan_model, "_approval_snapshot_from_plan", fail_snapshot)
    monkeypatch.setattr(samplers.np, "linspace", forbidden)
    monkeypatch.setattr(samplers, "execute_explicit_function", forbidden)
    outcome = sample_explicit_function(plan)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert outcome.recoverable is True
    assert "secret" not in (outcome.technical_message or "")
    _assert_plan_state(plan, before)


def test_formal_y_memory_error_stops_before_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    before = _plan_state(plan)
    assert plan.item_plan is not None
    original_empty = samplers.np.empty

    def fail_y(shape: object, *args: object, **kwargs: object) -> np.ndarray:
        if shape == plan.item_plan.sample_count:
            raise MemoryError("secret y allocator detail")
        return original_empty(shape, *args, **kwargs)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("y allocation failure must precede executor work")

    monkeypatch.setattr(samplers.np, "empty", fail_y)
    monkeypatch.setattr(samplers, "execute_explicit_function", forbidden)
    outcome = sample_explicit_function(plan)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert "secret" not in (outcome.technical_message or "")
    _assert_plan_state(plan, before)


def test_validity_mask_memory_error_stops_before_segmentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    before = _plan_state(plan)
    executor_calls = 0
    original_executor = samplers.execute_explicit_function

    def recording_executor(*args: object, **kwargs: object) -> object:
        nonlocal executor_calls
        executor_calls += 1
        return original_executor(*args, **kwargs)  # type: ignore[arg-type]

    def fail_mask(*args: object, **kwargs: object) -> object:
        raise MemoryError("secret mask allocator detail")

    def forbidden_scan(*args: object, **kwargs: object) -> object:
        raise AssertionError("mask allocation failure must precede segmentation")

    monkeypatch.setattr(samplers, "execute_explicit_function", recording_executor)
    monkeypatch.setattr(samplers.np, "isfinite", fail_mask)
    monkeypatch.setattr(samplers, "_scan_segments", forbidden_scan)
    outcome = sample_explicit_function(plan)

    assert executor_calls == 1
    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert "secret" not in (outcome.technical_message or "")
    _assert_plan_state(plan, before)


def test_segment_range_memory_error_stops_before_freezing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    before = _plan_state(plan)
    original_empty = samplers.np.empty

    def fail_ranges(shape: object, *args: object, **kwargs: object) -> np.ndarray:
        dtype = kwargs.get("dtype", args[0] if args else None)
        if shape == (1, 2) and np.dtype(dtype) == np.dtype(np.int64):
            raise MemoryError("secret ranges allocator detail")
        return original_empty(shape, *args, **kwargs)

    def forbidden_result(*args: object, **kwargs: object) -> object:
        raise AssertionError("range allocation failure must precede final freezing")

    monkeypatch.setattr(samplers.np, "empty", fail_ranges)
    monkeypatch.setattr(samplers, "SampledExplicitFunction", forbidden_result)
    outcome = sample_explicit_function(plan)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert "secret" not in (outcome.technical_message or "")
    _assert_plan_state(plan, before)


@pytest.mark.parametrize(
    ("constructor_name", "text"),
    [
        ("SamplingDiagnostics", "x"),
        ("SamplingWarning", "sqrt(x)"),
        ("SampledExplicitFunction", "x"),
    ],
)
def test_diagnostics_warning_and_final_result_memory_errors_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    constructor_name: str,
    text: str,
) -> None:
    plan = _plan(text)
    before = _plan_state(plan)

    def fail_construction(*args: object, **kwargs: object) -> object:
        raise MemoryError(f"secret {constructor_name} allocator detail")

    monkeypatch.setattr(samplers, constructor_name, fail_construction)
    outcome = sample_explicit_function(plan)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert outcome.recoverable is True
    assert outcome.technical_message == "sampling allocation failed"
    assert "secret" not in (outcome.technical_message or "")
    _assert_plan_state(plan, before)


@pytest.mark.parametrize("text", ["sin(x)", "x^2", "exp(x)"])
def test_ordinary_functions_do_not_get_dense_oscillation_warning(text: str) -> None:
    sampled = _sample(
        _plan(text, y_bounds=(-2, 25_000), image_width=800),
    )
    assert SamplingWarningCode.DENSE_OSCILLATION_SUSPECTED not in {
        warning.code for warning in sampled.warnings
    }


@pytest.mark.parametrize(
    ("text", "y_bounds"),
    [
        ("2", (1, 3)),
        ("2+0.000001*x", (1, 3)),
        ("0.000001*sin(1000*x)", (-1, 1)),
    ],
)
def test_constant_near_constant_and_tiny_high_frequency_are_not_dense(
    text: str,
    y_bounds: tuple[float, float],
) -> None:
    sampled = _sample(
        _plan(text, y_bounds=y_bounds, image_width=800, image_height=600),
    )

    assert sampled.diagnostics.significant_direction_change_count == 0
    assert SamplingWarningCode.DENSE_OSCILLATION_SUSPECTED not in {
        warning.code for warning in sampled.warnings
    }


@pytest.mark.parametrize(
    ("text", "y_bounds"),
    [
        ("sin(1000*x)", (-2, 2)),
        ("2+sin(1000*x)", (-1, 5)),
    ],
)
def test_frozen_high_frequency_examples_emit_typed_proxy_warning(
    text: str,
    y_bounds: tuple[float, float],
) -> None:
    sampled = _sample(
        _plan(text, y_bounds=y_bounds, image_width=800, image_height=600),
    )
    warning = next(
        warning
        for warning in sampled.warnings
        if warning.code is SamplingWarningCode.DENSE_OSCILLATION_SUSPECTED
    )

    assert type(warning.metrics) is DenseOscillationMetrics
    assert warning.metrics.significant_direction_change_count == 30
    assert warning.metrics.valid_adjacent_pair_count == 1_599
    assert warning.metrics.samples_per_monotone_run == pytest.approx(1_600 / 31)
    assert tuple(field.name for field in fields(warning)) == ("code", "metrics")


def test_engine_sampler_has_no_gui_renderer_or_expression_compiler_path() -> None:
    source = Path(samplers.__file__).read_text(encoding="utf-8").lower()
    forbidden = (
        "pyside",
        "matplotlib",
        "figurecanvasagg",
        "qthread",
        "sympy",
        "lambdify",
        "callable",
    )

    assert all(term not in source for term in forbidden)
