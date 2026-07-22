"""Public input-front-end and stage 7 restricted-analysis contracts."""

from math_drawing_assistant.engine.equation_splitter import (
    EquationInput,
    ExpressionInput,
    split_equation,
)
from math_drawing_assistant.engine.normalizer import NormalizedInput, normalize_input
from math_drawing_assistant.engine.numeric_executor import (
    Float64Vector,
    NUMERIC_EXECUTOR_CONTRACT_VERSION,
    NumericExecutionCost,
    NumericExecutionResult,
    NumericValue,
    estimate_numeric_execution_cost,
    execute_explicit_function,
)
from math_drawing_assistant.engine.render_plan_builder import (
    RenderPlanBuilder,
    build_single_explicit_render_plan,
)
from math_drawing_assistant.engine.parser import (
    ParseMetrics,
    ParsedEquationInput,
    ParsedExpressionInput,
    ParsedInput,
    parse_input,
)
from math_drawing_assistant.engine.plot_classifier import (
    ExplicitFunctionCandidate,
    classify_plot,
)
from math_drawing_assistant.engine.source_map import SourceMap
from math_drawing_assistant.engine.spec_builder import (
    build_explicit_function_spec,
    build_explicit_scene_spec,
)
from math_drawing_assistant.engine.tokenizer import (
    APPROVED_CONSTANTS,
    APPROVED_FUNCTIONS,
    APPROVED_VARIABLES,
    Token,
    TokenKind,
    tokenize,
)
from math_drawing_assistant.engine.viewport_resolver import (
    ViewportResolution,
    resolve_single_explicit_viewport,
)
from math_drawing_assistant.engine.validators import (
    ExplicitValidation,
    analyze_explicit_function,
    validate_explicit_candidate,
)

__all__ = [
    "APPROVED_CONSTANTS",
    "APPROVED_FUNCTIONS",
    "APPROVED_VARIABLES",
    "EquationInput",
    "ExplicitFunctionCandidate",
    "ExplicitValidation",
    "ExpressionInput",
    "Float64Vector",
    "NormalizedInput",
    "NUMERIC_EXECUTOR_CONTRACT_VERSION",
    "NumericExecutionCost",
    "NumericExecutionResult",
    "NumericValue",
    "ParseMetrics",
    "ParsedEquationInput",
    "ParsedExpressionInput",
    "ParsedInput",
    "RenderPlanBuilder",
    "SourceMap",
    "Token",
    "TokenKind",
    "ViewportResolution",
    "analyze_explicit_function",
    "build_explicit_function_spec",
    "build_explicit_scene_spec",
    "build_single_explicit_render_plan",
    "classify_plot",
    "normalize_input",
    "estimate_numeric_execution_cost",
    "execute_explicit_function",
    "parse_input",
    "resolve_single_explicit_viewport",
    "split_equation",
    "tokenize",
    "validate_explicit_candidate",
]
