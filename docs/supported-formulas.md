# 支持公式与横切契约

文档版本：stage-8c1-render-plan-budget-v1-worktree
状态：阶段 7、8A、8B 已通过；阶段 8C-1 的单项 RenderPlan、正式标量预算和 approval receipt 已实现。本文不声明 8C-2、sampler 或阶段 9 已实现。
单一事实来源职责：本文件登记输入语法、转换表、token 白名单、limits 字段与当前值、稳定错误码及验收矩阵。限制数值的唯一可执行来源仍是 `math_drawing_assistant/config/limits.py`。

## 当前实现边界与正式生产调用图

当前仓库正式生产调用图的统一入口是 `analyze_explicit_function`，执行以下数据流：

```text
原始用户文本
→ normalize_input
→ NormalizedInput(text, SourceMap)
→ tokenize
→ tuple[Token, ...]
→ split_equation
→ ExpressionInput | EquationInput
→ parse_input
→ 项目自有 RestrictedExpression AST
→ classify_plot
→ validate_explicit_candidate
→ ValidatedExplicitExpression
```

阶段 6 的四个模块仍只负责规范化、词法化、SourceMap 和等号拆分，既有语义未改变。阶段 7 不导入或调用 SymPy，不执行数值求值、常量折叠、化简、展开、移项、求解、采样、视口或渲染。`ValidatedExplicitExpression` 是尚未注入 `item_id` 的阶段 7 中间安全产物，不是可直接渲染的 `PlotItemSpec`；后续阶段必须结合调用者持有的 `PlotItemRequest.item_id` 创建正式 Spec。

独立的 parser、classifier 和 validator typed 接口仍公开用于组合与单元测试。正式调用链不得用 parser 或 classifier 的成功结果绕过 validator 构造后续 Spec。`ValidatedExplicitExpression` 的普通公共构造会明确拒绝；正式入口在 validator 成功后签发 parser/active limits 版本一致的内部 contract，再通过 model-owned 工厂重查整棵 AST、自由变量和 span 后构造结果。这是当前正式调用图和公开构造不变量，不宣称 Python 层具有密码学意义上的绝对私有性。

阶段 8A 增加以下唯一单项生产衔接，不重新运行 parser，也不接受原始文本、普通 AST、SymPy 表达式或 callable：

```text
PlotItemRequest + ValidatedExplicitExpression
→ build_explicit_function_spec
→ ExplicitFunctionSpec
→ build_explicit_scene_spec
→ PlotSceneSpec(items=(spec,))
```

`item_id` 只来自 `PlotItemRequest`；数学表达式及其 normalized/source spans、source form、free variables 和 limits version 只来自 `ValidatedExplicitExpression`。请求中的 `AUTO` 或 `EXPLICIT_FUNCTION` 可进入该显函数衔接，其他 PlotKind 拒绝。Scene tuple 顺序是权威顺序，`display_order` 不复制进 Spec。

## 字符与 token 白名单

规范化后只允许 tokenizer 产生下列 token：

| 类别 | 白名单 | 词法结果 |
|---|---|---|
| 数字 | ASCII 整数或有限小数，如 `2`、`12.5`、`.5` | `NUMBER`；保留字符串，不转换为数值对象 |
| 变量 | `x`、`y` | `VARIABLE` |
| 常量 | `pi`、`E` | `CONSTANT` |
| 函数名 | `sin`、`cos`、`tan`、`sqrt`、`abs`、`exp`、`log`、`ln`、`lg` | `FUNCTION`；阶段 6 不检查调用参数语义 |
| 运算符 | `+`、`-`、`*`、`/`、`^` | 对应明确 TokenKind |
| 分隔符 | `(`、`)`、`,`、`|` | 括号与竖线只做机械配对 |
| 方程边界 | `=` | `EQUAL`；只供 equation_splitter 使用 |

ASCII 标识符按连续字母整体扫描。未知标识符不会拆成合法前缀；例如 `sinh` 作为 `[0,4)` 整体拒绝。科学计数法、下划线标识符、属性访问、字符串、方括号、花括号及 Python 语法不在白名单内。

## 受控空格政策

只把 ASCII 空格 U+0020 视为可删除空格：

- 允许公式外围空格；
- 允许运算符、括号、逗号、竖线、等号及明确 token 边界附近的空格，例如 ` x + 1 ` 与 `2 ( x + 1 )`；
- 空格不得把两个 ASCII 字母合并成标识符，也不得把两个数字/小数片段合并成一个数字；因此 `s in(x)`、`p i`、`1 2` 和 `1 .5` 拒绝；
- Tab、CR、LF、全角空格及其他控制字符不作为空格处理，均明确拒绝；
- 换行、逗号和分号绝不被猜测为多公式分隔符。逗号只作为已批准函数参数 token，分号不在白名单内。

删除空格不会改变后续字符映射到原始文本的位置。

## 显式逐字符转换表

不使用 Unicode NFKC/NFKD 或其他宽泛兼容规范化。只执行下表转换。

### 全角字符

| 原字符 | 规范化结果 | 自动测试示例 |
|---|---|---|
| `０`–`９` | `0`–`9`（逐字符对应） | `（１２．５＋３）＝１５．５` |
| `（` | `(` | `（１２）` |
| `）` | `)` | `（１２）` |
| `＝` | `=` | `１＝１` |
| `＋` | `+` | `１＋２` |
| `－` | `-` | `３－２` |
| `＊` | `*` | `２＊x` |
| `／` | `/` | `１／２` |
| `，` | `,` | `log（x，１０）` 中已批准字符逐项转换；全角字母仍拒绝 |
| `．` | `.` | `１２．５` |
| `｜` | `|` | `｜x｜` |

全角拉丁字母（例如 `ｘ`）、全角空格和未列出的全角标点未获批准，必须拒绝。

### Unicode 上标

| 原字符 | 规范化结果 | SourceMap 语义 |
|---|---|---|
| `²` | `^2` | `^` 与 `2` 都映射到原始 `²` 的同一非空区间 |
| `³` | `^3` | `^` 与 `3` 都映射到原始 `³` 的同一非空区间 |

其他上标字符尚未批准。

### 数学运算符

| 原字符 | 规范化结果 |
|---|---|
| `−`（U+2212） | `-` |
| `×` | `*` |
| `·` | `*` |
| `÷` | `/` |

`≤`、`≥`、`≠` 不做运算符转换，而以 `unsupported_relation` 明确拒绝。未列出的数学符号以 `unknown_character` 拒绝。

## 幂、绝对值与隐式乘法

下列输入得到同一规范化文本，但保留各自 SourceMap：

| 原输入 | 规范化文本 |
|---|---|
| `x^2` | `x^2` |
| `x**2` | `x^2` |
| `x²` | `x^2` |
| `x³` | `x^3` |

`x**2` 中规范化后的 `^` 映射到原始 `**` 的完整区间。`x²` 中规范化后的 `^`、`2` 都映射到原始 `²`。

`|x|` 保留为 `BAR, VARIABLE, BAR`。阶段 6 只保证竖线数目可配对，不把它改写为 `abs(x)`、函数调用或 AST。

受控隐式乘法只保留相邻 token：

| 输入 | token lexeme |
|---|---|
| `2x` | `2`, `x` |
| `2(x+1)` | `2`, `(`, `x`, `+`, `1`, `)` |
| `(x+1)(x-1)` | `(`, `x`, `+`, `1`, `)`, `(`, `x`, `-`, `1`, `)` |

不会插入虚构的 `*`，不会构造 AST，也不会执行乘法。

阶段 7 只把下列三个 token 邻接解释为隐式乘法，AST 使用 `BinaryOpNode(MULTIPLY, implicit=True)`：

| 左 token | 右 token | 示例 |
|---|---|---|
| `NUMBER` | `VARIABLE` | `2x` |
| `NUMBER` | `LEFT_PAREN` | `2(x+1)` |
| `RIGHT_PAREN` | `LEFT_PAREN` | `(x+1)(x-1)` |

`x2`、`x(x+1)`、`(x+1)x`、`2sin(x)`、`2pi` 及其他未列邻接均以 `implicit_multiplication_not_allowed` 拒绝；请显式补写 `*`。显式与隐式乘法优先级相同。

## equation_splitter 契约

`split_equation` 只接收 tokenizer 已完整消费的 `tuple[Token, ...]`：

- 没有等号：返回冻结的 `ExpressionInput`，保留完整 token tuple、规范化区间和原始区间；
- 恰好一个等号且两侧非空：返回冻结的 `EquationInput`，左右 token 顺序、规范化区间和原始区间分别保留；
- 拒绝空输入、`=x`、`x=` 和两个或更多等号；
- `<`、`>`、`<=`、`>=`、`!=`、`≤`、`≥`、`≠` 在 tokenizer 阶段以 `unsupported_relation` 拒绝；
- 不交换左右两侧，不判断哪侧是 `y`，不构造 `lhs-rhs`，不移项、不求解、不分类；
- 不从换行、逗号或分号拆分多条公式。

## 阶段 7 自有受限 AST

AST 位于 `math_drawing_assistant/models/restricted_ast.py`，保持 `engine → models` 单向依赖。所有节点都是 frozen、slots、typed dataclass，参数集合使用 tuple，并同时保存规范化 `normalized_span` 与原文 `source_span`。Model-owned 构造不变量检查数字 lexeme、变量/常量/函数封闭名称、运算符、函数 arity 和每一个子节点；只有六种精确 RestrictedExpression 节点能进入整棵图：

| 节点 | 语义 |
|---|---|
| `NumberNode` | 保持为字符串的有界数字字面量 |
| `SymbolNode` | `x` 或 `y` |
| `ConstantNode` | `pi` 或 `E` |
| `UnaryOpNode` | 前缀 `+`、`-` |
| `BinaryOpNode` | `+ - * / ^`，并显式记录是否为白名单隐式乘法 |
| `FunctionCallNode` | 白名单函数调用；BAR 也统一为 `abs` 调用 |

联合类型为 `RestrictedExpression`。Unary/Binary 子节点及 Function arguments tuple 的每个成员均在构造时检查；dict、list、object、未知节点或携带可变 payload 的 tuple 会在 AST 构造边界拒绝。因节点字段只含 frozen SourceSpan、Enum、字符串、布尔、tuple 和其他封闭 AST 节点，合法 AST 是深层不可变图。不支持且不会构造属性、下标、任意调用、Lambda、字符串/字节串、列表、字典、集合、矩阵、comprehension、条件表达式、赋值、关键字参数、导入或任意 Python AST/对象节点。

## Parser 优先级、结合性与完整消费

优先级从低到高：加减；显式乘除/白名单隐式乘法；前缀一元正负；幂；括号、函数调用与绝对值。加减和乘除左结合，幂右结合：

```text
+x        → +(x)
-x^2      → −(x^2)
(-x)^2    → (−x)^2
x^-2      → x^(−2)
-x^-2     → −(x^(−2))
x^2^3     → x^(2^3)，不计算 2^3
x/2*3     → (x/2)*3
x-2+3     → (x-2)+3
```

Parser 只消费阶段 6 typed token，对 EquationInput 两侧分别解析，任何剩余 token、非法逗号或尾部都会结构化拒绝。它不重新扫描原文、不重新做 Unicode 规范化、不插入白名单外乘法、不调用 Python/SymPy parser，也不做代数变换。

构造期由 parser 唯一维护 AST 节点数、AST 最大深度、单函数参数数、直接有符号数字指数、有理数字面量分子/分母位数；有理检查对除法两侧一致识别直接数字或单层一元 `+/-` 包装，并分别读取 numerator/denominator 字段。每个节点在构造前预留预算，超限尽快失败。Validator 只读取 parser metrics 并用集中 `ApplicationLimits.validate_input_complexity` 防御性确认，不重数节点或复制阈值。

## 指数契约

阶段 7 支持：

* 有符号整数字面量指数，如 `x^2`、`x^-2`；每个直接字面量必须满足 `abs(exponent) <= max_absolute_exponent`；
* 右结合的整数字面量幂链，如 `x^2^3`；不进行常量折叠或巨大整数幂计算；
* 阶段 7 当前窄契约选择的指数函数形式 `2^x` 与 `exp(x)`；PRD 只提出指数函数产品范围，没有明确把变量指数底数限定为 2。

当前窄契约拒绝小数字面量指数、`x^x`、`x^(x+1)` 及除 `2^x` 外的变量/复合指数，错误码为 `unsupported_exponent`。扩大指数表达式语言前必须先更新本文和行为测试。

## 函数、arity 与对数

函数白名单沿用 tokenizer：`sin cos tan sqrt abs exp log ln lg`。常量白名单为 `pi E`。函数 token 后必须紧跟 `(`，裸 `sin` 等以 `function_call_required` 拒绝。

* `sin/cos/tan/sqrt/abs/exp/ln/lg`：恰好 1 个参数；
* `log`：恰好 2 个参数；裸 `log(x)` 以 `log_requires_base` 拒绝，并提示改用 `ln(x)`、`lg(x)` 或 `log(x,b)`；
* `log(value, base)` 的 base 必须是大于 0 且不等于 1 的数字字面量；`0`、`1`、负数、变量、常量或复合表达式均以 `invalid_log_base` 拒绝；
* 逗号只允许出现在函数参数列表，不支持关键字参数、省略括号或后缀调用。

## BAR 绝对值契约

`|expr|` 与 `abs(expr)` 统一构造 `FunctionCallNode(name="abs")`，不存在第二套绝对值 AST。支持 `|x|+|x+1|` 和 `abs(abs(x))`；直接嵌套 BAR `||x||` 以 `nested_absolute_value` 拒绝，并提示改用 `abs(abs(x))`。BAR 不使用猜测性回溯。

## M1 显函数分类与 typed validator

阶段 7 只交付 `PlotKind.EXPLICIT_FUNCTION`：

* 单独表达式作为显函数右侧候选；常量表达式合法；
* `y=rhs` 仅在左侧 AST 恰为单独 `y` 且 rhs 不含 `y` 时选择 rhs；
* `lhs=y` 仅在右侧 AST 恰为单独 `y` 且 lhs 不含 `y` 时直接选择 lhs；
* `x=y` 因直接左右互换而合法，不做通用移项；
* `y=y`、`y=x+y` 以显函数变量语义错误拒绝；
* 任何未形成上述直接显函数候选的方程统一以中性的 `unsupported_equation` 阶段性拒绝，消息只说明“当前不支持该方程形式”；
* `y+1=x+2`、`x+y=1`、`x=2`、`x^2+y^2=25`、`y^2=8*x`、高次方程和含函数方程均不在阶段 7 猜测为一次方程或圆锥曲线；不实现次数/系数提取、展开、化简或曲线分类。

Validator 使用明确 AST 联合和 `isinstance` 检查节点、运算、白名单名称、函数 arity、自由变量、对数底数与指数窄契约。显函数自由变量只能是 `x`，也可为空；任何 `y` 均拒绝。相同无效输入重复调用产生相同错误码和原文 span，失败后可继续处理下一条合法输入。

## SourceMap 数据契约

`SourceMap`、`NormalizedInput`、`Token` 和拆分结果均使用 `@dataclass(frozen=True, slots=True)`。所有区间复用 `models.errors.SourceSpan`，统一为零基半开区间 `[start, end)`。

- `character_spans[i]` 是产生规范化字符 `i` 的非空原始区间；
- 一对一替换保留原字符区间；
- 一对多展开为每个结果字符重复同一原始区间；
- 多对一替换保存完整原始区间；
- 非空规范化区间映射为首、末贡献字符覆盖的原始区间；
- 零长度边界在某字符之前时映射到该字符原始区间的 `start`，最终边界映射到最后字符原始区间的 `end`；空 SourceMap 的唯一边界映射到原始偏移 `0`；
- 正式组合入口遇到阶段 6 机械识别的未闭合左括号或 BAR 时，使用 SourceMap 确认开分隔符，并把错误位置适配为原始输入 EOF 零宽区间 `[len(original_text), len(original_text))`；多余右括号仍指向该右括号本身；
- 非法字符索引、越界区间、空字符映射、非单调映射或超出原文的映射都抛出明确的程序员边界异常，不返回伪造区间。

精确示例：

```text
原文 " x² "  → 规范化 "x^2"
x:[1,2)  ^:[2,3)  2:[2,3)

原文 "x**2" → 规范化 "x^2"
x:[0,1)  ^:[1,3)  2:[3,4)
```

## limits 配置索引与当前值

配置类型：`ApplicationLimits`
唯一默认实例：`DEFAULT_LIMITS`
版本：`limits-v2-viewport-initial-safety`
状态：`initial_safety`；这些值是初始安全上限，不是性能承诺。若代码值变化，必须在同一变更同步本表和边界测试。

<!-- LIMIT_FIELD_INDEX_START -->
| 字段 | 语义 | 当前值 | 当前用途 |
|---|---|---:|---|
| `version` | 稳定 limits 契约版本 | `limits-v2-viewport-initial-safety` | 读取 |
| `status` | 初始安全或基准冻结状态 | `initial_safety` | 读取 |
| `max_input_characters` | 原始输入最大字符数 | 4,096 | normalizer 在删除/展开前检查 |
| `max_tokens` | 最大 token 数 | 1,024 | tokenizer 每次追加前检查 |
| `max_ast_nodes` | 最大 AST 节点数 | 2,048 | 阶段 7 parser 构造前检查 |
| `max_nesting_depth` | 最大词法/AST 嵌套深度 | 64 | tokenizer 检查括号；parser 检查 AST 深度 |
| `max_numeric_digits` | 单个数字最大数字位数 | 128 | tokenizer 数字扫描期间检查 |
| `max_decimal_places` | 最大小数位数 | 64 | tokenizer 数字扫描期间检查 |
| `max_rational_numerator_digits` | 有理数分子最大位数 | 128 | 阶段 7 parser 字面量除法检查 |
| `max_rational_denominator_digits` | 有理数分母最大位数 | 128 | 阶段 7 parser 字面量除法检查 |
| `max_absolute_exponent` | 指数绝对值上限 | 1,000 | 阶段 7 parser 构造前检查 |
| `max_function_arguments` | 单个函数最大参数数 | 8 | 阶段 7 parser 读取下一参数前检查 |
| `max_scene_items` | 场景最大 item 数 | 16 | 后续阶段使用 |
| `max_sample_points_per_item` | 单项最大采样点数 | 20,000 | 后续阶段使用 |
| `max_total_sample_points` | 场景最大总采样点数 | 100,000 | 后续阶段使用 |
| `max_branches_per_item` | 单项最大分支数 | 16 | 后续阶段使用 |
| `max_total_branches` | 场景最大总分支数 | 64 | 后续阶段使用 |
| `max_estimated_memory_bytes` | 预计内存上限 | 268,435,456 bytes | 后续阶段使用 |
| `max_png_bytes` | 输出 PNG 字节上限 | 33,554,432 bytes | 后续阶段使用 |
| `min_image_width` | 图片最小宽度 | 320 | 后续阶段使用 |
| `max_image_width` | 图片最大宽度 | 4,096 | 后续阶段使用 |
| `min_image_height` | 图片最小高度 | 240 | 后续阶段使用 |
| `max_image_height` | 图片最大高度 | 4,096 | 后续阶段使用 |
| `min_dpi` | DPI 最小值 | 72 | 后续阶段使用 |
| `max_dpi` | DPI 最大值 | 300 | 后续阶段使用 |
| `max_log_file_bytes` | 单个日志文件容量 | 5,242,880 bytes | 阶段 5 日志使用 |
| `log_backup_count` | 日志轮转备份数量 | 3 | 阶段 5 日志使用 |
| `max_log_field_text_length` | 日志字段文本最大长度 | 512 | 阶段 5 日志使用 |
| `viewport_probe_points` | 自动视口数值探测的固定 float64 点数 | 1,024 | 阶段 8B 在预算通过后创建一维网格 |
| `max_viewport_probe_bytes` | 单项自动视口探测的独立硬内存预算 | 16 MiB | 阶段 8B 在 `linspace` 前估算并拒绝超限 |
| `min_viewport_span` | 最终 x/y 视口最小跨度 | 1 | 阶段 8B 手动、探测和回退范围共同使用 |
| `max_viewport_span` | 最终 x/y 视口最大跨度 | 1,000,000 | 阶段 8B 手动、探测和回退范围共同使用 |
| `max_viewport_absolute_coordinate` | 最终视口边界绝对坐标上限 | 10,000,000 | 阶段 8B 所有最终边界检查 |
| `default_auto_x_min` | 自动视口未提供 x 时的默认 x 下界 | -10 | 阶段 8B 自动探测输入 |
| `default_auto_x_max` | 自动视口未提供 x 时的默认 x 上界 | 10 | 阶段 8B 自动探测输入 |
| `fallback_auto_x_min` | 自动探测不可靠且未提供 x 时的回退 x 下界 | -10 | 阶段 8B 回退 |
| `fallback_auto_x_max` | 自动探测不可靠且未提供 x 时的回退 x 上界 | 10 | 阶段 8B 回退 |
| `fallback_auto_y_min` | 自动探测不可靠时的回退 y 下界 | -10 | 阶段 8B 回退 |
| `fallback_auto_y_max` | 自动探测不可靠时的回退 y 上界 | 10 | 阶段 8B 回退 |
| `viewport_quantile_low_percent` | 有限 y 样本的稳健下分位百分数 | 5 | 阶段 8B 探测统计 |
| `viewport_quantile_high_percent` | 有限 y 样本的稳健上分位百分数 | 95 | 阶段 8B 探测统计 |
| `viewport_relative_padding_percent` | 稳健 y 范围的相对留白百分数 | 10 | 阶段 8B 探测统计 |
| `viewport_absolute_padding` | 稳健 y 范围的绝对留白 | 1 | 阶段 8B 探测统计 |
| `min_finite_probe_values` | 接受自动探测所需的最少有限 y 值数 | 2 | 阶段 8B 不足时受控回退 |
<!-- LIMIT_FIELD_INDEX_END -->

阶段 6 不复制这些数值到 Python 实现或测试；实现直接读取传入的 `ApplicationLimits`/`DEFAULT_LIMITS`，边界测试从 `DEFAULT_LIMITS` 生成输入。

## 错误码注册表

<!-- ERROR_CODE_REGISTRY_START -->
| 稳定值 | 含义 | 首次用途 |
|---|---|---|
| `invalid_input` | 输入无效；保留阶段 2 已有值与含义，也用于受控空格位置无效 | 既有模型契约 / 阶段 6 |
| `render_failed` | 绘图任务失败；保留阶段 2 已有值与含义 | 既有控制器回退 |
| `invalid_request` | 请求级通用验证失败 | 阶段 5 基础设施 |
| `resource_limit_exceeded` | 通用资源限制被超过 | 阶段 5 基础设施 |
| `internal_error` | 已脱敏的内部错误 | 阶段 5 基础设施 |
| `empty_input` | 原文为空、仅含允许空格或 token tuple 为空 | 阶段 6 normalizer/splitter |
| `input_too_long` | 删除或展开前原始字符数超过集中上限 | 阶段 6 normalizer |
| `unknown_character` | 首个未批准字符或控制字符 | 阶段 6 normalizer/tokenizer |
| `unknown_identifier` | 连续 ASCII 字母形成的完整标识符不在白名单 | 阶段 6 tokenizer |
| `unsupported_relation` | 不等式或其他关系符不在当前范围 | 阶段 6 tokenizer |
| `token_limit_exceeded` | 追加下一个 token 将超过集中上限 | 阶段 6 tokenizer |
| `number_too_long` | 数字总位数或小数位数超过集中上限 | 阶段 6 tokenizer |
| `nesting_too_deep` | 扫描左括号时超过集中嵌套上限 | 阶段 6 tokenizer |
| `delimiter_mismatch` | 左右括号或绝对值竖线不匹配 | 阶段 6 tokenizer |
| `illegal_trailing` | 机械可判定的未完成数字或非法尾部 token | 阶段 6 tokenizer |
| `multiple_equals` | 一个 token tuple 中出现两个或更多等号 | 阶段 6 splitter |
| `equation_left_empty` | 唯一等号左侧没有 token | 阶段 6 splitter |
| `equation_right_empty` | 唯一等号右侧没有 token | 阶段 6 tokenizer/splitter |
| `parser_syntax_error` | typed token 不符合受限表达式语法或未完整消费 | 阶段 7 parser |
| `function_call_required` | 函数名后缺少括号调用 | 阶段 7 parser |
| `function_argument_error` | 函数参数为空、数量错误或超过上限 | 阶段 7 parser/validator |
| `log_requires_base` | 裸 `log(x)` 缺少必需底数 | 阶段 7 parser/validator |
| `invalid_log_base` | log 底数不满足正数字面量且不为 1 的窄契约 | 阶段 7 validator |
| `implicit_multiplication_not_allowed` | 相邻 token 不在隐式乘法白名单 | 阶段 7 parser |
| `nested_absolute_value` | 直接嵌套 BAR 未支持 | 阶段 7 parser |
| `ast_node_limit_exceeded` | parser 构造下一个节点将超过上限 | 阶段 7 parser |
| `ast_depth_limit_exceeded` | parser 构造节点将超过 AST 深度上限 | 阶段 7 parser |
| `rational_literal_too_long` | 数字字面量分子或分母超过对应上限 | 阶段 7 parser |
| `exponent_out_of_range` | 直接有符号整数指数超过绝对值上限 | 阶段 7 parser |
| `unsupported_exponent` | 小数、变量或复合指数不在当前窄契约 | 阶段 7 parser/validator |
| `invalid_ast` | 防御性验证发现非封闭节点、名称或预算品牌 | 阶段 7 validator |
| `explicit_function_y_not_allowed` | 显函数候选表达式包含 y | 阶段 7 classifier/validator |
| `unsupported_equation` | 未形成直接显函数候选的方程形式当前不支持；不携带真实曲线类别判断 | 阶段 7 classifier |
| `invalid_viewport` | 视口请求的边界、顺序、跨度或坐标范围无效 | 阶段 8B resolver |
| `viewport_probe_budget_exceeded` | 自动视口探测的独立预分配预算不足或获批分配失败 | 阶段 8B resolver |
<!-- ERROR_CODE_REGISTRY_END -->

## 阶段 8B 单显函数视口解析契约

阶段 8B 只接受一个 `PlotSceneSpec`，且其中恰有一个经阶段 8A 验证的
`ExplicitFunctionSpec`，再加一个 `ViewportRequest` 与集中式
`ApplicationLimits`。它不接受原始文本、token、AST、SymPy 对象或任意 callable，
也不构建 `RenderPlan`、采样结果、渲染对象或 UI 状态。

手动视口必须提供四个有限边界，满足严格顺序、跨度与坐标上限；成功时原样保留
边界并给出 `ViewportSource.MANUAL`，不创建探测网格也不调用数值执行器。自动视口
只能提供完整的 x 区间或完全不提供 x；未提供时使用 `default_auto_x_*`。自动 y 由
解析器控制，任何 partial x、显式 y 或非法 x 都以 `ErrorInfo` 失败且不回退。

自动探测先读取阶段 8A 的精确向量存活成本，并在分配前以
`max_viewport_probe_bytes` 计入固定 x 网格、执行器峰值、返回向量、有限掩码、有限值
压缩、分位数工作区和解析器缓冲区。预算或执行器契约失败不会返回视口，更不会回退。
预算通过后才创建固定的一维 `float64` 网格；只使用有限 y 值，以集中式分位数和相对/绝对
留白生成 y 范围。常量以 Python `float` 单独处理，并围绕常量值保证最小 y 跨度。

若预算和执行器契约均成功、但数学探测结果不可靠（例如有限点不足或稳健统计不可用），
返回受控 `ViewportSource.AUTO_FALLBACK` 与如下强类型警告。提供 x 时保留该 x，仅回退 y；
未提供 x 时使用 `fallback_auto_x_*` 与 `fallback_auto_y_*`。正常探测成功使用
`ViewportSource.AUTO_PROBE`。

| 警告代码 | 含义 | 首次使用 |
|---|---|---|
| `auto_viewport_fallback` | 数学探测不可靠，使用集中式安全回退范围 | 阶段 8B resolver |

## 阶段 8C-1 单项 RenderPlan、预算与 approval receipt

阶段 8C-1 的唯一入口为 `build_single_explicit_render_plan` 或等价的
`RenderPlanBuilder.build`。它只接收一个 `PlotSceneSpec`、一个已经完整的
`ResolvedViewport`、输出标量 `image_width`、`image_height`、`dpi`、`show_grid`、
`show_legend`、当前 `ApplicationLimits` 和 `ExplicitSamplingPolicy`；不再接收原始
文本、token、普通 AST、SymPy 表达式、callable 或阶段 8B probe x/y 数组。

Builder 只接受恰有一个精确 `ExplicitFunctionSpec` 的 Scene，并重新验证 Spec 的
validated-expression/active-limits 契约。`ResolvedViewport` 是最终范围值对象，而非
可信能力对象：Builder 不追溯其 resolver 来源，也不运行 probe；它按**当前** limits
重新检查精确类型、四个有限非 bool 边界、顺序、x/y span、坐标绝对值、`AspectRequest`
和 `ViewportSource`。`source` 可保留给诊断，但不影响预算是否获批。

### ExplicitSamplingPolicy

默认 `DEFAULT_EXPLICIT_SAMPLING_POLICY` 的版本为
`explicit-sampling-policy-v1`。它是 frozen/slots 的纯标量模型，没有 NumPy 数组，也
不覆盖 `ApplicationLimits` 的硬上限。

| 字段 | 默认值 | 用途 |
|---|---:|---|
| `points_per_horizontal_pixel` | 2 | 将输出宽度确定性映射为正式点数 |
| `min_sample_points` | 320 | 最小正式点数 |
| `preferred_batch_points` | 4,096 | 内存允许时的首选 batch |
| `preferred_max_segment_count` | 16 | 再与 branches 硬上限取最小值 |
| `cancellation_check_interval` | 256 | 后续 sampler 的取消/诊断检查间隔契约 |
| `finite_jump_threshold` | 64 | 后续有限跳变诊断阈值契约 |
| `dense_oscillation_proxy_threshold` | 32 | 后续密集振荡代理阈值契约 |

正式点数为 `max(min_sample_points, image_width * points_per_horizontal_pixel)`；超出
`max_sample_points_per_item` 或 `max_total_sample_points` 时，返回可恢复的
`resource_limit_exceeded`，而不是直接把每个请求提升到最大点数。

### 正式内存预算与批准门禁

Builder 在任何采样数组、`np.linspace` 或执行器调用之前，只用 Python 标量计算：

```text
N*8                         final x
N*8                         final y
N*1                         finite/validity mask
S*2*8                       segment index ranges
max(L-1, 0)*B*8             executor extra batch peak
W*H*4                       one RGBA canvas
max_png_bytes               PNG output reserve
```

其中 `N` 为正式点数、`B` 为 batch、`L` 为 stage 8A
`NumericExecutionCost.max_live_float64_vectors`、`S` 为已受硬 branches 上限约束的
segment 数。完整 final x 已单独计入，batch x 是它的 slice view，因此执行器额外项使用
`L-1`，不重复计数。Builder 先计算与 batch 无关的固定项，再从剩余内存反推不大于首选值
的 batch；最小 batch 仍无法容纳时返回可恢复的 `resource_limit_exceeded`。这只是项目
控制的大缓冲上界，不是对 Python、NumPy 或未来 Matplotlib RSS 的精确预测。

普通 `RenderPlan(...)` 只能构造未审批快照。Builder 在所有 Scene、viewport、输出、点数、
branches 和预算检查成功后才由 model-owned factory 签发 typed approval receipt。未来
sampler 必须调用 `validate_approved_render_plan`；该校验会重查 receipt seal 与计划的版本、
输出和预算关键字段，拒绝普通构造、旧计划或字段篡改。该模式是 Python 层的协议门禁，
不声称密码学私有性。

获批计划固定：`render-plan-v1-budgeted-explicit`、本次实际重验证所用
`ApplicationLimits.version`、sampling policy version、
`numeric-executor-v1-postorder-float64`，以及 Spec 的 active limits contract。计划中的
`limits_version` 仅表示 Builder 使用该版本重新验证和预算；不声称上游 viewport resolver
使用过同一版本。

阶段 8C-1 不创建正式 x/y 数组，不实现 sampler、分段、振荡诊断执行、Figure/Canvas、PNG
renderer、Qt、Matplotlib、Actor 或 UI。

所有阶段 6、7 用户错误均返回中文 `user_message`、原始输入 `SourceSpan` 和 `recoverable=True`。`technical_message` 只包含脱敏类别、计数或 token kind，不包含完整原始公式、堆栈、本地路径，也不暴露内部规范化偏移。

## 阶段 6 自动测试矩阵

| 类别 | 已覆盖样例/边界 | 自动测试 |
|---|---|---|
| 规范化正向 | `x^2`、`x**2`、`x²`、`x³`、`|x|`、全角数字/括号/等号、`− × · ÷`、外围/运算符空格 | `tests/engine/test_normalizer.py` |
| SourceMap 精确值 | `" x² " → "x^2"`、`"x**2" → "x^2"`、空映射边界、首末/零长/越界、全角替换与删除空格 | `tests/engine/test_source_map.py` |
| tokenizer 正向 | `2x`、`2(x+1)`、`(x+1)(x-1)`、所有批准函数、`ln`、`lg`、`log(x,10)`、`pi`、`E` | `tests/engine/test_tokenizer.py` |
| splitter 正向 | `x^2`、`y=x^2`、`x=y`、`y+1=x+2`；左右顺序与原始区间保留 | `tests/engine/test_equation_splitter.py` |
| 反向输入 | 空输入、仅空格、`=x`、`x=`、`x=y=1`、不等式、换行/分号、未知字符/标识符、合法前缀加非法尾部、`x+`、`x^`、`sin(`、括号/竖线不匹配 | 各模块测试及 `test_input_frontend_robustness.py` |
| 集中资源边界 | 字符、token、数字位数、小数位数、嵌套深度各自“恰好达到”与“超过” | `test_normalizer.py`、`test_tokenizer.py`；全部读取 `DEFAULT_LIMITS` |
| 固定种子健壮性 | ASCII、全角、Unicode 运算符、控制符、括号、竖线、多等号、长数字、未知标识符和标点的 500+ 混合输入 | `tests/engine/test_input_frontend_robustness.py` |
| 静态架构 | Engine 无 PySide6/SymPy/NumPy/Matplotlib，无执行式调用；公开数据冻结、slots、字段有类型 | `tests/engine/test_input_frontend_robustness.py` |

## 阶段 7 自动测试矩阵

| 类别 | 覆盖内容 | 自动测试 |
|---|---|---|
| AST/parser 正向 | 节点类型、深层不可变/slots、封闭名称与子节点、span、优先级、左/右结合、一元负号、负指数、无常量折叠 | `tests/engine/test_parser.py` |
| 函数与 BAR | 全部白名单函数、arity、裸 log、对数底数、并列 BAR、嵌套函数 abs、直接嵌套 BAR 拒绝 | parser/validator 测试 |
| 隐式乘法 | 三个允许邻接及 `x2`、`x(...)`、`)x`、`2sin`、`2pi` 拒绝 | parser/validator 测试 |
| 分类与语义 | expression、`y=rhs`、`lhs=y`、常量、自由变量，以及九类非直接方程统一中性阶段拒绝 | classifier/validator 测试 |
| SourceMap/EOF | Unicode 上标、全角字符、`**`、空格、隐式乘法、BAR、原文 EOF 零宽 span | parser/validator 测试 |
| 限制边界 | AST 节点、AST 深度、字面量指数、函数参数；六种无符号/单层有符号有理形式分别以不同 numerator/denominator 配置覆盖 4/3/2 | `tests/engine/test_parser.py`；读取 `DEFAULT_LIMITS` 或其受控替换 |
| 保证无效 mutation | 固定种子 `20260721`，生成 90 条、31 个唯一字符串，覆盖删除闭符号、多余分隔符、非法尾部、未知名称、非法邻接和超深嵌套 | `tests/engine/test_stage7_safety.py` |
| 有界 mixed fuzz | 固定种子 `20260722`，生成 600 条、556 个唯一字符串；结果稳定且只为 `ValidatedExplicitExpression | ErrorInfo` | `tests/engine/test_stage7_safety.py` |
| 静态安全 | 禁止动态执行、`ast.parse`/`ast.literal_eval` 和通用数学 parser API；Models 不导入 Engine；validated result 使用唯一正式工厂调用点；生产入口顺序 | `tests/engine/test_stage7_safety.py` |

随机健壮性测试只接受成功的 `ValidatedExplicitExpression` 或结构化 `ErrorInfo`。它使用 Python 标准库固定种子，不引入 Hypothesis 或其他依赖；这些生成条目包含重复值，只是有界的最小健壮性与确定性证据，不是同等数量的独立案例或形式化安全证明。当前测试没有“完全不产生日志”的断言，因此本文不作该声明。

## 阶段 8A 单项 Spec 与 validated receipt 契约

`ValidatedExplicitExpression` 继续只能由阶段 7 正式入口创建，并在结果内保留 model-owned、不可公开签发的 typed receipt。阶段 8A 使用前重新核对：结果精确类型、receipt seal、结果/receipt/active limits 三方版本、完整受限 AST、free variables、root spans、source form 和固定 `EXPLICIT_FUNCTION` 类型。缺少 receipt 的旧对象、伪造 receipt、普通 `RestrictedExpression`、字符串或不兼容 limits version 统一作为内部契约错误拒绝。

`ExplicitFunctionSpec` 只保存：

```text
item_id: str
validated_expression: ValidatedExplicitExpression
```

其 `expression`、normalized/source 元数据、free variables、limits version 和固定 plot kind 都是 validated result 的只读属性投影，不存在第二份可失配数学 payload。单项 Scene 仍是通用 `PlotSceneSpec(items=(spec,))`。

## 阶段 8A 安全 NumPy 数值执行契约

生产入口 `execute_explicit_function` 只接收 `ExplicitFunctionSpec` 和调用者提供的 x batch。x 必须是精确 `numpy.ndarray`、dtype 严格为 `float64`、形状严格为一维且全部元素有限；不接收 list、float32、object、complex、二维数组、NaN 或无穷输入。执行不修改输入，不缓存 Spec、程序、输入或输出。

执行器把当前六种受限 AST 节点编译为局部后序 typed 指令 tuple，只用显式分支实现以下封闭联合：

```text
NumberNode
SymbolNode(x)
ConstantNode(pi, E)
UnaryOpNode(+/-)
BinaryOpNode(+ - * / power)
FunctionCallNode(sin cos tan sqrt abs exp ln lg log)
```

不存在任意模块、函数或名称注入；未知节点、运算符、常量、函数、非 x symbol、栈契约或 validated/limits mismatch 都返回不可恢复的结构化 `internal_error`。正式 Engine 继续禁止调用 `eval`、`exec`、`compile`、`ast.parse`、`sympify`、`parse_expr`、`parse_latex` 或 `lambdify`。

所有数值运算在局部 `numpy.errstate(divide="ignore", invalid="ignore", over="ignore", under="ignore")` 内执行。锁定 NumPy 2.5.1 下：除零保留带符号无穷；sqrt 和对数定义域外保留 NaN/负无穷；exp 溢出保留正无穷；负底数整数幂保持实数；下溢的有限零保留；`RuntimeWarning` 不逃逸。执行器不把这些数值域结果误报为结构错误。

常量表达式最终规范为 Python `float`。含 x 的结果必须严格为 `(batch_length,)` float64 数组；Python scalar、NumPy float64 scalar和零维 float64 仅在标量指令边界接受。错误维度、错误长度、object、complex 或其他 dtype 统一结构化拒绝。向量结果由执行器独立持有并设为只读；`x` 恒等表达式通过最终所有权复制避免输出别名修改输入。

`estimate_numeric_execution_cost` 在不执行表达式的情况下模拟同一后序栈策略，并返回：

```text
NumericExecutionCost.max_live_float64_vectors
```

计数包含整个调用期间存活的调用者 x 向量、栈中仍存活的执行器临时 float64 向量，以及 operand 尚存活时正在分配的输出向量。`log(x,b)` 按实际 `log(value)` 临时向量与随后 divide 输出分别计数；根结果仍别名 x 时计入最终所有权复制。该值来自具体执行/释放顺序，不使用固定魔法倍数，也不估算 NumPy 内部非 float64 workspace。

阶段 8A 不生成采样网格，不调用 `np.linspace`，不广播常量到 batch，不解析视口，不处理渐近线/分段/密集振荡，不构造 RenderPlan、sampler、renderer、Actor 或 UI，也不实现多项 Scene。

## 阶段 8A 自动测试矩阵

| 类别 | 覆盖内容 | 自动测试 |
|---|---|---|
| 单项 Spec | request item_id、AUTO/显函数 kind、validated AST identity、单项 Scene tuple、无 display_order 副本 | `tests/engine/test_spec_builder.py` |
| Spec 拒绝 | 空白/非字符串 item_id、kind mismatch、普通 AST/字符串注入、旧/伪造 receipt、不兼容 limits version | `tests/engine/test_spec_builder.py` |
| 数值节点 | 常量、x、一元正负、五种二元运算、全部九个函数名 | `tests/engine/test_numeric_executor.py` |
| 指数契约 | 整数、带符号整数、整数字面量幂链、`2^x`；`x^x`/复合指数仍由阶段 7 拒绝 | `tests/engine/test_numeric_executor.py` |
| 输入/输出 | 严格有限一维 float64、Python/零维标量、严格一维结果、错误形状/长度/dtype、输入未修改、结果独立所有权 | `tests/engine/test_numeric_executor.py` |
| 浮点行为 | 除零、sqrt/ln/lg/log 域外、exp 溢出、负底数整数幂、下溢、无 RuntimeWarning | `tests/engine/test_numeric_executor.py` |
| 成本与安全 | 精确策略峰值、无缓存、未知 typed 节点/运算符/函数、public contract tamper | `tests/engine/test_numeric_executor.py` |

## 版本与变更规则

1. 新增或改变公开语法、错误码或 limits 字段时，同一变更必须更新对应实现、行为测试和本文件。
2. 已发布错误码不得改变字符串值或含义。
3. 初始安全上限只有在冻结测量协议并取得基准证据后，才可改标为基准冻结；它们不是产品性能承诺。
4. 不在 UI、模型、测试或其他文档建立第二套独立阈值或错误码表。
5. 阶段 7 typed 验证成功只证明当前受限显函数语法安全形成；不表示已经具备数值函数、视口、采样、渲染、Scene Spec 或阶段 8 能力。
