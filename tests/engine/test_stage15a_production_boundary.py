"""Stage 15A P3-1: AST-level production boundary scan over the whole package.

The package root is derived from this test file, never from the current
working directory, matching the Stage 14E acceptance pattern.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import math_drawing_assistant.engine as public_engine

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "math_drawing_assistant"

# Modules that production code must never reference, directly or dynamically.
_FORBIDDEN_ROOTS = ("tests", "benchmarks")
_PROJECTION_MODULES = frozenset(
    {
        "math_drawing_assistant.engine.oval_geometry",
        "math_drawing_assistant.engine.hyperbola_geometry",
        "math_drawing_assistant.engine.parabola_geometry",
    },
)
_RENDERER_FORBIDDEN_CALLS = frozenset(
    {
        "sample_explicit_function",
        "sample_parameterized_curve",
        "analyze_plot_item",
        "analyze_explicit_function",
        "resolve_single_item_viewport",
        "resolve_single_explicit_viewport",
        "RenderPlanBuilder",
        "build",
    },
)
_PRODUCTION_RENDER_ENTRIES = frozenset(
    {"render_explicit_png", "render_sampled_curve_png"},
)


def _production_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def _dotted_attribute_chain(node: ast.Attribute) -> str:
    parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _import_bindings(tree: ast.AST) -> dict[str, str]:
    """Resolve the direct import aliases frozen by the P3-1 boundary.

    This deliberately models static ``import``/``from ... import`` bindings
    and module-attribute calls only. Reassignment, ``getattr``, star imports,
    and arbitrary dynamic Python are outside the frozen scanner claim.
    """

    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is not None:
                    bindings[alias.asname] = alias.name
                else:
                    root = alias.name.split(".", 1)[0]
                    bindings[root] = root
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                if alias.name == "*":
                    continue
                bindings[alias.asname or alias.name] = (
                    f"{node.module}.{alias.name}"
                )
    return bindings


def _resolved_call_name(
    callee: ast.expr,
    bindings: dict[str, str],
) -> str | None:
    if isinstance(callee, ast.Name):
        return bindings.get(callee.id, callee.id)
    if not isinstance(callee, ast.Attribute):
        return None
    chain = _dotted_attribute_chain(callee)
    if not chain:
        return callee.attr
    root, separator, remainder = chain.partition(".")
    resolved_root = bindings.get(root, root)
    return (
        f"{resolved_root}.{remainder}"
        if separator
        else resolved_root
    )


def _production_entry_calls(source: str) -> set[str]:
    """Return statically imported/direct production renderer entry calls."""

    tree = ast.parse(source)
    bindings = _import_bindings(tree)
    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        resolved = _resolved_call_name(node.func, bindings)
        if resolved is None:
            continue
        leaf = resolved.rsplit(".", 1)[-1]
        if leaf in _PRODUCTION_RENDER_ENTRIES:
            calls.add(leaf)
    return calls


def _module_reference_violations(module: str, how: str) -> set[str]:
    violations: set[str] = set()
    if module == "matplotlib.pyplot" or module.startswith("matplotlib.pyplot."):
        violations.add(f"{how}: {module}")
    root = module.split(".", 1)[0]
    if root in _FORBIDDEN_ROOTS:
        violations.add(f"{how}: {module}")
    if module in _PROJECTION_MODULES and how.startswith("renderer"):
        violations.add(f"{how}: {module}")
    return violations


def _analyze(
    source: str,
    *,
    role: str = "production",
) -> set[str]:
    """Return every boundary violation found in one source file."""

    tree = ast.parse(source)
    bindings = _import_bindings(tree)
    violations: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                violations |= _module_reference_violations(
                    alias.name,
                    f"{role} import",
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            how = f"{role} import-from"
            violations |= _module_reference_violations(node.module, how)
            if node.module == "matplotlib":
                for alias in node.names:
                    if alias.name == "pyplot":
                        violations.add(f"{how}: matplotlib.pyplot")
            if node.level == 0 and node.module.split(".", 1)[0] in (
                _FORBIDDEN_ROOTS
            ):
                violations.add(f"{how}: {node.module}")
        elif isinstance(node, ast.Call):
            callee = node.func
            if isinstance(callee, ast.Attribute) and callee.attr == "contour":
                violations.add(f"{role} .contour call")
            dynamic_module: str | None = None
            if (
                isinstance(callee, ast.Attribute)
                and callee.attr == "import_module"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                dynamic_module = node.args[0].value
            if (
                isinstance(callee, ast.Name)
                and callee.id == "__import__"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                dynamic_module = node.args[0].value
            if dynamic_module is not None:
                violations |= _module_reference_violations(
                    dynamic_module,
                    f"{role} dynamic import",
                )
            if role == "renderer":
                resolved = _resolved_call_name(callee, bindings)
                name = resolved.rsplit(".", 1)[-1] if resolved else None
                if name in _RENDERER_FORBIDDEN_CALLS:
                    violations.add(f"renderer forbidden call: {name}")
        elif isinstance(node, ast.Attribute):
            chain = _dotted_attribute_chain(node)
            if chain == "matplotlib.pyplot" or chain.startswith(
                "matplotlib.pyplot.",
            ):
                violations.add(f"{role} matplotlib.pyplot attribute use")
    return violations


def _caller_files(function_name: str) -> list[Path]:
    callers: list[Path] = []
    for path in _production_files():
        if function_name in _production_entry_calls(
            path.read_text(encoding="utf-8"),
        ):
            callers.append(path)
    return callers


def _relative(path: Path) -> str:
    return path.relative_to(PACKAGE_ROOT.parent).as_posix()


def test_production_package_has_no_boundary_violations() -> None:
    files = _production_files()
    assert len(files) > 40, "the production package scan must cover real files"
    for path in files:
        role = "renderer" if path.name == "renderer.py" else "production"
        violations = _analyze(
            path.read_text(encoding="utf-8"),
            role=role,
        )
        assert not violations, f"{_relative(path)}: {sorted(violations)}"


def test_engine_except_renderer_never_imports_matplotlib() -> None:
    engine_files = [
        path
        for path in (PACKAGE_ROOT / "engine").glob("*.py")
        if path.name != "renderer.py"
    ]
    assert len(engine_files) > 10
    for path in engine_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                assert not (
                    module == "matplotlib" or module.startswith("matplotlib.")
                ), f"{_relative(path)} imports {module}"


def test_engine_never_imports_workers_ui_or_app_controller() -> None:
    for path in (PACKAGE_ROOT / "engine").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                assert not (
                    module.startswith("math_drawing_assistant.workers")
                    or module.startswith("math_drawing_assistant.ui")
                    or module == "math_drawing_assistant.app_controller"
                ), f"{_relative(path)} imports {module}"


def test_renderer_file_set_stays_singleton_and_projection_free() -> None:
    engine_files = sorted(
        path.name for path in (PACKAGE_ROOT / "engine").glob("*renderer*.py")
    )
    assert engine_files == ["renderer.py"]
    renderer_source = (PACKAGE_ROOT / "engine" / "renderer.py").read_text(
        encoding="utf-8",
    )
    for module_name in ("oval_geometry", "hyperbola_geometry", "parabola_geometry"):
        assert f"from math_drawing_assistant.engine.{module_name}" not in (
            renderer_source
        )
        assert f"import math_drawing_assistant.engine.{module_name}" not in (
            renderer_source
        )


def test_render_explicit_png_calls_stay_in_scene_executor_only() -> None:
    callers = _caller_files("render_explicit_png")
    assert callers == [PACKAGE_ROOT / "engine" / "scene_executor.py"]


def test_unified_entry_has_no_production_caller_in_stage_15a() -> None:
    assert _caller_files("render_sampled_curve_png") == []


def test_engine_exports_one_unified_renderer_entry_and_no_split_entries() -> None:
    assert "render_sampled_curve_png" in public_engine.__all__
    assert "render_explicit_png" in public_engine.__all__
    for forbidden in (
        "render_line_png",
        "render_circle_png",
        "render_ellipse_png",
        "render_hyperbola_png",
        "render_parabola_png",
        "render_geometry_png",
    ):
        assert forbidden not in public_engine.__all__


SYNTHETIC_VIOLATIONS = (
    (
        "import matplotlib.pyplot as mp\n",
        "production",
        "import: matplotlib.pyplot",
    ),
    (
        "from matplotlib import pyplot as p\n",
        "production",
        "import-from: matplotlib.pyplot",
    ),
    (
        "from matplotlib.pyplot import figure\n",
        "production",
        "import-from: matplotlib.pyplot",
    ),
    (
        "import matplotlib\n\n\ndef draw():\n    return matplotlib.pyplot.figure()\n",
        "production",
        "matplotlib.pyplot attribute use",
    ),
    (
        "import importlib\n\n\ndef load():\n    return importlib.import_module('matplotlib.pyplot')\n",
        "production",
        "dynamic import: matplotlib.pyplot",
    ),
    (
        "value = __import__('tests.test_stage14e_acceptance')\n",
        "production",
        "dynamic import: tests.test_stage14e_acceptance",
    ),
    (
        "from benchmarks.m1_5_performance_v1 import run_all\n",
        "production",
        "import-from: benchmarks.m1_5_performance_v1",
    ),
    (
        "def draw(axes, x, y):\n    return axes.contour(x, y)\n",
        "production",
        ".contour call",
    ),
    (
        "from math_drawing_assistant.engine.samplers import sample_parameterized_curve\n\n\ndef run(plan):\n    return sample_parameterized_curve(plan)\n",
        "renderer",
        "renderer forbidden call: sample_parameterized_curve",
    ),
    (
        "from math_drawing_assistant.engine.plot_analyzer import analyze_plot_item\n\n\ndef run(request):\n    return analyze_plot_item(request)\n",
        "renderer",
        "renderer forbidden call: analyze_plot_item",
    ),
    (
        "from math_drawing_assistant.engine.oval_geometry import project_oval_geometry\n",
        "renderer",
        "renderer import-from: math_drawing_assistant.engine.oval_geometry",
    ),
)


@pytest.mark.parametrize(
    ("source", "role", "expected_fragment"),
    SYNTHETIC_VIOLATIONS,
    ids=[
        "aliased-pyplot-import",
        "from-matplotlib-pyplot",
        "from-pyplot-module",
        "attribute-chain",
        "dynamic-import_module",
        "dynamic-dunder-import",
        "benchmarks-import",
        "contour-call",
        "renderer-sampler-call",
        "renderer-analyzer-call",
        "renderer-projection-import",
    ],
)
def test_scanner_detects_synthetic_alias_and_indirect_cases(
    source: str,
    role: str,
    expected_fragment: str,
) -> None:
    violations = _analyze(source, role=role)
    assert violations, "scanner must not be bypassable by this construct"
    assert any(
        expected_fragment in violation for violation in violations
    ), f"expected {expected_fragment!r} in {sorted(violations)}"


RENDERER_IMPORT_ALIAS_VIOLATIONS = (
    (
        "from math_drawing_assistant.engine.samplers import sample_parameterized_curve as run_geometry\nrun_geometry(plan)\n",
        "sample_parameterized_curve",
    ),
    (
        "from math_drawing_assistant.engine.plot_analyzer import analyze_plot_item as inspect_item\ninspect_item(request)\n",
        "analyze_plot_item",
    ),
    (
        "from math_drawing_assistant.engine.viewport_resolver import resolve_single_item_viewport as choose_view\nchoose_view(scene, request)\n",
        "resolve_single_item_viewport",
    ),
    (
        "from math_drawing_assistant.engine.render_plan_builder import RenderPlanBuilder as Builder\nBuilder()\n",
        "RenderPlanBuilder",
    ),
    (
        "import math_drawing_assistant.engine.samplers as sampling\nsampling.sample_parameterized_curve(plan)\n",
        "sample_parameterized_curve",
    ),
    (
        "import math_drawing_assistant.engine.plot_analyzer as analyzer\nanalyzer.analyze_plot_item(request)\n",
        "analyze_plot_item",
    ),
    (
        "import math_drawing_assistant.engine.viewport_resolver as resolver\nresolver.resolve_single_item_viewport(scene, request)\n",
        "resolve_single_item_viewport",
    ),
    (
        "import math_drawing_assistant.engine.render_plan_builder as planning\nplanning.RenderPlanBuilder()\n",
        "RenderPlanBuilder",
    ),
)


@pytest.mark.parametrize(
    ("source", "forbidden_name"),
    RENDERER_IMPORT_ALIAS_VIOLATIONS,
    ids=(
        "sampler-from-import-alias",
        "analyzer-from-import-alias",
        "resolver-from-import-alias",
        "builder-from-import-alias",
        "sampler-module-alias",
        "analyzer-module-alias",
        "resolver-module-alias",
        "builder-module-alias",
    ),
)
def test_renderer_alias_rule_independently_catches_each_forbidden_entry(
    source: str,
    forbidden_name: str,
) -> None:
    assert _analyze(source, role="renderer") == {
        f"renderer forbidden call: {forbidden_name}",
    }


PRODUCTION_ENTRY_ALIAS_CALLS = (
    (
        "from math_drawing_assistant.engine.renderer import render_explicit_png as produce\nproduce(plan, sampled)\n",
        "render_explicit_png",
    ),
    (
        "import math_drawing_assistant.engine.renderer as rendering\nrendering.render_explicit_png(plan, sampled)\n",
        "render_explicit_png",
    ),
    (
        "from math_drawing_assistant.engine.renderer import render_sampled_curve_png as produce\nproduce(plan, sampled)\n",
        "render_sampled_curve_png",
    ),
    (
        "import math_drawing_assistant.engine.renderer as rendering\nrendering.render_sampled_curve_png(plan, sampled)\n",
        "render_sampled_curve_png",
    ),
)


@pytest.mark.parametrize(
    ("source", "entry_name"),
    PRODUCTION_ENTRY_ALIAS_CALLS,
    ids=(
        "legacy-from-import-alias",
        "legacy-module-attribute",
        "unified-from-import-alias",
        "unified-module-attribute",
    ),
)
def test_production_entry_rule_independently_catches_each_alias_form(
    source: str,
    entry_name: str,
) -> None:
    assert _production_entry_calls(source) == {entry_name}


def test_scanner_accepts_the_real_backend_agg_and_renderer_imports() -> None:
    assert _analyze(
        "from matplotlib.backends.backend_agg import FigureCanvasAgg\n",
    ) == set()
    assert _analyze(
        "from matplotlib.figure import Figure\n",
    ) == set()
    assert _analyze(
        "from math_drawing_assistant.engine.renderer import render_explicit_png\n",
    ) == set()
