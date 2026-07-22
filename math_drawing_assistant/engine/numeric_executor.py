"""Closed typed execution of stage 7 explicit-function AST nodes with NumPy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, TypeAlias

import numpy as np
from numpy.typing import NDArray

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.plot_specs import (
    ExplicitFunctionSpec,
    _validate_validated_explicit_expression,
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


Float64Vector: TypeAlias = NDArray[np.float64]
NumericValue: TypeAlias = float | Float64Vector
_ValueKind: TypeAlias = Literal["scalar", "input", "temporary"]

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


@dataclass(frozen=True, slots=True)
class NumericExecutionCost:
    """Deterministic vector-liveness cost for the exact postorder strategy."""

    max_live_float64_vectors: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_live_float64_vectors, bool)
            or not isinstance(self.max_live_float64_vectors, int)
        ):
            raise TypeError("max_live_float64_vectors must be an integer.")
        if self.max_live_float64_vectors < 1:
            raise ValueError("max_live_float64_vectors must be positive.")


@dataclass(frozen=True, slots=True)
class NumericExecutionResult:
    """One scalar or owned read-only vector plus its execution cost."""

    value: NumericValue
    cost: NumericExecutionCost

    def __post_init__(self) -> None:
        if not isinstance(self.cost, NumericExecutionCost):
            raise TypeError("cost must be NumericExecutionCost.")
        if isinstance(self.value, np.ndarray):
            if self.value.dtype != np.dtype(np.float64) or self.value.ndim != 1:
                raise TypeError("vector values must be one-dimensional float64 arrays.")
            if self.value.flags.writeable:
                raise ValueError("vector values must be read-only.")
        elif type(self.value) is not float:
            raise TypeError("scalar values must be Python floats.")


@dataclass(slots=True)
class _StackValue:
    value: object
    kind: _ValueKind


def estimate_numeric_execution_cost(
    spec: ExplicitFunctionSpec,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> NumericExecutionCost | ErrorInfo:
    """Estimate peak live float64 vectors without executing or caching the AST."""

    prepared = _prepare_numeric_program(spec, limits=limits)
    if isinstance(prepared, ErrorInfo):
        return prepared
    return _estimate_program_cost(prepared, item_id=spec.item_id)


def execute_explicit_function(
    spec: ExplicitFunctionSpec,
    x: Float64Vector,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> NumericExecutionResult | ErrorInfo:
    """Execute one validated explicit function for one caller-supplied x batch."""

    if not isinstance(limits, ApplicationLimits):
        raise TypeError("limits must be an ApplicationLimits value.")
    if type(spec) is not ExplicitFunctionSpec:
        return _internal_error(
            None,
            "numeric executor requires an exact ExplicitFunctionSpec",
        )
    input_error = _validate_input_array(x, item_id=spec.item_id)
    if input_error is not None:
        return input_error

    prepared = _prepare_numeric_program(spec, limits=limits)
    if isinstance(prepared, ErrorInfo):
        return prepared
    cost = _estimate_program_cost(prepared, item_id=spec.item_id)
    if isinstance(cost, ErrorInfo):
        return cost

    stack: list[_StackValue] = []
    try:
        with np.errstate(divide="ignore", invalid="ignore", over="ignore", under="ignore"):
            for node in prepared:
                execution_error = _execute_instruction(
                    node,
                    stack,
                    x=x,
                    item_id=spec.item_id,
                )
                if execution_error is not None:
                    return execution_error
    except (FloatingPointError, OverflowError, TypeError, ValueError):
        return _internal_error(
            spec.item_id,
            "closed numeric instruction raised an unexpected exception",
        )

    if len(stack) != 1:
        return _internal_error(
            spec.item_id,
            "postorder execution did not leave exactly one value",
        )
    return _finalize_result(
        stack[0],
        spec=spec,
        x=x,
        cost=cost,
    )


def _prepare_numeric_program(
    spec: object,
    *,
    limits: ApplicationLimits,
) -> tuple[RestrictedExpression, ...] | ErrorInfo:
    if not isinstance(limits, ApplicationLimits):
        raise TypeError("limits must be an ApplicationLimits value.")
    if type(spec) is not ExplicitFunctionSpec:
        return _internal_error(None, "numeric program received a non-explicit spec")
    try:
        spec.__post_init__()
        _validate_validated_explicit_expression(
            spec.validated_expression,
            active_limits_version=limits.version,
        )
    except (AttributeError, TypeError, ValueError):
        return _internal_error(spec.item_id, "numeric spec contract mismatch")
    return _compile_postorder(
        spec.expression,
        item_id=spec.item_id,
        max_nodes=limits.max_ast_nodes,
    )


def _compile_postorder(
    expression: object,
    *,
    item_id: str,
    max_nodes: int,
) -> tuple[RestrictedExpression, ...] | ErrorInfo:
    program: list[RestrictedExpression] = []
    pending: list[tuple[object, bool]] = [(expression, False)]
    scheduled_nodes = 0
    while pending:
        node, visited = pending.pop()
        if type(node) not in _EXACT_NODE_TYPES:
            return _internal_error(item_id, "numeric program found an unknown AST node")
        if visited:
            program.append(node)
            continue

        scheduled_nodes += 1
        if scheduled_nodes > max_nodes:
            return _internal_error(item_id, "numeric AST exceeds the active node contract")
        pending.append((node, True))
        if type(node) is SymbolNode:
            if node.name != "x":
                return _internal_error(item_id, "numeric program found a non-x symbol")
        elif type(node) is ConstantNode:
            if node.name not in {"pi", "E"}:
                return _internal_error(item_id, "numeric program found an unknown constant")
        elif type(node) is UnaryOpNode:
            if node.operator not in {UnaryOperator.POSITIVE, UnaryOperator.NEGATIVE}:
                return _internal_error(item_id, "numeric program found an unknown unary operator")
            pending.append((node.operand, False))
        elif type(node) is BinaryOpNode:
            if node.operator not in {
                BinaryOperator.ADD,
                BinaryOperator.SUBTRACT,
                BinaryOperator.MULTIPLY,
                BinaryOperator.DIVIDE,
                BinaryOperator.POWER,
            }:
                return _internal_error(item_id, "numeric program found an unknown binary operator")
            if node.implicit and node.operator is not BinaryOperator.MULTIPLY:
                return _internal_error(item_id, "numeric program found an invalid implicit marker")
            if node.operator is BinaryOperator.POWER and not _is_supported_power(node):
                return _internal_error(item_id, "numeric power is outside the stage 7 contract")
            pending.append((node.right, False))
            pending.append((node.left, False))
        elif type(node) is FunctionCallNode:
            if node.name not in {
                "sin",
                "cos",
                "tan",
                "sqrt",
                "abs",
                "exp",
                "ln",
                "lg",
                "log",
            }:
                return _internal_error(item_id, "numeric program found an unknown function")
            expected_arity = 2 if node.name == "log" else 1
            if len(node.arguments) != expected_arity:
                return _internal_error(item_id, "numeric function has invalid arity")
            if node.name == "log" and not _is_valid_log_base(node.arguments[1]):
                return _internal_error(item_id, "numeric log base violates the stage 7 contract")
            for argument in reversed(node.arguments):
                pending.append((argument, False))
    return tuple(program)


def _is_supported_power(node: BinaryOpNode) -> bool:
    if _is_signed_integer_literal(node.right):
        return True
    if _is_integer_literal_power_chain(node.right):
        return True
    return (
        type(node.left) is NumberNode
        and node.left.lexeme == "2"
        and type(node.right) is SymbolNode
        and node.right.name == "x"
    )


def _is_signed_integer_literal(expression: RestrictedExpression) -> bool:
    if type(expression) is NumberNode:
        return "." not in expression.lexeme
    return (
        type(expression) is UnaryOpNode
        and expression.operator in {UnaryOperator.POSITIVE, UnaryOperator.NEGATIVE}
        and type(expression.operand) is NumberNode
        and "." not in expression.operand.lexeme
    )


def _is_integer_literal_power_chain(expression: RestrictedExpression) -> bool:
    current = expression
    while type(current) is BinaryOpNode:
        if current.operator is not BinaryOperator.POWER:
            return False
        if type(current.left) is not NumberNode or "." in current.left.lexeme:
            return False
        current = current.right
    return _is_signed_integer_literal(current)


def _is_valid_log_base(expression: RestrictedExpression) -> bool:
    if type(expression) is not NumberNode:
        return False
    try:
        value = Decimal(expression.lexeme)
    except InvalidOperation:
        return False
    return value.is_finite() and value > 0 and value != 1


def _estimate_program_cost(
    program: tuple[RestrictedExpression, ...],
    *,
    item_id: str,
) -> NumericExecutionCost | ErrorInfo:
    stack: list[_ValueKind] = []
    peak = 1  # The caller-owned x float64 vector remains live for the whole call.
    for node in program:
        if type(node) in {NumberNode, ConstantNode}:
            stack.append("scalar")
            continue
        if type(node) is SymbolNode:
            if node.name != "x":
                return _internal_error(item_id, "numeric program found a non-x symbol")
            stack.append("input")
            continue

        arity = _instruction_arity(node)
        if arity is None or len(stack) < arity:
            return _internal_error(item_id, "numeric cost stack underflow")
        live_temporaries = sum(kind == "temporary" for kind in stack)
        operands = stack[-arity:]
        del stack[-arity:]
        vector_result = any(kind != "scalar" for kind in operands)
        if vector_result:
            extra_outputs = 2 if type(node) is FunctionCallNode and node.name == "log" else 1
            peak = max(peak, 1 + live_temporaries + extra_outputs)
            stack.append("temporary")
        else:
            stack.append("scalar")

    if len(stack) != 1:
        return _internal_error(item_id, "numeric cost program did not reduce to one value")
    if stack[0] == "input":
        peak = max(peak, 2)  # Final ownership copy while x remains live.
    return NumericExecutionCost(max_live_float64_vectors=peak)


def _instruction_arity(node: RestrictedExpression) -> int | None:
    if type(node) is UnaryOpNode:
        return 1
    if type(node) is BinaryOpNode:
        return 2
    if type(node) is FunctionCallNode:
        if node.name == "log":
            return 2
        return 1
    return None


def _execute_instruction(
    node: RestrictedExpression,
    stack: list[_StackValue],
    *,
    x: Float64Vector,
    item_id: str,
) -> ErrorInfo | None:
    if type(node) is NumberNode:
        stack.append(_StackValue(np.float64(node.lexeme), "scalar"))
        return None
    if type(node) is SymbolNode:
        if node.name != "x":
            return _internal_error(item_id, "numeric execution found a non-x symbol")
        stack.append(_StackValue(x, "input"))
        return None
    if type(node) is ConstantNode:
        if node.name == "pi":
            stack.append(_StackValue(np.float64(np.pi), "scalar"))
            return None
        if node.name == "E":
            stack.append(_StackValue(np.float64(np.e), "scalar"))
            return None
        return _internal_error(item_id, "numeric execution found an unknown constant")

    arity = _instruction_arity(node)
    if arity is None or len(stack) < arity:
        return _internal_error(item_id, "numeric execution stack underflow")
    operands = stack[-arity:]
    del stack[-arity:]
    vector_result = any(operand.kind != "scalar" for operand in operands)

    if type(node) is UnaryOpNode:
        if node.operator is UnaryOperator.POSITIVE:
            raw_result = np.positive(operands[0].value)
        elif node.operator is UnaryOperator.NEGATIVE:
            raw_result = np.negative(operands[0].value)
        else:
            return _internal_error(item_id, "numeric execution found an unknown unary operator")
    elif type(node) is BinaryOpNode:
        left = operands[0].value
        right = operands[1].value
        if node.operator is BinaryOperator.ADD:
            raw_result = np.add(left, right)
        elif node.operator is BinaryOperator.SUBTRACT:
            raw_result = np.subtract(left, right)
        elif node.operator is BinaryOperator.MULTIPLY:
            raw_result = np.multiply(left, right)
        elif node.operator is BinaryOperator.DIVIDE:
            raw_result = np.divide(left, right)
        elif node.operator is BinaryOperator.POWER:
            raw_result = np.power(left, right)
        else:
            return _internal_error(item_id, "numeric execution found an unknown binary operator")
    elif type(node) is FunctionCallNode:
        raw_result = _execute_function(node, operands, item_id=item_id)
        if isinstance(raw_result, ErrorInfo):
            return raw_result
    else:
        return _internal_error(item_id, "numeric execution found an unknown AST node")

    checked = _validate_operation_output(
        raw_result,
        expect_vector=vector_result,
        batch_length=x.shape[0],
        item_id=item_id,
    )
    if isinstance(checked, ErrorInfo):
        return checked
    stack.append(checked)
    return None


def _execute_function(
    node: FunctionCallNode,
    operands: list[_StackValue],
    *,
    item_id: str,
) -> object | ErrorInfo:
    value = operands[0].value
    if node.name == "sin":
        return np.sin(value)
    if node.name == "cos":
        return np.cos(value)
    if node.name == "tan":
        return np.tan(value)
    if node.name == "sqrt":
        return np.sqrt(value)
    if node.name == "abs":
        return np.abs(value)
    if node.name == "exp":
        return np.exp(value)
    if node.name == "ln":
        return np.log(value)
    if node.name == "lg":
        return np.log10(value)
    if node.name == "log":
        if len(operands) != 2:
            return _internal_error(item_id, "numeric log instruction has invalid arity")
        return np.divide(np.log(value), np.log(operands[1].value))
    return _internal_error(item_id, "numeric execution found an unknown function")


def _validate_operation_output(
    value: object,
    *,
    expect_vector: bool,
    batch_length: int,
    item_id: str,
) -> _StackValue | ErrorInfo:
    if expect_vector:
        if type(value) is not np.ndarray:
            return _internal_error(item_id, "vector instruction returned a non-array")
        if value.dtype != np.dtype(np.float64):
            return _internal_error(item_id, "vector instruction returned a non-float64 dtype")
        if value.shape != (batch_length,):
            return _internal_error(item_id, "vector instruction returned an invalid shape")
        return _StackValue(value, "temporary")

    if type(value) is np.ndarray:
        if value.dtype != np.dtype(np.float64):
            return _internal_error(item_id, "scalar instruction returned a non-float64 dtype")
        if value.shape != ():
            return _internal_error(item_id, "scalar instruction returned a non-scalar shape")
        return _StackValue(np.float64(value[()]), "scalar")
    if type(value) is np.float64:
        return _StackValue(value, "scalar")
    if type(value) is float:
        return _StackValue(np.float64(value), "scalar")
    return _internal_error(item_id, "scalar instruction returned an invalid dtype")


def _finalize_result(
    entry: _StackValue,
    *,
    spec: ExplicitFunctionSpec,
    x: Float64Vector,
    cost: NumericExecutionCost,
) -> NumericExecutionResult | ErrorInfo:
    if spec.free_variables == ():
        if entry.kind != "scalar":
            return _internal_error(spec.item_id, "constant expression returned a vector")
        if type(entry.value) is not np.float64:
            return _internal_error(spec.item_id, "constant expression returned an invalid scalar")
        return NumericExecutionResult(value=float(entry.value), cost=cost)

    if spec.free_variables != ("x",) or entry.kind == "scalar":
        return _internal_error(spec.item_id, "nonconstant expression returned an invalid value")
    if entry.kind == "input":
        vector = np.array(x, dtype=np.float64, copy=True, order="K")
    elif type(entry.value) is np.ndarray:
        vector = entry.value
    else:
        return _internal_error(spec.item_id, "vector result has an invalid representation")
    if vector.dtype != np.dtype(np.float64) or vector.shape != (x.shape[0],):
        return _internal_error(spec.item_id, "final vector violates dtype or shape contract")
    vector.setflags(write=False)
    return NumericExecutionResult(value=vector, cost=cost)


def _validate_input_array(
    x: object,
    *,
    item_id: str,
) -> ErrorInfo | None:
    if type(x) is not np.ndarray:
        return _input_error(item_id, "x must be an exact NumPy array")
    if x.dtype != np.dtype(np.float64):
        return _input_error(item_id, "x dtype must be float64")
    if x.ndim != 1:
        return _input_error(item_id, "x must be one-dimensional")
    if not bool(np.isfinite(x).all()):
        return _input_error(item_id, "x must contain only finite values")
    return None


def _input_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INVALID_REQUEST,
        user_message="数值执行输入必须是一维有限 float64 数组。",
        technical_message=technical_message,
        item_id=item_id,
        field_name="x",
        recoverable=True,
    )


def _internal_error(item_id: str | None, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="数值执行契约无效，请重新提交公式。",
        technical_message=technical_message,
        item_id=item_id,
        field_name="numeric_execution",
        recoverable=False,
    )


__all__ = [
    "Float64Vector",
    "NumericExecutionCost",
    "NumericExecutionResult",
    "NumericValue",
    "estimate_numeric_execution_cost",
    "execute_explicit_function",
]
