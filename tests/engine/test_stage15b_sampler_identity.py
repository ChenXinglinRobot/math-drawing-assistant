"""Stage 15-B exact sampler dispatch and P3-6 cancellation identity tests."""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from math_drawing_assistant.engine import scene_executor as executor_module
from math_drawing_assistant.engine.plot_analyzer import analyze_plot_item
from math_drawing_assistant.engine.render_plan_builder import RenderPlanBuilder
from math_drawing_assistant.engine.samplers import (
    SampledExplicitFunction,
    SampledParameterizedCurve,
    SamplingCancelled,
    sample_explicit_function,
    sample_parameterized_curve,
)
from math_drawing_assistant.engine.scene_executor import SceneRenderExecutor
from math_drawing_assistant.engine.viewport_resolver import resolve_single_item_viewport
from math_drawing_assistant.models import (
    ErrorCode,
    ErrorInfo,
    InputSource,
    PlotItemRequest,
    PlotKind,
    PlotSceneRequest,
    PlotSceneSpec,
    RenderPlan,
    ViewportMode,
    ViewportRequest,
)


class _NeverCancelled:
    def __init__(self) -> None:
        self.calls = 0

    def is_cancelled(self) -> bool:
        self.calls += 1
        return False


class _CancelOnCall:
    def __init__(self, target: int) -> None:
        self.target = target
        self.calls = 0

    def is_cancelled(self) -> bool:
        self.calls += 1
        return self.calls == self.target


def _item(text: str, item_id: str = "identity-item") -> PlotItemRequest:
    return PlotItemRequest(
        item_id=item_id,
        input_text=text,
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.AUTO,
        display_order=0,
    )


def _plan(text: str, item_id: str = "identity-item") -> RenderPlan:
    spec = analyze_plot_item(_item(text, item_id))
    assert not isinstance(spec, ErrorInfo)
    scene = PlotSceneSpec(items=(spec,))
    resolution = resolve_single_item_viewport(
        scene,
        ViewportRequest(
            mode=ViewportMode.MANUAL,
            x_min=-10,
            x_max=10,
            y_min=-10,
            y_max=10,
        ),
    )
    assert resolution.viewport is not None and resolution.error is None
    plan = RenderPlanBuilder().build(
        scene,
        resolution.viewport,
        image_width=400,
        image_height=300,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )
    assert type(plan) is RenderPlan
    return plan


def _request(text: str) -> PlotSceneRequest:
    return PlotSceneRequest(
        request_id=71,
        scene_revision=8,
        items=(_item(text),),
        viewport=ViewportRequest(
            mode=ViewportMode.MANUAL,
            x_min=-10,
            x_max=10,
            y_min=-10,
            y_max=10,
        ),
        image_width=400,
        image_height=300,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )


@pytest.mark.parametrize(
    ("text", "expected_sampler"),
    (
        ("y=x^2", "explicit"),
        ("x+y=1", "parameterized"),
        ("x^2+y^2=25", "parameterized"),
        ("x^2/9+y^2/4=1", "parameterized"),
        ("x^2/9-y^2/4=1", "parameterized"),
        ("x^2=4*y", "parameterized"),
    ),
)
def test_each_exact_spec_calls_only_its_exact_sampler(
    text: str,
    expected_sampler: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    original_explicit = executor_module.sample_explicit_function
    original_parameterized = executor_module._sample_geometry_curve_for_scene

    def explicit(*args: object, **kwargs: object):
        calls.append("explicit")
        return original_explicit(*args, **kwargs)

    def parameterized(*args: object, **kwargs: object):
        calls.append("parameterized")
        return original_parameterized(*args, **kwargs)

    monkeypatch.setattr(executor_module, "sample_explicit_function", explicit)
    monkeypatch.setattr(
        executor_module,
        "_sample_geometry_curve_for_scene",
        parameterized,
    )

    result = SceneRenderExecutor().execute(_request(text), _NeverCancelled())

    assert result.success is True
    assert calls == [expected_sampler]


def _successful_sample(text: str):
    plan = _plan(text)
    if text.startswith("y="):
        sampled = sample_explicit_function(plan)
        assert type(sampled) is SampledExplicitFunction
    else:
        sampled = sample_parameterized_curve(plan)
        assert type(sampled) is SampledParameterizedCurve
    return sampled


@pytest.mark.parametrize(
    ("text", "outcome_factory"),
    (
        ("y=x^2", lambda: _successful_sample("x+y=1")),
        ("x+y=1", lambda: _successful_sample("y=x^2")),
        ("y=x^2", object),
    ),
)
def test_wrong_sampled_class_or_union_fails_closed_before_renderer(
    text: str,
    outcome_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sampled = outcome_factory()
    sampler_name = (
        "sample_explicit_function"
        if text.startswith("y=")
        else "_sample_geometry_curve_for_scene"
    )
    monkeypatch.setattr(executor_module, sampler_name, lambda *args, **kwargs: sampled)
    monkeypatch.setattr(
        executor_module,
        "render_sampled_curve_png",
        lambda *args, **kwargs: pytest.fail("renderer must not run"),
    )
    result = SceneRenderExecutor().execute(_request(text), _NeverCancelled())
    assert result.error is not None
    assert result.error.code is ErrorCode.INTERNAL_ERROR
    assert result.error.item_id == "identity-item"


def test_wrong_sampled_item_id_fails_closed_before_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = executor_module.sample_explicit_function

    def wrong_id(*args: object, **kwargs: object):
        sampled = original(*args, **kwargs)
        assert type(sampled) is SampledExplicitFunction
        object.__setattr__(sampled, "item_id", "other-item")
        return sampled

    monkeypatch.setattr(executor_module, "sample_explicit_function", wrong_id)
    monkeypatch.setattr(
        executor_module,
        "render_sampled_curve_png",
        lambda *args, **kwargs: pytest.fail("renderer must not run"),
    )
    result = SceneRenderExecutor().execute(_request("y=x^2"), _NeverCancelled())
    assert result.error is not None
    assert result.error.code is ErrorCode.INTERNAL_ERROR


@pytest.mark.parametrize(
    "outcome",
    (
        SamplingCancelled("other-item"),
        ErrorInfo(
            code=ErrorCode.NO_VISIBLE_CURVE,
            user_message="wrong owner",
            item_id="other-item",
            recoverable=True,
        ),
    ),
)
def test_wrong_cancel_or_error_item_id_never_becomes_success_or_neutral_cancel(
    outcome: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executor_module,
        "sample_explicit_function",
        lambda *args, **kwargs: outcome,
    )
    monkeypatch.setattr(
        executor_module,
        "render_sampled_curve_png",
        lambda *args, **kwargs: pytest.fail("renderer must not run"),
    )
    result = SceneRenderExecutor().execute(_request("y=x^2"), _NeverCancelled())
    assert result.success is False
    assert result.error is not None
    assert result.error.code is ErrorCode.INTERNAL_ERROR
    assert result.error.item_id == "identity-item"
    assert result.item_results != ()


def test_spec_item_plan_union_mismatch_calls_neither_sampler_nor_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrong_plan = _plan("x+y=1")
    monkeypatch.setattr(
        executor_module.RenderPlanBuilder,
        "build",
        lambda *args, **kwargs: wrong_plan,
    )
    monkeypatch.setattr(
        executor_module,
        "sample_explicit_function",
        lambda *args, **kwargs: pytest.fail("sampler must not run"),
    )
    monkeypatch.setattr(
        executor_module,
        "_sample_geometry_curve_for_scene",
        lambda *args, **kwargs: pytest.fail("sampler must not run"),
    )
    monkeypatch.setattr(
        executor_module,
        "render_sampled_curve_png",
        lambda *args, **kwargs: pytest.fail("renderer must not run"),
    )
    result = SceneRenderExecutor().execute(_request("y=x^2"), _NeverCancelled())
    assert result.error is not None
    assert result.error.code is ErrorCode.INTERNAL_ERROR


@pytest.mark.parametrize(
    "text",
    ("x^2/9+y^2/4=1", "x^2/9-y^2/4=1", "x^2=4*y"),
    ids=("oval", "hyperbola", "parabola"),
)
def test_every_parameterized_cancellation_point_keeps_exact_item_identity(
    text: str,
) -> None:
    plan = _plan(text)
    counting_probe = _NeverCancelled()
    completed = sample_parameterized_curve(
        plan,
        cancellation_probe=counting_probe,
    )
    assert type(completed) is SampledParameterizedCurve
    poll_count = counting_probe.calls
    assert poll_count > 0

    for target in range(1, poll_count + 1):
        outcome = sample_parameterized_curve(
            plan,
            cancellation_probe=_CancelOnCall(target),
        )
        assert type(outcome) is SamplingCancelled
        assert outcome.item_id == plan.item_plan.item_id
        assert [field.name for field in fields(outcome)] == ["item_id"]
        for forbidden in (
            "x",
            "y",
            "ranges",
            "segment_ranges",
            "warnings",
            "diagnostics",
            "sampled_result",
        ):
            assert not hasattr(outcome, forbidden)
