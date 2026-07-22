"""Complete recursive-descent parser for the project-owned restricted AST."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TypeAlias, cast

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.equation_splitter import (
    EquationInput,
    ExpressionInput,
)
from math_drawing_assistant.engine.tokenizer import Token, TokenKind
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo, SourceSpan
from math_drawing_assistant.models.restricted_ast import (
    BinaryOpNode,
    BinaryOperator,
    ConstantName,
    ConstantNode,
    FunctionCallNode,
    FunctionName,
    NumberNode,
    RestrictedExpression,
    SymbolNode,
    UnaryOpNode,
    UnaryOperator,
    VariableName,
)


@dataclass(frozen=True, slots=True)
class ParseMetrics:
    """Construction metrics produced by the parser's sole budget authority."""

    token_count: int
    ast_node_count: int
    max_ast_depth: int
    max_function_arguments: int
    max_absolute_literal_exponent: int
    limits_version: str


@dataclass(frozen=True, slots=True)
class ParsedExpressionInput:
    """One completely parsed expression and its construction metrics."""

    expression: RestrictedExpression
    normalized_span: SourceSpan
    source_span: SourceSpan
    metrics: ParseMetrics


@dataclass(frozen=True, slots=True)
class ParsedEquationInput:
    """Two completely parsed equation sides sharing one construction budget."""

    left: RestrictedExpression
    right: RestrictedExpression
    left_normalized_span: SourceSpan
    right_normalized_span: SourceSpan
    left_source_span: SourceSpan
    right_source_span: SourceSpan
    metrics: ParseMetrics


ParsedInput: TypeAlias = ParsedExpressionInput | ParsedEquationInput


@dataclass(frozen=True, slots=True)
class _BuiltExpression:
    node: RestrictedExpression
    depth: int


class _ParseFailure(Exception):
    def __init__(self, error: ErrorInfo) -> None:
        super().__init__(error.code.value)
        self.error = error


class _ConstructionBudget:
    __slots__ = (
        "limits",
        "node_count",
        "max_depth",
        "max_arguments",
        "max_absolute_exponent",
    )

    def __init__(self, limits: ApplicationLimits) -> None:
        self.limits = limits
        self.node_count = 0
        self.max_depth = 0
        self.max_arguments = 0
        self.max_absolute_exponent = 0

    def reserve_node(self, depth: int, source_span: SourceSpan) -> None:
        if self.node_count >= self.limits.max_ast_nodes:
            raise _ParseFailure(
                _error(
                    ErrorCode.AST_NODE_LIMIT_EXCEEDED,
                    "表达式节点数量超过当前安全上限，请缩短后重试。",
                    "AST node limit exceeded during construction",
                    source_span,
                ),
            )
        if depth > self.limits.max_nesting_depth:
            raise _ParseFailure(
                _error(
                    ErrorCode.AST_DEPTH_LIMIT_EXCEEDED,
                    "表达式嵌套超过当前安全上限，请简化后重试。",
                    "AST depth limit exceeded during construction",
                    source_span,
                ),
            )
        self.node_count += 1
        self.max_depth = max(self.max_depth, depth)

    def observe_arguments(self, count: int, source_span: SourceSpan) -> None:
        if count > self.limits.max_function_arguments:
            raise _ParseFailure(
                _error(
                    ErrorCode.FUNCTION_ARGUMENT_ERROR,
                    "函数参数数量超过当前安全上限。",
                    "function argument limit exceeded during construction",
                    source_span,
                ),
            )
        self.max_arguments = max(self.max_arguments, count)

    def observe_exponent(self, value: int, source_span: SourceSpan) -> None:
        absolute = abs(value)
        if absolute > self.limits.max_absolute_exponent:
            raise _ParseFailure(
                _error(
                    ErrorCode.EXPONENT_OUT_OF_RANGE,
                    "指数超过当前安全上限，请减小后重试。",
                    "literal exponent limit exceeded during construction",
                    source_span,
                ),
            )
        self.max_absolute_exponent = max(self.max_absolute_exponent, absolute)

    def metrics(self, token_count: int) -> ParseMetrics:
        return ParseMetrics(
            token_count=token_count,
            ast_node_count=self.node_count,
            max_ast_depth=self.max_depth,
            max_function_arguments=self.max_arguments,
            max_absolute_literal_exponent=self.max_absolute_exponent,
            limits_version=self.limits.version,
        )


class _Parser:
    __slots__ = ("tokens", "limits", "budget", "index", "eof_span", "bar_depth")

    _PRIMARY_STARTS = frozenset(
        {
            TokenKind.NUMBER,
            TokenKind.VARIABLE,
            TokenKind.CONSTANT,
            TokenKind.FUNCTION,
            TokenKind.LEFT_PAREN,
            TokenKind.BAR,
        },
    )
    _IMPLICIT_PAIRS = frozenset(
        {
            (TokenKind.NUMBER, TokenKind.VARIABLE),
            (TokenKind.NUMBER, TokenKind.LEFT_PAREN),
            (TokenKind.RIGHT_PAREN, TokenKind.LEFT_PAREN),
        },
    )
    _FUNCTION_ARITY = {
        "sin": 1,
        "cos": 1,
        "tan": 1,
        "sqrt": 1,
        "abs": 1,
        "exp": 1,
        "ln": 1,
        "lg": 1,
        "log": 2,
    }

    def __init__(
        self,
        tokens: tuple[Token, ...],
        *,
        limits: ApplicationLimits,
        budget: _ConstructionBudget,
        eof_span: SourceSpan,
    ) -> None:
        self.tokens = tokens
        self.limits = limits
        self.budget = budget
        self.index = 0
        self.eof_span = eof_span
        self.bar_depth = 0

    def parse_complete(self) -> RestrictedExpression:
        built = self._parse_additive()
        if self.index != len(self.tokens):
            token = self.tokens[self.index]
            raise _ParseFailure(
                _error(
                    ErrorCode.PARSER_SYNTAX_ERROR,
                    "公式包含无法解析的多余内容，请检查后重试。",
                    f"unconsumed token kind={token.kind.value}",
                    token.source_span,
                ),
            )
        return built.node

    def _parse_additive(self) -> _BuiltExpression:
        left = self._parse_multiplicative()
        while self._peek_kind() in {TokenKind.PLUS, TokenKind.MINUS}:
            operator_token = self._advance()
            right = self._parse_multiplicative()
            operator = (
                BinaryOperator.ADD
                if operator_token.kind is TokenKind.PLUS
                else BinaryOperator.SUBTRACT
            )
            left = self._binary(operator, left, right)
        return left

    def _parse_multiplicative(self) -> _BuiltExpression:
        left = self._parse_unary()
        while self.index < len(self.tokens):
            next_kind = self.tokens[self.index].kind
            if next_kind in {TokenKind.STAR, TokenKind.SLASH}:
                operator_token = self._advance()
                right = self._parse_unary()
                operator = (
                    BinaryOperator.MULTIPLY
                    if operator_token.kind is TokenKind.STAR
                    else BinaryOperator.DIVIDE
                )
                if operator is BinaryOperator.DIVIDE:
                    self._check_rational_literal(left.node, right.node)
                left = self._binary(operator, left, right)
                continue

            if next_kind is TokenKind.BAR and self.bar_depth > 0:
                break
            if next_kind not in self._PRIMARY_STARTS:
                break

            previous_kind = self.tokens[self.index - 1].kind
            pair = (previous_kind, next_kind)
            if pair not in self._IMPLICIT_PAIRS:
                token = self.tokens[self.index]
                raise _ParseFailure(
                    _error(
                        ErrorCode.IMPLICIT_MULTIPLICATION_NOT_ALLOWED,
                        "这里的相邻写法不在隐式乘法白名单中，请补写 *。",
                        (
                            "implicit multiplication pair rejected "
                            f"left={previous_kind.value} right={next_kind.value}"
                        ),
                        token.source_span,
                    ),
                )
            right = self._parse_unary()
            left = self._binary(BinaryOperator.MULTIPLY, left, right, implicit=True)
        return left

    def _parse_unary(self) -> _BuiltExpression:
        kind = self._peek_kind()
        if kind not in {TokenKind.PLUS, TokenKind.MINUS}:
            return self._parse_power()

        token = self._advance()
        operand = self._parse_unary()
        operator = (
            UnaryOperator.POSITIVE
            if token.kind is TokenKind.PLUS
            else UnaryOperator.NEGATIVE
        )
        depth = operand.depth + 1
        span = SourceSpan(token.source_span.start, operand.node.source_span.end)
        normalized_span = SourceSpan(
            token.normalized_span.start,
            operand.node.normalized_span.end,
        )
        self.budget.reserve_node(depth, span)
        return _BuiltExpression(
            UnaryOpNode(
                normalized_span=normalized_span,
                source_span=span,
                operator=operator,
                operand=operand.node,
            ),
            depth,
        )

    def _parse_power(self) -> _BuiltExpression:
        left = self._parse_primary()
        if self._peek_kind() is not TokenKind.POWER:
            return left

        self._advance()
        right = self._parse_unary()
        self._check_direct_literal_exponent(right.node)
        return self._binary(BinaryOperator.POWER, left, right)

    def _parse_primary(self) -> _BuiltExpression:
        token = self._peek()
        if token is None:
            raise _ParseFailure(
                _error(
                    ErrorCode.PARSER_SYNTAX_ERROR,
                    "公式尚未结束，请补全后重试。",
                    "expression expected at EOF",
                    self.eof_span,
                ),
            )

        if token.kind is TokenKind.NUMBER:
            self._advance()
            self.budget.reserve_node(1, token.source_span)
            return _BuiltExpression(
                NumberNode(
                    normalized_span=token.normalized_span,
                    source_span=token.source_span,
                    lexeme=token.lexeme,
                ),
                1,
            )
        if token.kind is TokenKind.VARIABLE:
            self._advance()
            self.budget.reserve_node(1, token.source_span)
            return _BuiltExpression(
                SymbolNode(
                    normalized_span=token.normalized_span,
                    source_span=token.source_span,
                    name=cast(VariableName, token.lexeme),
                ),
                1,
            )
        if token.kind is TokenKind.CONSTANT:
            self._advance()
            self.budget.reserve_node(1, token.source_span)
            return _BuiltExpression(
                ConstantNode(
                    normalized_span=token.normalized_span,
                    source_span=token.source_span,
                    name=cast(ConstantName, token.lexeme),
                ),
                1,
            )
        if token.kind is TokenKind.FUNCTION:
            return self._parse_function_call()
        if token.kind is TokenKind.LEFT_PAREN:
            return self._parse_group()
        if token.kind is TokenKind.BAR:
            return self._parse_absolute_value()

        raise _ParseFailure(
            _error(
                ErrorCode.PARSER_SYNTAX_ERROR,
                "此处需要数字、变量、常量、函数或括号表达式。",
                f"primary expression expected, found={token.kind.value}",
                token.source_span,
            ),
        )

    def _parse_group(self) -> _BuiltExpression:
        opening = self._advance()
        if self._peek_kind() is TokenKind.RIGHT_PAREN:
            raise _ParseFailure(
                _error(
                    ErrorCode.PARSER_SYNTAX_ERROR,
                    "括号内不能为空，请补充表达式。",
                    "empty parenthesized expression",
                    self.tokens[self.index].source_span,
                ),
            )
        inner = self._parse_additive()
        closing = self._require(
            TokenKind.RIGHT_PAREN,
            "缺少右括号，请补全后重试。",
            "right parenthesis required",
        )
        widened = replace(
            inner.node,
            normalized_span=SourceSpan(
                opening.normalized_span.start,
                closing.normalized_span.end,
            ),
            source_span=SourceSpan(opening.source_span.start, closing.source_span.end),
        )
        return _BuiltExpression(widened, inner.depth)

    def _parse_function_call(self) -> _BuiltExpression:
        function_token = self._advance()
        if self._peek_kind() is not TokenKind.LEFT_PAREN:
            raise _ParseFailure(
                _error(
                    ErrorCode.FUNCTION_CALL_REQUIRED,
                    "函数名后必须使用括号，例如 sin(x)。",
                    "approved function token not followed by left parenthesis",
                    function_token.source_span,
                ),
            )
        self._advance()

        arguments: list[_BuiltExpression] = []
        if self._peek_kind() is not TokenKind.RIGHT_PAREN:
            while True:
                if self._peek_kind() is TokenKind.COMMA:
                    raise _ParseFailure(
                        _error(
                            ErrorCode.FUNCTION_ARGUMENT_ERROR,
                            "函数参数不能为空，请补全后重试。",
                            "empty function argument before comma",
                            self.tokens[self.index].source_span,
                        ),
                    )
                arguments.append(self._parse_additive())
                self.budget.observe_arguments(
                    len(arguments),
                    arguments[-1].node.source_span,
                )
                if self._peek_kind() is not TokenKind.COMMA:
                    break
                comma = self._advance()
                if self._peek_kind() in {TokenKind.RIGHT_PAREN, None}:
                    raise _ParseFailure(
                        _error(
                            ErrorCode.FUNCTION_ARGUMENT_ERROR,
                            "逗号后缺少函数参数，请补全后重试。",
                            "empty function argument after comma",
                            comma.source_span,
                        ),
                    )
                if len(arguments) >= self.limits.max_function_arguments:
                    self.budget.observe_arguments(
                        len(arguments) + 1,
                        comma.source_span,
                    )

        closing = self._require(
            TokenKind.RIGHT_PAREN,
            "函数调用缺少右括号，请补全后重试。",
            "function right parenthesis required",
        )
        name = function_token.lexeme
        expected = self._FUNCTION_ARITY[name]
        if name == "log" and len(arguments) == 1:
            raise _ParseFailure(
                _error(
                    ErrorCode.LOG_REQUIRES_BASE,
                    "请改用 ln(x)、lg(x) 或 log(x, b)。",
                    "log call omitted its required base",
                    function_token.source_span,
                ),
            )
        if len(arguments) != expected:
            raise _ParseFailure(
                _error(
                    ErrorCode.FUNCTION_ARGUMENT_ERROR,
                    "函数参数数量不正确，请按支持的写法修改。",
                    (
                        "function arity mismatch "
                        f"name={name} expected={expected} actual={len(arguments)}"
                    ),
                    function_token.source_span,
                ),
            )

        depth = 1 + max((argument.depth for argument in arguments), default=0)
        source_span = SourceSpan(
            function_token.source_span.start,
            closing.source_span.end,
        )
        normalized_span = SourceSpan(
            function_token.normalized_span.start,
            closing.normalized_span.end,
        )
        self.budget.reserve_node(depth, source_span)
        return _BuiltExpression(
            FunctionCallNode(
                normalized_span=normalized_span,
                source_span=source_span,
                name=cast(FunctionName, name),
                arguments=tuple(argument.node for argument in arguments),
            ),
            depth,
        )

    def _parse_absolute_value(self) -> _BuiltExpression:
        opening = self._advance()
        if self.bar_depth > 0 or self._peek_kind() is TokenKind.BAR:
            location = self._peek().source_span if self._peek() is not None else self.eof_span
            raise _ParseFailure(
                _error(
                    ErrorCode.NESTED_ABSOLUTE_VALUE,
                    "暂不支持直接嵌套竖线，请改用 abs(abs(x))。",
                    "nested absolute-value bar rejected",
                    location,
                ),
            )

        self.bar_depth += 1
        try:
            argument = self._parse_additive()
        finally:
            self.bar_depth -= 1
        closing = self._require(
            TokenKind.BAR,
            "绝对值竖线未闭合，请补全后重试。",
            "closing absolute-value bar required",
        )
        depth = argument.depth + 1
        source_span = SourceSpan(opening.source_span.start, closing.source_span.end)
        normalized_span = SourceSpan(
            opening.normalized_span.start,
            closing.normalized_span.end,
        )
        self.budget.reserve_node(depth, source_span)
        return _BuiltExpression(
            FunctionCallNode(
                normalized_span=normalized_span,
                source_span=source_span,
                name="abs",
                arguments=(argument.node,),
            ),
            depth,
        )

    def _binary(
        self,
        operator: BinaryOperator,
        left: _BuiltExpression,
        right: _BuiltExpression,
        *,
        implicit: bool = False,
    ) -> _BuiltExpression:
        depth = max(left.depth, right.depth) + 1
        source_span = SourceSpan(
            left.node.source_span.start,
            right.node.source_span.end,
        )
        normalized_span = SourceSpan(
            left.node.normalized_span.start,
            right.node.normalized_span.end,
        )
        self.budget.reserve_node(depth, source_span)
        return _BuiltExpression(
            BinaryOpNode(
                normalized_span=normalized_span,
                source_span=source_span,
                operator=operator,
                left=left.node,
                right=right.node,
                implicit=implicit,
            ),
            depth,
        )

    def _check_direct_literal_exponent(self, expression: RestrictedExpression) -> None:
        sign = 1
        literal: NumberNode | None = None
        if isinstance(expression, NumberNode):
            literal = expression
        elif isinstance(expression, UnaryOpNode) and isinstance(
            expression.operand,
            NumberNode,
        ):
            literal = expression.operand
            if expression.operator is UnaryOperator.NEGATIVE:
                sign = -1
        if literal is None:
            return
        if "." in literal.lexeme:
            raise _ParseFailure(
                _error(
                    ErrorCode.UNSUPPORTED_EXPONENT,
                    "当前版本暂不支持小数指数。",
                    "decimal literal exponent rejected by stage 7 contract",
                    expression.source_span,
                ),
            )
        self.budget.observe_exponent(sign * int(literal.lexeme), expression.source_span)

    def _check_rational_literal(
        self,
        left: RestrictedExpression,
        right: RestrictedExpression,
    ) -> None:
        numerator = self._signed_integer_literal(left)
        if numerator is not None:
            if len(numerator.lexeme) > self.limits.max_rational_numerator_digits:
                raise _ParseFailure(
                    _error(
                        ErrorCode.RATIONAL_LITERAL_TOO_LONG,
                        "分数分子超过当前安全上限。",
                        "rational numerator digit limit exceeded",
                        left.source_span,
                    ),
                )
        denominator = self._signed_integer_literal(right)
        if denominator is not None:
            if len(denominator.lexeme) > self.limits.max_rational_denominator_digits:
                raise _ParseFailure(
                    _error(
                        ErrorCode.RATIONAL_LITERAL_TOO_LONG,
                        "分数分母超过当前安全上限。",
                        "rational denominator digit limit exceeded",
                        right.source_span,
                    ),
                )

    @staticmethod
    def _signed_integer_literal(
        expression: RestrictedExpression,
    ) -> NumberNode | None:
        if isinstance(expression, NumberNode) and "." not in expression.lexeme:
            return expression
        if (
            isinstance(expression, UnaryOpNode)
            and expression.operator
            in {UnaryOperator.POSITIVE, UnaryOperator.NEGATIVE}
            and isinstance(expression.operand, NumberNode)
            and "." not in expression.operand.lexeme
        ):
            return expression.operand
        return None

    def _peek(self) -> Token | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _peek_kind(self) -> TokenKind | None:
        token = self._peek()
        return token.kind if token is not None else None

    def _advance(self) -> Token:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def _require(
        self,
        kind: TokenKind,
        user_message: str,
        technical_message: str,
    ) -> Token:
        token = self._peek()
        if token is None:
            raise _ParseFailure(
                _error(
                    ErrorCode.PARSER_SYNTAX_ERROR,
                    user_message,
                    technical_message,
                    self.eof_span,
                ),
            )
        if token.kind is not kind:
            raise _ParseFailure(
                _error(
                    ErrorCode.PARSER_SYNTAX_ERROR,
                    user_message,
                    f"{technical_message}; found={token.kind.value}",
                    token.source_span,
                ),
            )
        return self._advance()


def parse_input(
    input_value: ExpressionInput | EquationInput,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> ParsedInput | ErrorInfo:
    """Parse every supplied token exactly once into the restricted AST."""

    if not isinstance(input_value, (ExpressionInput, EquationInput)):
        raise TypeError("input_value must be an ExpressionInput or EquationInput.")
    if not isinstance(limits, ApplicationLimits):
        raise TypeError("limits must be an ApplicationLimits value.")

    budget = _ConstructionBudget(limits)
    try:
        if isinstance(input_value, ExpressionInput):
            expression = _Parser(
                input_value.tokens,
                limits=limits,
                budget=budget,
                eof_span=SourceSpan(input_value.source_span.end, input_value.source_span.end),
            ).parse_complete()
            return ParsedExpressionInput(
                expression=expression,
                normalized_span=input_value.normalized_span,
                source_span=input_value.source_span,
                metrics=budget.metrics(len(input_value.tokens)),
            )

        left = _Parser(
            input_value.left_tokens,
            limits=limits,
            budget=budget,
            eof_span=SourceSpan(
                input_value.left_source_span.end,
                input_value.left_source_span.end,
            ),
        ).parse_complete()
        right = _Parser(
            input_value.right_tokens,
            limits=limits,
            budget=budget,
            eof_span=SourceSpan(
                input_value.right_source_span.end,
                input_value.right_source_span.end,
            ),
        ).parse_complete()
        return ParsedEquationInput(
            left=left,
            right=right,
            left_normalized_span=input_value.left_normalized_span,
            right_normalized_span=input_value.right_normalized_span,
            left_source_span=input_value.left_source_span,
            right_source_span=input_value.right_source_span,
            metrics=budget.metrics(
                len(input_value.left_tokens) + len(input_value.right_tokens) + 1,
            ),
        )
    except _ParseFailure as failure:
        return failure.error


def _error(
    code: ErrorCode,
    user_message: str,
    technical_message: str,
    source_location: SourceSpan,
) -> ErrorInfo:
    return ErrorInfo(
        code=code,
        user_message=user_message,
        technical_message=technical_message,
        field_name="input_text",
        source_location=source_location,
        recoverable=True,
    )


__all__ = [
    "ParseMetrics",
    "ParsedEquationInput",
    "ParsedExpressionInput",
    "ParsedInput",
    "parse_input",
]
