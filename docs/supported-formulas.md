# 支持公式与横切契约

文档版本：stage-15b-unified-executor-v1
状态：阶段 13A 至 13E、Stage 14B 至 14E 和 Stage 15A 已完成；Stage 15B 候选实施已把 `SceneRenderExecutor` 统一为 M1/M1.5 单项 manual production executor，六种 exact 类型统一进入 `render_sampled_curve_png`。既有 Actor/Controller/UI 文件未在 15B 修改，M1.5 真实组合证明属于 15C，GUI 闭环属于 15D；Stage 15、P0-07、正式性能、教材证据、checkpoint 和核心 MVP 均未完成。
单一事实来源职责：本文件登记输入语法、转换表、token 白名单、limits 字段与当前值、稳定错误码及验收矩阵。限制数值的唯一可执行来源仍是 `math_drawing_assistant/config/limits.py`。

## 当前实现边界与正式生产调用图

当前仓库保留两个正式、职责不同的单项分析入口。

既有 M1 专用入口保持不变：

```text
input_text
→ analyze_explicit_function
→ ValidatedExplicitExpression | ErrorInfo
```

它仍只处理既有 M1 显函数语义；其正常返回是尚未注入 `item_id` 的 `ValidatedExplicitExpression`，不是可直接渲染的 `PlotItemSpec`。

阶段 13 的正式 request-level 入口是 `analyze_plot_item`：


```text
PlotItemRequest
→ analyze_plot_item
→ 一次 normalize / tokenize / split / parse
→ classify_plot_route
  → ExplicitFunctionCandidate
    → 既有显函数 validation
    → ValidatedExplicitExpression
    → ExplicitFunctionSpec
  → EquationCandidate
    → sealed equation validation
    → bounded exact polynomial canonicalization
    → exact geometry classification
    → LineSpec | CircleSpec | EllipseSpec | HyperbolaSpec | ParabolaSpec
→ PlotItemSpec | ErrorInfo
```

`analyze_plot_item` 是阶段 13 的正式单项分析边界：它不生成 `PlotSceneSpec`，不计算 viewport，也不执行 sampling 或 render。equation Spec 的 viewport、数值规划与参数化采样原型已由 Stage 14 完成；Stage 15A 已把六种 typed sampled output 经统一 renderer 入口渲染为 Agg/PNG，Stage 15B 再把该入口接入唯一 `SceneRenderExecutor`。Actor/Controller/UI 的真实组合与 GUI 闭环仍属于 15C/15D。阶段 6/7 的规范化、词法化、SourceMap、AST 和既有显函数 validation 语义不变，也不导入 SymPy 或执行数值求值、常量折叠、化简、展开、移项或求解。

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
版本：`limits-v3-equation-normalization-initial-safety`
状态：`initial_safety`；这些值是初始安全上限，不是性能承诺。若代码值变化，必须在同一变更同步本表和边界测试。

三个 equation exact arithmetic limits 同样属于 `INITIAL_SAFETY`，不是性能或教材承诺。它们现在由 bounded exact rational、polynomial canonicalization 和 geometry classifier 消费；`analyze_plot_item` 会将对应 resource failure 映射为 `resource_limit_exceeded`。这些限制不表示阶段 14 sampling/render 已完成，也不改变既有 M1 receipt 的结构、签发边界、校验逻辑或安全语义。

<!-- LIMIT_FIELD_INDEX_START -->
| 字段 | 语义 | 当前值 | 当前用途 |
|---|---|---:|---|
| `version` | 稳定 limits 契约版本 | `limits-v3-equation-normalization-initial-safety` | 读取；阶段 13 已完成，不表示阶段 14/15 已完成 |
| `status` | 初始安全或基准冻结状态 | `initial_safety` | 读取 |
| `max_input_characters` | 原始输入最大字符数 | 4,096 | normalizer 在删除/展开前检查 |
| `max_tokens` | 最大 token 数 | 1,024 | tokenizer 每次追加前检查 |
| `max_ast_nodes` | 最大 AST 节点数 | 2,048 | 阶段 7 parser 构造前检查 |
| `max_nesting_depth` | 最大词法/AST 嵌套深度 | 64 | tokenizer 检查括号；parser 检查 AST 深度 |
| `max_numeric_digits` | 单个数字最大数字位数 | 128 | tokenizer 数字扫描期间检查 |
| `max_decimal_places` | 最大小数位数 | 64 | tokenizer 数字扫描期间检查 |
| `max_rational_numerator_digits` | 有理数分子最大位数 | 128 | 阶段 7 parser 字面量除法检查 |
| `max_rational_denominator_digits` | 有理数分母最大位数 | 128 | 阶段 7 parser 字面量除法检查 |
| `max_equation_coefficient_numerator_digits` | 阶段 13 多项式系数及精确几何 Fraction 分子的最大十进制位数 | 128 | bounded exact rational、polynomial canonicalization 与 geometry classifier |
| `max_equation_coefficient_denominator_digits` | 阶段 13 多项式系数及精确几何 Fraction 分母的最大十进制位数 | 128 | bounded exact rational、polynomial canonicalization 与 geometry classifier |
| `max_equation_canonical_coefficient_digits` | denominator clearing、LCM、canonicalization 中间整数及最终 primitive integer coefficient 的最大十进制位数 | 768 | polynomial canonicalization 与 geometry classifier |
| `max_absolute_exponent` | 指数绝对值上限 | 1,000 | 阶段 7 parser 构造前检查 |
| `max_function_arguments` | 单个函数最大参数数 | 8 | 阶段 7 parser 读取下一参数前检查 |
| `max_scene_items` | 场景最大 item 数 | 16 | 阶段 8C-1 Builder 的 Scene 资源审批 |
| `max_sample_points_per_item` | 单项最大采样点数 | 20,000 | 阶段 8C-1 Builder 批准正式点数；8C-2 sampler 消费批准值 |
| `max_total_sample_points` | 场景最大总采样点数 | 100,000 | 阶段 8C-1 Builder 的 Scene 正式点数审批 |
| `max_branches_per_item` | 单项最大分支数 | 16 | 阶段 8C-1 批准 segment capacity；8C-2 sampler 执行容量 |
| `max_total_branches` | 场景最大总分支数 | 64 | 阶段 8C-1 Builder 的 Scene 分支审批 |
| `max_estimated_memory_bytes` | 预计内存上限 | 268,435,456 bytes | 阶段 8C-1 Builder 的正式内存预算上限 |
| `max_png_bytes` | 输出 PNG 字节上限 | 33,554,432 bytes | 阶段 8C-1 memory budget 的 PNG reserve；实际 PNG 仍属后续 renderer |
| `min_image_width` | 图片最小宽度 | 320 | 阶段 8C-1 Builder 输出验证与正式采样点规划 |
| `max_image_width` | 图片最大宽度 | 4,096 | 阶段 8C-1 Builder 输出验证与正式采样点规划 |
| `min_image_height` | 图片最小高度 | 240 | 阶段 8C-1 Builder 输出验证与 canvas 预算 |
| `max_image_height` | 图片最大高度 | 4,096 | 阶段 8C-1 Builder 输出验证与 canvas 预算 |
| `min_dpi` | DPI 最小值 | 72 | 阶段 8C-1 Builder 输出验证 |
| `max_dpi` | DPI 最大值 | 300 | 阶段 8C-1 Builder 输出验证 |
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
| `unsupported_equation` | M1 非直接显函数的阶段性拒绝；M1.5 的零/常量方程、被冻结的变量零次幂，以及当前未支持的 equation structure 也使用该值 | 阶段 7 classifier / 阶段 13 polynomial normalizer |
| `equation_non_rational_coefficient` | 方程系数不属于 M1.5 精确有理数范围 | 阶段 13B-2 polynomial normalizer / 阶段 13D-3 `analyze_plot_item` |
| `equation_non_polynomial` | 方程包含非多项式结构 | 阶段 13B-2 polynomial normalizer / 阶段 13D-3 `analyze_plot_item` |
| `equation_variable_denominator` | 变量出现在分母中 | 阶段 13B-2 polynomial normalizer / 阶段 13D-3 `analyze_plot_item` |
| `equation_zero_denominator` | 纯数值分母精确为零 | 阶段 13B-2 polynomial normalizer / 阶段 13D-3 `analyze_plot_item` |
| `equation_degree_exceeded` | 变量结构形成总次数超过 2 的项 | 阶段 13B-2 polynomial normalizer / 阶段 13D-3 `analyze_plot_item` |
| `rotated_conic_not_supported` | 最终精确 xy 系数非零 | 阶段 13C geometry classifier / 阶段 13D-3 `analyze_plot_item` |
| `degenerate_conic` | 二次方程表示点、一条或两条直线等退化集合 | 阶段 13C geometry classifier / 阶段 13D-3 `analyze_plot_item` |
| `conic_has_no_real_points` | 二次方程不存在可绘制的实数图形 | 阶段 13C geometry classifier / 阶段 13D-3 `analyze_plot_item` |
| `invalid_viewport` | 视口请求的边界、顺序、跨度或坐标范围无效 | 阶段 8B resolver |
| `viewport_probe_budget_exceeded` | 自动视口探测的独立预分配预算不足或获批分配失败 | 阶段 8B resolver |
| `no_visible_curve` | 采样成功但当前视口没有可绘制曲线；内部 typed reason 区分无有限点、无可绘制段和视口外 | 阶段 8C-2 sampler |
| `numeric_range_unsupported` | 参数化数值范围超出当前可证明支持的有限精度范围 | Stage 14B-2 直线、Stage 14C 圆/椭圆、Stage 14D-1 双曲线和 Stage 14D-2 抛物线的自动视口、规划与残差门禁 |
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
(N*8)+(N*8)                 Line/Artist drawing data
N*1                         finite/validity mask
S*2*8                       segment index ranges
max(L-1, 0)*B*8             executor extra batch peak
W*H*4                       one RGBA canvas
max_png_bytes               BytesIO PNG buffer reserve
max_png_bytes               final immutable PNG bytes copy
```

其中 `N` 为正式点数、`B` 为 batch、`L` 为 stage 8A
`NumericExecutionCost.max_live_float64_vectors`、`S` 为已受硬 branches 上限约束的
segment 数。完整 final x 已单独计入，batch x 是它的 slice view，因此执行器额外项使用
`L-1`，不重复计数。Builder 先计算与 batch 无关的固定项，再从剩余内存反推不大于首选值
的 batch；最小 batch 仍无法容纳时返回可恢复的 `resource_limit_exceeded`。
`artist_data_bytes = final_x_bytes + final_y_bytes`，覆盖 Matplotlib Line/Artist 在 PNG
编码完成前可能继续持有的一份绘图数据；`png_copy_bytes = max_png_bytes`，覆盖从
`BytesIO` 形成最终不可变 `bytes` 时 PNG 缓冲与最终副本可能同时存在。当前预算覆盖项目
可明确控制的正式数组、Artist 数据、RGBA canvas、`BytesIO` PNG reserve 和最终 PNG
bytes copy；Matplotlib/Pillow 内部不可观测的临时分配仍属于库实现风险，不在此上界承诺内。

普通 `RenderPlan(...)` 只能构造未审批快照。Builder 在所有 Scene、viewport、输出、点数、
branches 和预算检查成功后才由 model-owned factory 签发 typed approval receipt。未来
sampler 必须调用 `validate_approved_render_plan`。receipt 不保存可与计划同步变化的 Scene、
Spec、viewport、item plan 或 memory budget 对象引用，而在签发时递归形成独立语义值快照：
Scene item 数量/顺序/精确类型/item_id、validated expression 的受限 AST 节点类型、运算、
字面量、children、source spans、source form、free variables 和 limits contract，viewport 四边界、
aspect/source，输出尺寸、dpi、grid/legend，全部版本，item plan 全字段及每个 memory budget
组成字段。验证时从当前计划重新形成同一 typed/value snapshot 与签发值比较，再复验
validated-expression 私有 seal 等嵌套契约；因此对 frozen nested dataclass 使用
`object.__setattr__` 的原位篡改也会被直接拒绝，失败不会重签 receipt。该模式仍只是 Python
层 capability/integrity 门禁，不声称密码学安全。

获批计划固定：`render-plan-v1-budgeted-explicit`、本次实际重验证所用
`ApplicationLimits.version`、sampling policy version、
`numeric-executor-v1-postorder-float64`，以及 Spec 的 active limits contract。计划中的
`limits_version` 仅表示 Builder 使用该版本重新验证和预算；不声称上游 viewport resolver
使用过同一版本。

阶段 8C-1 不创建正式 x/y 数组，不实现 sampler、分段、振荡诊断执行、Figure/Canvas、PNG
renderer、Qt、Matplotlib、Actor 或 UI。

## 阶段 8C-2 explicit sampler、分段与采样诊断

唯一入口为：

```text
sample_explicit_function(
    approved RenderPlan,
    *,
    cancellation_probe: CancellationProbe | None,
) -> SampledExplicitFunction | SamplingCancelled | ErrorInfo
```

入口不再接收 Spec、ResolvedViewport、采样点数、batch、x/y 边界、AST、表达式对象、
函数对象、原始文本或阶段 8B probe 数据。第一步固定调用
`validate_approved_render_plan()`；随后只消费 receipt 已绑定的 Scene、viewport、item plan、
输出标量、版本和完整 memory budget snapshot；正式点数、batch、segment capacity 与 executor
liveness 直接读取 approved item plan。sampler 仍核对 active limits version、sampling policy
version、executor contract version、单项精确 `ExplicitFunctionSpec` 及 Spec/viewport/item plan/
memory budget 的基础 typed contract；这些是活动契约与运行时阈值检查，不是预算重算。sampler
不按 image width/policy 重算点数或 segment capacity，不调用 cost estimator 或 Builder，不重推
executor liveness、内存分解或 limits 预算总额，也不重新构造 RenderPlan 或签发第二种 receipt。
无效或篡改计划由 approval 验证在 `np.linspace`、正式 y、validity mask 和 executor 前拒绝。

### typed outcome 与数组所有权

成功类型 `SampledExplicitFunction` 至少包含：

```text
item_id
x / y
segment_ranges
finite_sample_count / nonfinite_sample_count
isolated_finite_count / discontinuity_break_count
visible_segment_count
tuple[SamplingWarning, ...]
SamplingDiagnostics
internal exact-approved-plan snapshot contract
```

`SamplingCancelled` 是独立结果，不是 ErrorInfo、warning 或部分成功。成功返回前固定保证：

```text
x: float64, shape (N,), OWNDATA=True, WRITEABLE=False
y: float64, shape (N,), OWNDATA=True, WRITEABLE=False
segment_ranges: int64, shape (S,2), OWNDATA=True, WRITEABLE=False
```

普通 `SampledExplicitFunction(...)` 构造仍可用于模型测试，但其 internal plan contract
固定为空，也不公开接受调用者传入 snapshot/fingerprint。正式 sampler 只有在入口
`validate_approved_render_plan()` 成功并完成全部采样检查后，才通过 model-owned
`_snapshot_approved_render_plan()` 保存与 approval receipt 唯一构造逻辑同源的完整 typed
semantic snapshot。阶段 9B 可通过受控私有 helper 比较 sampled outcome 保存值与当前 approved
plan 的重新快照，不需要读取 receipt 字段或 seal。viewport、Scene AST/metadata、全部版本、
item plan 和完整 memory budget 的任一语义差异都会使比较失败；`item_id`、样本数或数组 shape
相同不能替代该契约。

NumPy 2.5.1 的 `linspace` 当前返回覆盖完整内部 owner 的 view；sampler 验证 shape、dtype、
stride 和首地址一致后直接接管该任务私有 owner，不建立第二份完整 x。若未来 NumPy 行为不再
能证明这一点，返回内部契约错误，不用未预算的完整复制补救。y 是独立正式缓冲；每批只把 x
的 slice view 交给阶段 8A executor。正式 x owner 在首次跨组件暴露前即设为只读，因此每个
batch view 也是 `WRITEABLE=False`；executor 即使保留 view，也不能在采样期间或成功返回后反向
修改正式 x。sampler 立刻把 scalar/vector 结果写入 y 对应 slice，并释放 batch 输出引用。
executor typed ErrorInfo 原样返回，sampler 不修复 dtype、shape、长度或所有权。

### segment 与可见性

任一端为 NaN、`+inf` 或 `-inf` 时相邻 pair 不连接。连续有限点使用归一化值：

```text
u = (y - y_min) / (y_max - y_min)
```

有限 pair 仅在以下条件全部成立时断开：

1. 两端分别严格位于 y 视口下方和上方；
2. `abs(Δu) > finite_jump_threshold`；默认批准值为 64；
3. 半径为 `max(4, floor(sqrt(finite_jump_threshold)))`；默认半径为 8；
4. 候选 pair 自身不进入局部基准；左侧只取 `i-radius ... i-1`，右侧只取
   `i+1 ... i+radius`；每个局部 pair 两端都必须有限，且不得跨非有限边界；
5. 左右必须**各自完整取得 radius 个**有限归一化差分；任一侧不足时不按本启发式断线；
6. 左右分别计算 `abs(Δu)` 中位数，并分别与 `1 / image_height` 取较大值；再用两侧基准中
   较大的一个作为保守局部基准；
7. 候选 `abs(Δu)` 大于该基准的 `sqrt(finite_jump_threshold)` 倍；默认相对倍数为 8。

这同时保留 absolute jump、局部 outlier 和至少一垂直像素的基准下限。单个很大值不触发
断线；靠近数组/segment 边缘而缺少任一侧完整证据的有限 pair 也不断开。非有限点仍无条件
断线。与附近斜率一致的陡峭线性、`x^3` 和 `exp(x)` 不断开；该启发式不声称识别任意函数的
全部不连续点。segment 使用共享 x/y 的
`[start, stop)` int64 ranges，每段至少两个点、有序且不重叠。孤立有限点不构成 segment。
segment 数超过 plan 批准容量时返回 `resource_limit_exceeded`，不截断或合并。

segment 可见，当且仅当至少有一个点位于闭区间 `[y_min,y_max]`，或一个未断开的有限 pair
穿过任一 y 视口边界。统一可恢复错误 `no_visible_curve` 的内部 typed reason 为：

| typed reason | 含义 |
|---|---|
| `NO_FINITE_SAMPLES` | 没有有限采样点 |
| `NO_DRAWABLE_SEGMENT` | 有限点存在，但没有至少两点的可绘制 segment |
| `OUTSIDE_VIEWPORT` | 有 segment，但没有点或连续 pair 与当前 y 视口相交 |

### sampling warning 与密集振荡代理

warning 只含稳定 code 和匹配的 typed metrics，不含自由文本周期声明：

| warning code | typed metrics | 语义 |
|---|---|---|
| `partial_domain_omitted` | `finite_sample_count`、`nonfinite_sample_count` | 部分定义域有可绘制结果，非有限部分已省略 |
| `dense_oscillation_suspected` | `significant_direction_change_count`、`valid_adjacent_pair_count`、`samples_per_monotone_run` | 受预算样本可能不足以表达密集振荡 |
| `viewport_clipped` | exact `ViewportClippedMetrics(clipped_segment_count)` | Stage 14B-2 直线固定报告 1；Stage 14C 部分可见圆/椭圆报告实际可见弧数，完整闭合曲线不报告 |
| `sampling_precision_limited` | exact `SamplingPrecisionLimitedMetrics(limited_segment_count)` | Stage 14B-2 直线或 Stage 14C 圆/椭圆残差超过目标阈值但未超过 hard threshold 时报告受限 segment 数 |

密集振荡代理在每个 segment 内读取一阶差分；绝对变化小于一个 y 输出像素
`(y_max-y_min)/image_height` 时忽略。统计显著差分方向反转，`valid_adjacent_pair_count` 为
segment 内全部连续有限 pair 数；`samples_per_monotone_run` 为 segment 样本总数除以
`direction_changes + 有显著方向的 segment 数`。若没有显著方向，则退化为 segment 样本总数。

默认批准 `dense_oscillation_proxy_threshold=32`，冻结判定派生为：

```text
minimum_direction_changes = max(1, threshold // 2) = 16
maximum_samples_per_monotone_run = threshold * 2 = 64
```

两项同时满足才警告。冻结诊断使用 x=`[-10,10]`、y viewport=`[-2,2]`、
image_width=800、image_height=600、正式 N=1600。冻结诊断指标同时依赖 x/y viewport、
image_width、image_height 和正式采样点数 N：

| 公式 | significant direction changes | samples/monotone run | 期望 |
|---|---:|---:|---|
| `sin(x)` | 6 | 228.571 | 不警告 |
| `x^2` | 1 | 800.000 | 不警告 |
| `exp(x)` | 0 | 1600.000 | 不警告 |
| `sin(1000*x)` | 30 | 51.613 | `dense_oscillation_suspected` |
| `2+sin(1000*x)` | 30 | 51.613 | `dense_oscillation_suspected` |

这些值只描述该冻结采样序列，不表示函数的精确周期数。

### cancellation、异常与禁止依赖

`CancellationProbe` 只定义 `is_cancelled() -> bool`，不导入 Qt。固定检查点为 approval 成功后且
首次分配前、每批 executor 前、executor 返回后、分段/诊断每处理
`cancellation_check_interval` 个点，以及冻结返回前。取消后不调用后续 batch，不返回半成品。

已批准分配仍可能失败；正式 x、正式 y、validity mask、segment ranges 及其他 sampler 控制的
实际 NumPy/局部结构分配发生 `MemoryError`（包括适用的 NumPy 内存异常子类）时，统一转为
脱敏、可恢复 `resource_limit_exceeded`，不泄露 allocator 文本、公式、路径、repr 或堆栈，
不继续后续阶段，也不返回部分数组。approval 语义快照的小型结构构造发生 MemoryError 时同样
不会从 sampler 逸出。其他 sampler/executor/cancellation 程序员契约错误使用不可恢复
`internal_error`。本模块不包含 Qt、Matplotlib、Figure/Canvas/PNG、SymPy、lambdify、原始文本
或外部函数对象路径，也不实现 midpoint 探测、第二套 executor 调度、renderer、Actor 或阶段 9B。

阶段 8C-2 自动测试位于 `tests/engine/test_samplers.py`；覆盖未批准/篡改 plan 的分配前拒绝、
正式 batch、标量、部分/空定义域、半开 segment、segment capacity、可见性、`1/x`、`tan(x)`、
连续陡峭与边缘 `exp(x)` 反例、6000 点真实短尾 `[4096,1904]`、所有权、executor 返回后和
诊断循环内取消、各正式分配失败、warning 正反例及禁止依赖。

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
6. 阶段 12 的 M1 checkpoint 只覆盖本文件已声明的单显函数语法，性能证据见 [`m1-performance-v1`](benchmarks/m1-performance-v1.md) 及其[正式结果摘要](benchmarks/m1-performance-v1-results.md)；八公式矩阵不扩大支持公式范围。
7. Clipboard 实现不改变本文件的语法、白名单、错误码或 limits 契约。性能结论仅适用于 Windows 11 开发参考机，不外推为课堂设备结论；阶段 12 收口本身未进入阶段 13，后续入口范围见下节。

## M1.5 阶段 13 已实现范围

<!-- STAGE_13_STATUS_START -->
阶段 13A 至 13E 已完成。`analyze_plot_item` 是 M1.5 正式的单项 request-level 分析入口；既有 `analyze_explicit_function`、`classify_plot` 和 `ValidatedExplicitExpression` 保持兼容。阶段 13 本身不生成 `PlotSceneSpec`；Stage 14 已在后续完成 typed spec → `PlotSceneSpec` → viewport/Builder/receipt/sampling 原型；Stage 15A 完成统一 renderer，Stage 15B 中 SceneRenderExecutor 已统一 M1/M1.5 单项 manual production 链。既有 Actor、Controller 或 UI 文件未在 15B 修改，真实组合证明和 GUI 闭环仍分别属于 15C/15D。Stage 15 仍未完成，核心 MVP 也未因阶段 13/14/15A/15B 候选实施而完成。
<!-- STAGE_13_STATUS_END -->

当前实现接受仅含有理系数、总次数为 1 或 2 的方程，并以 bounded exact arithmetic 归一化为 primitive integer coefficients。它通过 typed `PlotKind` 路由交付下列非退化 Spec：一般直线 `LineSpec`，以及轴向平行的 `CircleSpec`、`EllipseSpec`、`HyperbolaSpec` 和 `ParabolaSpec`。

当前实现拒绝旋转圆锥曲线、退化圆锥曲线、无实点圆锥曲线、变量分母、非多项式结构、非有理系数、三次及以上结构、零/常量方程、被冻结的变量零次幂，以及超过 exact arithmetic limits 的输入。纯数字幂仍不属于 equation coefficient arithmetic 白名单；tokenizer/parser 白名单没有扩大。

`y=x+y`、`x+y=y` 和 `2*y=x+2*y` 在 `analyze_plot_item` 的 equation route 中可成为 `LineSpec`；直接调用 `analyze_explicit_function` 时，`y=x+y` 和 `x+y=y` 仍返回 `explicit_function_y_not_allowed`。requested kind 不会重新解释 typed route；违法、安全超限与数学错误优先于 requested-kind mismatch。

<!-- STAGE_13_REQUESTED_KIND_MATRIX_START -->
| 输入 | `AUTO` | `EXPLICIT_FUNCTION` | `LINE_EQUATION` | `CONIC_EQUATION` |
|---|---|---|---|---|
| `y=2*x+1` | `ExplicitFunctionSpec` | `ExplicitFunctionSpec` | `invalid_request` | `invalid_request` |
| `x=y` | `ExplicitFunctionSpec` | `ExplicitFunctionSpec` | `invalid_request` | `invalid_request` |
| `x=2` | `LineSpec` | `unsupported_equation` | `LineSpec` | `invalid_request` |
| `x+y=1` | `LineSpec` | `unsupported_equation` | `LineSpec` | `invalid_request` |
| `x^2+y^2=25` | `CircleSpec` | `unsupported_equation` | `invalid_request` | `CircleSpec` |
| `x^2=4*y` | `ParabolaSpec` | `unsupported_equation` | `invalid_request` | `ParabolaSpec` |
| `y=x+y` | `LineSpec` | `explicit_function_y_not_allowed` | `LineSpec` | `invalid_request` |
<!-- STAGE_13_REQUESTED_KIND_MATRIX_END -->

## 阶段 13 变量零次幂与重叠错误裁定

<!-- STAGE_13_X0_ERROR_PRECEDENCE_START -->
| 输入 | 当前结果 |
|---|---|
| `x^0+y=1` | `unsupported_equation`（已实现） |
| `(x+1)^0+y=2` | `unsupported_equation`（已实现） |
| `x^0+y^2=1` | `unsupported_equation`（已实现） |
| `y=x^0` | 保持既有 M1 显函数成功 |
| 无等号 `x^0` | 保持既有 M1 显函数成功 |
| `x^3/(x-1)=0` | `equation_degree_exceeded` |
| `x^2/(x-1)=0` | `equation_variable_denominator` |
| `1/(x^3)=0` | `equation_degree_exceeded` |
<!-- STAGE_13_X0_ERROR_PRECEDENCE_END -->

变量零次幂不新增 `variable_zero_exponent`，exact arithmetic 资源超限不新增 `equation_normalization_limit_exceeded`，仍分别使用 `unsupported_equation` 与 `resource_limit_exceeded`。当多个非法结构重叠时，bounded polynomial traversal 按既有子节点访问顺序立即传播错误；这只决定先报告哪个错误，不改变输入被拒绝的事实。阶段 13E 不修改该 traversal。

## Stage 14B/14C/14D-1/14D-2/14E 公共契约与正式参数化原型

### aspect、viewport 与统一 resolver

`ViewportRequest.aspect_request` 的默认值为 `AspectRequest.DEFAULT`。request enum 的完整成员是 `DEFAULT | AUTO | EQUAL`；成功的 `ResolvedViewport.aspect` 必须是 exact `ResolvedAspect.AUTO | ResolvedAspect.EQUAL`，不得保存任何 `AspectRequest` 成员。

DEFAULT 映射表：

| exact Stage 13 Spec | `ResolvedAspect` |
|---|---|
| `ExplicitFunctionSpec` | `AUTO` |
| `LineSpec` | `AUTO` |
| `CircleSpec` | `EQUAL` |
| `EllipseSpec` | `EQUAL` |
| `HyperbolaSpec` | `EQUAL` |
| `ParabolaSpec` | `EQUAL` |

用户显式 `AspectRequest.AUTO/EQUAL` 覆盖上表。`resolve_single_item_viewport` 是唯一单项 resolver；既有 `resolve_single_explicit_viewport` 保留签名并委托它。manual 模式为六种 exact Spec 校验四边界和 aspect，source 为 `MANUAL`。显函数 auto 完全保持既有 probe/typed warning/fallback 行为。exact `LineSpec` auto 不运行 probe 或 fallback：令直线为 `d*x + e*y + f = 0`，先在 workspace 门禁后 exact 计算最近原点锚点 `(-d*f/(d²+e²), -e*f/(d²+e²))`；未给 x 时用既有默认 x/y 固定跨度围绕锚点并在绝对坐标边界平移、不缩小，给出完整 x 时保持 x 原值并从两端 exact 求 y，再应用现有 absolute/relative padding 与最小跨度；竖直线使用锚点 y 的既有 fallback 固定跨度。成功 source 为 `AUTO_GEOMETRY`。partial x 和任何 explicit y 都返回 `invalid_viewport`；不可表示或越界返回 `numeric_range_unsupported`。

exact `CircleSpec | EllipseSpec` auto 先用有界 exact workspace 投影 center 与半轴平方，以 exact 比较和 `nextafter` 得到不会内缩的 float64 包围盒，再应用集中 absolute/relative padding、最小/最大跨度和绝对坐标限制；临近坐标上限时只平移、不缩小。成功 source 同为 `AUTO_GEOMETRY`，任一显式 bound 返回 `invalid_viewport`，不可完整包含时返回 `numeric_range_unsupported`，且不调用显函数 probe/executor/fallback。

exact `HyperbolaSpec` auto 在投影前先用 `estimate_hyperbola_exact_workspace_bytes` 通过 `max_viewport_probe_bytes` 门禁。令 `a²=semi_transverse_squared`、`b²=semi_conjugate_squared`，有限教学窗口固定为：水平横轴 `x∈[h-sqrt(2*a²), h+sqrt(2*a²)]、y∈[k-sqrt(b²), k+sqrt(b²)]`；垂直横轴交换坐标角色。边界用 exact square enclosure 和 `nextafter` outward 转换，随后复用 `_fit_auto_geometry_axis` 的同一套 absolute/relative padding、min/max span、absolute coordinate 规则，不内缩教学窗口。成功 source 为 `AUTO_GEOMETRY`；任一 explicit x/y bound 返回 `invalid_viewport`；workspace 超限返回 `viewport_probe_budget_exceeded`；不能有限表示或完整容纳返回 `numeric_range_unsupported`。它不调用显函数 probe、numeric executor 或 fallback。

exact `ParabolaSpec` auto 在投影前先用 `estimate_parabola_exact_workspace_bytes` 通过同一 `max_viewport_probe_bytes` 门禁。令顶点为 `(h,k)`、有符号焦参数为 `p`，有限教学窗口固定为 `t∈[-1,1]`：竖轴时 `x∈[h-2|p|,h+2|p|]` 且 y 覆盖 `k,k+p`；横轴时 x 覆盖 `h,h+p` 且 `y∈[k-2|p|,k+2|p|]`。四边先 exact 推导并 outward 转为 float64，再复用 `_fit_auto_geometry_axis`；成功 source 为 `AUTO_GEOMETRY`，DEFAULT aspect 为 `EQUAL`，显式 `AUTO/EQUAL` 优先。任一 explicit x/y bound 返回 `invalid_viewport`；workspace 超限返回 `viewport_probe_budget_exceeded`；不能有限表示或完整容纳返回 `numeric_range_unsupported`。它不调用显函数 probe、numeric executor 或 fallback。未知 exact Spec 返回 `invalid_request`。

### line sampling policy

唯一激活的 frozen scalar policy 为 `line-sampling-policy-v1`：

| 字段 | 精确值 |
|---|---:|
| `sample_count` | 2 |
| `batch_size` | 1 |
| `endpoint_merge_ulps` | 2 |
| `target_residual_ulps` | 4 |
| `maximum_residual_ulps` | 16 |
| `cancellation_check_interval` | 1 |

该 v1 version 不允许替换上述语义。Builder 只为 exact `LineSpec` 写入此 policy version。

### circle/ellipse angular sampling policy 与可见区间

`CircleSpec | EllipseSpec` 唯一激活的 frozen scalar policy 为 `angular-sampling-policy-v1`：

| 字段 | 精确值 |
|---|---:|
| `samples_per_pixel` | 1 |
| `minimum_open_segment_samples` | 2 |
| `minimum_closed_curve_samples` | 64 |
| `preferred_batch_points` | 4096 |
| `angle_merge_ulps` | 8 |
| `viewport_boundary_ulps` | 8 |
| `target_residual_ulps` | 32 |
| `maximum_residual_ulps` | 256 |
| `cancellation_check_interval` | 256 |

圆/椭圆共用 `x=h+a*cos(theta), y=k+b*sin(theta)`。Builder 对矩形四边以 exact `delta²` 与 exact 半轴平方判断 0/1/2 个边界根，将根规范化、按 `ulp(2*pi)` 尺度去重，再对循环相邻开区间做中点 sweep。完整可见时只批准 `[0,2*pi] + CLOSED`，采样时用 `j/N` 且不重复首点；部分弧均为 `OPEN` 并包含批准的两个端点，跨 seam 的首尾弧合成 `stop>2*pi` 的单个展开区间。所有弧按 start 稳定排序、branch 固定为 0、容量固定为 4，不相邻弧始终由独立 range/metadata 隔离。

### hyperbola sampling policy、分支与有限可见区间

`HyperbolaSpec` 唯一激活的 frozen scalar policy 为 `hyperbolic-sampling-policy-v1`：

| 字段 | 精确值 |
|---|---:|
| `samples_per_pixel` | 1 |
| `minimum_open_segment_samples` | 2 |
| `preferred_batch_points` | 4096 |
| `parameter_merge_ulps` | 8 |
| `viewport_boundary_ulps` | 8 |
| `target_residual_ulps` | 32 |
| `maximum_residual_ulps` | 256 |
| `cancellation_check_interval` | 256 |

该 v1 version 不允许替换上述语义。令 `s=-1` 对应 branch 0、`s=+1` 对应 branch 1；水平横轴使用 `x=h+s*a*cosh(t), y=k+b*sinh(t)`，垂直横轴使用 `x=h+b*sinh(t), y=k+s*a*cosh(t)`。因此 branch 0 始终是左支/下支，branch 1 始终是右支/上支，不因 viewport 或参数方向交换。

Builder 先把最终 float64 viewport 四边恢复为 exact `Fraction`，并在任何 `asinh/acosh` 转换之前 exact 判断分支可达性、横轴上下界与 `a²` 的关系、孤立切点以及是否必须拆成两个参数区间；共轭方向给出单调 `asinh` 界，横轴方向给出 `acosh` 单区间或跨 `t=0` 的两个区间，再取交集。孤立切点、空交集和 float64 转换后坍缩均不批准。每个数学分支最多两个 `OPEN` 区间、全项最多四个，固定按 `(branch_id, start)` 稳定排序；区间端点虽标为 OPEN，仍是批准并采样的 viewport 边界点。根转换后最多用 `parameter_merge_ulps` 次 `nextafter` 向区间内部修正，且最终端点必须实际位于闭 viewport 内。

每个区间在 `max(abs(start),abs(stop))` 处取单调导数上界。水平横轴的像素速度为 `hypot(a*sinh(t)*width/x_span, b*cosh(t)*height/y_span)`，垂直横轴交换两项；点数为 `max(2, ceil(samples_per_pixel * maximum_pixel_speed * (stop-start)) + 1)`，随后统一通过每项/全局点数、segment 容量、batch 与总内存门禁。不可见返回 `no_visible_curve`，不能有限安全表示返回 `numeric_range_unsupported`，资源不足返回现有 typed resource error；不建立二维网格或 contour 后备路径。

双曲线每个 float64 点以 primitive integer coefficients 和 `Fraction.from_float` 计算：

```text
R = |A*x^2 + C*y^2 + D*x + E*y + F| /
    (|A|*max(1,|x^2|) + |C|*max(1,|y^2|)
     + |D|*max(1,|x|) + |E|*max(1,|y|) + |F|)
```

`R > 256*epsilon64` 拒绝为 `numeric_range_unsupported`；`32*epsilon64 < R <= 256*epsilon64` 成功但生成 `sampling_precision_limited`；目标阈值以内不生成该 warning。

### parabola sampling policy、单分支与 exact 可见区间

`ParabolaSpec` 唯一激活的 frozen scalar policy 为 `parabolic-sampling-policy-v1`：

| 字段 | 精确值 |
|---|---:|
| `samples_per_pixel` | 1 |
| `minimum_open_segment_samples` | 2 |
| `preferred_batch_points` | 4096 |
| `parameter_merge_ulps` | 8 |
| `viewport_boundary_ulps` | 8 |
| `target_residual_ulps` | 32 |
| `maximum_residual_ulps` | 256 |
| `cancellation_check_interval` | 256 |

该 v1 version 不允许替换上述语义。抛物线固定只有一个数学分支，`mathematical_branch_count=1` 且所有 segment 的 `branch_id=0`。令顶点为 `(h,k)`、有符号焦参数为 `p=focal_parameter`：

```text
竖轴（上/下）：x=h+2*p*t, y=k+p*t*t
横轴（左/右）：x=h+p*t*t, y=k+2*p*t
```

`p` 的符号自然决定四种 opening，不存在四套方向算法。Builder 将 viewport 分为 cross 轴和 opening 轴，exact 形成：

```text
cross_interval = sorted((cross_min-cross_vertex)/(2p),
                        (cross_max-cross_vertex)/(2p))
q_interval = sorted((axis_min-axis_vertex)/p,
                    (axis_max-axis_vertex)/p)
```

将 `t²` 限制到 `q_interval∩[0,+∞)`：`q_upper<0` 不可见，`q_upper==0` 至多是孤立顶点；`q_lower<=0` 产生候选 `[-sqrt(q_upper),+sqrt(q_upper)]`；`q_lower>0` 产生负、正两个候选 `[-sqrt(q_upper),-sqrt(q_lower)]` 与 `[+sqrt(q_lower),+sqrt(q_upper)]`。候选分别和 cross interval 求交。空集、singleton、单双区间、端点来源及有理值与 `±sqrt(q)` 的顺序全部在任何 Decimal/float sqrt 之前，以 Fraction 符号和平方的 exact 比较决定；exact singleton 返回 `no_visible_curve`。

非空区间随后才转换为有限 float64。端点若因舍入落在 viewport 外，只能在 `parameter_merge_ulps` 次 `nextafter` 内向区间内部修正，并以实际参数点和 `viewport_boundary_ulps` 复验。float64 转换后 `start>=stop`、两端点相同或 segment 坍缩返回 `numeric_range_unsupported`。最终最多两个互不重叠的 `OPEN` interval，按 `parameter_start` 稳定排序，ranges 不跨 interval 连线。

每段在 `max(abs(start),abs(stop))` 处计算导数像素速度上界。竖轴为 `dx/dt=2p, dy/dt=2pt`，横轴交换两项；点数为 `max(2, ceil(samples_per_pixel*maximum_pixel_speed*(stop-start))+1)`。所有速度、乘积、rounding 和总点数必须有限且通过集中 limits；不可安全计算返回 `numeric_range_unsupported`，资源不足返回现有 `resource_limit_exceeded`。

每个 float64 点使用与双曲线相同的 primitive normalized residual 公式。`R > 256*epsilon64` 拒绝为 `numeric_range_unsupported`；`32*epsilon64 < R <= 256*epsilon64` 成功并生成 `sampling_precision_limited`。抛物线无界，因此所有成功结果生成一次 `viewport_clipped`，`clipped_segment_count` 为实际成功 segment 数。

### exact 四边求交、排序与残差

Builder 将最终 float64 viewport 四边用 `Fraction.from_float` 还原为 exact 二进制有理数，固定按 left、right、bottom、top 求 `d*x + e*y + f = 0` 的交点。先 exact 去重并处理直线与边共线时的两个角点，随后转为有限 float64；两坐标都满足 `abs(a-b) <= 2 * max(ulp(a), ulp(b))` 才进行近重复合并。少于两个不同端点（完全不可见、单角点接触或转换后坍缩）返回 `no_visible_curve`；超过两个 float64 端点或不能有限表示返回 `numeric_range_unsupported`。唯一线段按方向投影 `(-e)*x + d*y` 的 exact 值稳定升序排列，不使用斜率专线、二维网格或 contour。

每个 float64 端点以 exact `Fraction.from_float` 计算归一化残差：

```text
R = |d*x + e*y + f| /
    (|d|*max(1, |x|) + |e|*max(1, |y|) + |f|)
```

`R > 16*epsilon64` 拒绝为 `numeric_range_unsupported`；`4*epsilon64 < R <= 16*epsilon64` 成功但生成 `sampling_precision_limited`；目标阈值以内不生成该 warning。

### RenderPlan、版本与 approval receipt

当前计划版本为 `render-plan-v2-typed-geometry`，参数化 sampler 契约版本为 `parameterized-sampler-v1`。封闭联合为：

```text
GeometrySegmentPlan = LineSegmentPlan | ParameterIntervalPlan
RenderItemPlan = ExplicitRenderItemPlan | GeometryRenderItemPlan
```

几何 approval 固定矩阵：

| exact Spec | mathematical branches | drawable segment capacity | exact segment type |
|---|---:|---:|---|
| `LineSpec` | 1 | 1 | `LineSegmentPlan` |
| `CircleSpec` | 1 | 4 | `ParameterIntervalPlan` |
| `EllipseSpec` | 1 | 4 | `ParameterIntervalPlan` |
| `HyperbolaSpec` | 2 | 4 | `ParameterIntervalPlan` |
| `ParabolaSpec` | 1 | 2 | `ParameterIntervalPlan` |

合法组合只有：

| plan | sampling policy | numeric version | parameterized version | memory |
|---|---|---|---|---|
| exact `ExplicitRenderItemPlan` | 非空 | `numeric-executor-v1-postorder-float64` | `None` | exact `RenderMemoryBudget` |
| exact `GeometryRenderItemPlan` | 非空 | `None` | `parameterized-sampler-v1` | exact `ParameterizedRenderMemoryBudget` |

receipt 在签发前和消费时交叉校验上述矩阵，并独立快照 exact Spec 类型、六个 primitive integer coefficients、EquationProvenance 文本/spans/limits、全部 Fraction 分子分母和几何 enum、ResolvedViewport、endpoint/interval、branch、sample、closure、版本、全部 memory 字段与输出配置。公开 API 不提供 receipt 构造器，也不接受调用者传入现成 geometry segments 直接批准。

### 内存预算与历史 limits 语义

`RenderMemoryBudget` 保持公开名称，新增并计入 `segment_metadata_bytes`。其 `fixed_bytes` 包含最终 x/y、artist、validity mask、segment ranges/metadata、RGBA canvas、PNG reserve/copy；`batch_bytes` 为 numeric executor 的额外 batch；`total_bytes = fixed_bytes + batch_bytes`。

`ParameterizedRenderMemoryBudget` 独立记录 `final_x_bytes`、`final_y_bytes`、`artist_data_bytes`、`segment_index_range_bytes`、`segment_metadata_bytes`、`parameter_batch_bytes`、`transcendental_workspace_bytes`、`validation_workspace_bytes`、`rgba_canvas_bytes`、`png_buffer_reserve_bytes` 与 `png_copy_bytes`。parameter/transcendental/validation 三项组成 `batch_bytes`，其余组成 `fixed_bytes`，`total_bytes = fixed_bytes + batch_bytes`。参数化预算没有也不伪装 `executor_extra_batch_bytes`。

直线 Builder 与 sampler 使用唯一共享公式。令 `N=2`、`B=1`、候选容量 `C=4`，则 final x/y 各 `N*8=16` bytes，artist `2*N*8=32`，range `1*2*8=16`，metadata `2*8=16`，parameter batch `N*8*B=16`，transcendental 为 `0`，RGBA 为 `width*height*4`，PNG reserve/copy 各为 `max_png_bytes`。exact workspace 的最大整数位数为 `4*max_equation_canonical_coefficient_digits + 2*1074 + 2`；按运行时 bigint digit 大小估算 28 个临时整数。validation workspace 为 exact workspace 加 `C*(2*8+1) + C*8 + N*8`。Builder 在求交前审批完整预算；sampler 在首次数组分配前重新计算、逐字段核对并复验 scene resource limits。

圆/椭圆共享另一个 `ParameterizedRenderMemoryBudget` 公式：总点数 `N`、batch `B` 下 final x/y 各 `N*8`，artist `2*N*8`，range 和 metadata 都按批准容量 4 各计 `4*2*8`，parameter batch 为 `B*8`，sin/cos 为 `2*B*8`，validation 覆盖命名的同时存活 exact bigint 清单、9 个候选角、4 个区间、`B` 个 bool 和 `B*8` residual workspace；RGBA 与两份 PNG 储备沿用集中 limits。令 `D=max_equation_canonical_coefficient_digits`、`C=4*D`、`F=1075`：由于 `10 < 2^4`，十进制 canonical coefficient 严格小于 `10^D` 可保守换算为 `C` 个二进制 bits；任一有限 float64 的 `Fraction.from_float` 分子和分母分别不超过 `F` bits。center 为 `-d/(2a)`，axis square 为 `q/(4*a^2*c)` 且 `q=d^2*c+e^2*a-4*a*c*f`；edge-center 差值的平方与 axis square 比较所形成的未约分交叉乘积最多 `5*C+2*F+6` bits。normalized residual 中系数乘 float ratio 平方、五项加法及最终 polynomial/scale 除法最多 `C+6*F+3` bits，与整数倍 `2^-52` 阈值比较再加最多 53 bits。因此椭圆/双曲线专用的 axis-aligned-conic 私有上界取 `max(5*C+2*F+6, C+6*F+56)`，纯整数计算，不使用浮点 `log2` 或安全倍率；按运行时 bigint digit 大小保守估算 40 个同时存活整数。默认 `D=768` 时，旧混合进制公式为 7,372 bits / 40,480 bytes，新上界为 17,516 bits / 94,560 bytes，仍低于 16 MiB exact-workspace 门禁。Builder 从完整固定开销反推最大合法 batch 并审批 total，sampler 在首次数组分配前以批准的 N/B 和当前 limits 逐字段重算、核对并复验 scene resources。

双曲线使用独立、同构但不复用 oval 40 项 liveness 的预算。总点数 `N`、batch `B` 下 final x/y 各 `N*8`，artist `2*N*8`，range 和 metadata 均按容量 4 各计 `4*2*8`，parameter 为 `B*8`，sinh/cosh 为 `2*B*8`；validation 为 exact workspace，加 12 个参数根 `12*8`、12 个 root-valid bool、4 个区间 `4*2*8`、`B` 个 bool 与 `B*8` residual。RGBA 为 `width*height*4`，PNG reserve/copy 各为 `max_png_bytes`。

双曲线 exact workspace 的 49 个同时存活命名整数为：`coefficient_a/c/d/e/f`；`center_x_numerator/denominator`、`center_y_numerator/denominator`；`transverse_square_numerator/denominator`、`conjugate_square_numerator/denominator`；`transverse_lower_numerator/denominator`、`transverse_upper_numerator/denominator`、`conjugate_lower_numerator/denominator`、`conjugate_upper_numerator/denominator`；`transverse_lower_square_numerator/denominator`、`transverse_upper_square_numerator/denominator`；`lower_axis_comparison_left/right`、`upper_axis_comparison_left/right`；`float_x_numerator/denominator`、`float_y_numerator/denominator`；`x_square_numerator/denominator`、`y_square_numerator/denominator`；`term_a_numerator`、`term_c_numerator`、`term_d_numerator`、`term_e_numerator`；`polynomial_numerator/denominator`、`scale_numerator/denominator`、`residual_numerator/denominator`；`comparison_cross_product_left/right`。两支横轴界与单调共轭界会在区间求交期间同时存活，所以不能借用 oval 的 40 项计数。位宽使用同一个 axis-aligned-conic 证明：axis-square 分子至多 `3*C+3`、分母至多 `3*C+2`，最终上界仍为 `max(5*C+2*F+6, C+6*F+56)`。Builder 在区间/数组建立前批准 total，并从固定开销反推不超过 4096 的最大 batch；sampler 在任何输出数组分配前按批准 N/B 与当前 limits 逐字段重算 budget 和 scene resource gate。

抛物线使用独立预算。总点数 `N`、batch `B` 下 final x/y 各 `N*8`，artist `2*N*8`，range 和 metadata 均按容量 2 各计 `2*2*8`，parameter batch 为 `B*8`，transcendental workspace 固定为 `0`。validation 为 `exact_workspace + 6*8 + 6*1 + 2*2*8 + B*1 + B*8`，分别覆盖 6 个参数根、6 个 root-valid bool、2 个 interval、batch finite bool 和 residual workspace；RGBA 为 `width*height*4`，PNG reserve/copy 各为 `max_png_bytes`。

抛物线 exact liveness 分阶段取最大值，不把不同时存活的 phase 相加，也不使用经验倍率。interval/topology phase 的 31 个同时存活整数为：`coefficient_a/c/d/e/f`；`vertex_x_numerator/denominator`、`vertex_y_numerator/denominator`、`focal_parameter_numerator/denominator`；`viewport_left/right/bottom/top_numerator/denominator`；`cross_lower/upper_numerator/denominator`、`q_lower/upper_numerator/denominator`；`comparison_rational_square_numerator/denominator`、`comparison_cross_product_left/right`。residual phase 的 27 个同时存活整数为：`coefficient_a/c/d/e/f`；同一 vertex/focal 六值；`float_x/y_numerator/denominator`、`x_square/y_square_numerator/denominator`；`polynomial_numerator/denominator`、`scale_numerator/denominator`、`residual_numerator/denominator`、`comparison_cross_product_left/right`。

抛物线 interval/root 比较使用独立位宽证明。对 float edge `e`、canonical vertex `v` 和 focal parameter `p`，`e-v` 的分子/分母分别至多为 `C+F+1` / `C+F` bits；`r=(e-v)/(2p)` 的每个 Fraction component 至多为 `2*C+F+1` bits，`q=(axis_edge-v)/p` 也满足同一统一上界。因此 `r^2` 的 component 至多为 `4*C+2*F+2` bits，`r^2` 与 `q` 的未约分比较叉积至多为 `6*C+3*F+3` bits；estimator 采用再保守 2 bits 的 `6*C+3*F+5`。抛物线 primitive residual 仍按五项 polynomial/scale 推导：除法叉积至多 `C+6*F+3` bits，与整数倍 `2^-52` 比较再加最多 53 bits，故 residual 上界为 `C+6*F+56`。最终抛物线专用 estimator 明确取 `max(6*C+3*F+5, C+6*F+56)`，不再复用椭圆/双曲线的 axis-aligned-conic 上界。默认 `D=768`、`C=3072`、`F=1075` 时，interval/root 项为 21,662 bits，residual 项为 9,578 bits，最终位宽为 21,662 bits；运行时按该位宽估算 interval phase 的 31 个同时存活 bigint。Builder 在签 receipt 前审批完整预算；sampler 在第一次数组分配前逐字段重算并再次运行 scene resource gate。batch planner 返回不超过 4096 的最大可批准值。

历史配置字段 `max_branches_per_item` 与 `max_total_branches` 保持名称、值、版本不变；它们当前实际批准 drawable segment/path capacity，不表示数学曲线 branch count。数学 branch count 由 exact geometry plan 矩阵独立声明和验证。本步骤未增加 `ApplicationLimits` 字段，也未修改 limits version。

### typed sampled result 与 warning 注册

公共成功联合为 `SampledCurve = SampledExplicitFunction | SampledParameterizedCurve`。

`SampledExplicitFunction` 保持原 exact class、原构造参数和原 dataclass 字段，包括 `finite_sample_count`、`nonfinite_sample_count`、`isolated_finite_count`、`discontinuity_break_count`、`visible_segment_count`；只新增只读 `segment_metadata` property，其 branch ID 全为 `None`、closure 为 `OPEN`。

`SampledParameterizedCurve` 要求自有且只读的一维 `float64` x/y、自有且只读的 `(S,2)` `int64` 半开 ranges、与 ranges 一一对应且 branch ID 非空的 `SampledSegmentMetadata`、typed warnings 和 `ParameterizedSamplingDiagnostics`。每个成功 segment 至少两个点。内部 approval snapshot 不在公共构造签名中。

`sample_parameterized_curve(plan, *, cancellation_probe=None)` 的第一项操作是现有 approval receipt 校验。Line 路径继续只消费一个已批准 `LineSegmentPlan`，保留 Stage 14B-2 的两点、`OPEN`、warning 和六个取消检查点语义不变。

Circle/Ellipse 路径只消费已批准 `ParameterIntervalPlan`。它在预算复验后一次分配最终 x/y/ranges，按绝对样本索引分 batch 生成 theta/sin/cos，OPEN 用 `j/(N-1)` 并显式固定 stop，CLOSED 用 `j/N` 且不采样 stop。每点用 primitive coefficients 与 `Fraction.from_float` exact 计算归一化隐式残差：超过 `256*epsilon64` 拒绝，超过 `32*epsilon64` 的 segment 报告 precision-limited。成功数组和 ranges 均自有、只读并保存现有 plan snapshot；部分弧生成一次实际弧数的 clipping warning，完整 CLOSED 曲线不生成。取消覆盖 approval 后、分配前、每段/每 batch、坐标写入后、每 256 个 residual 点、冻结前及 snapshot/返回前；取消仍返回中性 `SamplingCancelled`。sampler 不调用 resolver、Builder 或角区间规划器。

Hyperbola 路径同样只消费已签名批准的 `ParameterIntervalPlan`，并在首个输出数组分配前重投影几何、复验 interval/branch/policy/version/budget/limits。每个 OPEN 区间用 `j/(N-1)`，显式固定两个端点；按 batch 生成 sinh/cosh，拒绝任何非有限中间量或相邻点坍缩，不采用“生成 Inf/NaN 后过滤”的策略。每个 range 与一个非空 branch ID 元数据一一对应，x/y/ranges 均为自有只读数组；成功总是生成一次带实际 segment 数的 `viewport_clipped` warning，并按上述 exact residual 阈值可追加 precision warning。取消覆盖 receipt 后、context/budget 复验后、分配前后、每段/每 batch、坐标后、每 256 个 residual、metadata/冻结/snapshot/返回前；sampler 不重入 resolver、Builder 或 interval planner。

Parabola 路径只消费已签名批准的最多两个 `ParameterIntervalPlan`，在首个输出数组分配前重投影 geometry，并复验 spec/interval/branch/policy/version/budget/limits。每个 OPEN interval 用绝对样本索引的 `j/(N-1)`，显式固定两端点；batch 内使用 `np.errstate(over="raise", invalid="raise")`，把 `t*t` 直接写入对应最终坐标 slice，不建立平方或 transcendental 临时数组。参数、坐标全部有限，每个 segment 至少有一对相邻不同点；每点 exact residual。metadata 与 range 一一对应且 branch 固定为 0，x/y/ranges 自有只读并保存现有 plan snapshot。所有成功结果报告实际 segment 数的 clipping warning，并可追加 precision warning。取消覆盖 receipt 后、context/budget 后、首次分配前后、每 segment/batch、坐标后、每 256 个 residual、metadata/冻结/snapshot/返回前；sampler 不重入 resolver、Builder 或 interval planner。

Stage 14B-2 验收矩阵继续覆盖 line v1 的全部冻结行为。Stage 14C 验收矩阵覆盖 angular policy、完整/裁切/跨 seam/最多四弧、切点和不可见、outward 自动视口、确定性点数与 batch、完整预算/receipt 篡改、残差 warning/error、所有新增取消检查点、正式数组所有权/冻结、Circle/Ellipse 直接原型及显函数/renderer/executor/workers/public API 静态边界。Stage 14D-1 验收矩阵覆盖双曲线两种轴向、平移、左右/上下 branch identity、单支/拆分/双支/孤立切点/不可见、exact-before-root 决策、教学 auto viewport、导数点数、49 项 exact liveness 与所有预算边界、receipt 篡改、残差 warning/error、非有限与坍缩、所有取消检查点和相同静态架构边界。Stage 14D-2 验收矩阵覆盖四种 opening、平移、auto teaching window、单/双/空/singleton interval、exact-before-sqrt、导数点数、31/27 项 exact liveness、零 transcendental 预算与 batch 精确边界、完整 receipt/budget 篡改、残差 warning/error、underflow/overflow/坍缩、所有取消检查点、数组所有权、四向正式原型和相同静态阶段边界。

Stage 14E 新增跨类型矩阵，使用 exact `LineSpec | CircleSpec | EllipseSpec | HyperbolaSpec | ParabolaSpec` 和既有 M1 显函数复验公共契约、AUTO_GEOMETRY/aspect、exact plan/result 字段、segment topology、不误连、预算、只读数组/snapshot、warning/error、receipt 全字段篡改、极端合法输入、`NUMERIC_RANGE_UNSUPPORTED`、`NO_VISIBLE_CURVE` 和合作取消。独立 oracle 仅用 primitive equation 与 `Fraction.from_float`，不调用生产 residual/projector/planner；静态检查确认无 contour、无 sampler 重入、无 geometry renderer/scene executor/Actor/UI/第二套公开管线。确定性探针覆盖 14 个固定教学与裁切场景、70 个保留记录；全部成功，原始总耗时 0.9235–70.9235 ms，样本数 2–2400、segment 数 1–2，最大获批总内存预算 69,301,000 bytes。该数据是开发参考，不是正式 P50/P95 或 M1.5 性能结论。

最终自动化证据为 Stage 14D-1/14E、public API 与 benchmark 契约定向复验 331 passed、Stage 14B-1/B-2/C/D-1/D-2/E 联合测试 614 passed、`tests/engine` 1860 passed、public API 5 passed、`tests/benchmarks` 101 passed、完整回归 2325 passed，全部为 0 failed / 0 errors / 0 skipped。

### Stage 15A 统一 renderer 契约

Stage 15A 在现有 `math_drawing_assistant/engine/renderer.py` 边界内把六种 exact 类型的 typed sampled output 统一渲染为 Agg/PNG。新公共入口 `render_sampled_curve_png(plan, sampling_outcome, *, cancellation_probe=None)` 与旧入口 `render_explicit_png` 委托同一实现核心：旧入口保持原显函数专用契约（几何 plan/outcome 按既有消息拒绝），两入口互不转发，renderer 中不存在第二行为链。15A 完成时 `SceneRenderExecutor` 仍只调用旧入口；15B 已将 production caller 收口为统一入口，旧 wrapper 当前无 production caller。

校验顺序全部先于任何 Matplotlib 资源与 `BytesIO`：approval receipt 第一操作 → item plan 联合门（`ExplicitRenderItemPlan`；统一入口额外接受 `GeometryRenderItemPlan`，否则原消息 `approved render-plan item contract failed`）→ outcome 三分发（`ErrorInfo` item_id 一致性透传、`SamplingCancelled`→`RenderCancelled`、typed sampled 流）→ 几何流 provenance 门（既有 `_sampled_parameterized_curve_matches_approved_plan` helper；type 与 snapshot 两类拒绝合并为一条 `sampling outcome type mismatch`，与显函数两条消息的粒度不对称属既定取舍）→ 几何 render context（scene 恰一项、五类 exact geometry Spec 封闭集合、item_id 三方一致、limits 版本、legend 可用性）→ 几何 sampled 契约复验。最后一步先重跑 `SampledParameterizedCurve.__post_init__()`；该方法只检查 metadata 的 exact tuple/type、数量和 branch ID 非空，不会调用每个 metadata 的 `__post_init__()`，因此 renderer 随后逐项显式调用 `SampledSegmentMetadata.__post_init__()`，并要求获批 segments、ranges、metadata 三者数量完全相等，branch ID 与 closure 分别精确等于对应获批 segment，每个 range 长度精确等于对应 `segment.sample_count`，且 ranges 从 0 开始逐段连续并恰好覆盖全部 sampled points。provenance snapshot 不含当前 sampled metadata，不能替代这组事后篡改防线。任一失败统一映射为 `internal_error / sampled result contract validation failed`；零 ranges 篡改同样在资源前被拒绝，几何路径不由 renderer 合成 `no_visible_curve`（与 `ERROR_CODE_REGISTRY` 中该码的 sampler 来源登记不冲突：合法不可见只以上游 planner/sampler `ErrorInfo` 原样透传，显函数路径保留其既有零 ranges 防御行为）。`sampled result contract validation failed` 因此成为该既有消息在几何路径的第二发射点。

P3-1 的冻结 AST 边界解析直接 `import`、`from ... import` 的 `as` 绑定以及模块 alias 的属性调用；renderer 的 sampler/analyzer/resolver/`RenderPlanBuilder` 禁止入口与两个 renderer production entry 均按解析后的静态调用名检查。15B 只把 caller 期望改为：旧入口无 production caller，统一入口仅由 `scene_executor.py` 调用；其余 AST 扫描、自证、renderer singleton、contour/重依赖/反向依赖禁令保持不变。本规则不宣称覆盖名称重赋值、`getattr`、star import 或任意动态 Python；既有常量字符串 `importlib.import_module` / `__import__` 检查只覆盖已登记的模块边界。

绘制契约与显函数路径同构：每段开头轮询取消（检查点序：资源前一次 → 资源创建 → 每 segment 前 → 编码前 → 编码后 → 返回前，满足既有 Agg actor probe 的 pass-poll 拓扑）；主段以冻结采样数组的零拷贝 view 绘制，双曲线分支、抛物线分段与多条圆弧互不误连；legend 取 `provenance.normalized_input` 且多 segment 只一个条目；EQUAL 视口固定 equal/box 且绘制后不漂移；编码沿用 `min(png_buffer_reserve_bytes, png_copy_bytes)` 上限、Agg 直连 `print_png`、签名 + IHDR 宽高校验；`finally` 全释放（buffer close → axes/figure clear → 引用置空）。

CLOSED 圆/椭圆的视觉闭合由主段 N 点折线加一条独立 2 点闭合 chord artist 完成（数据为 `([x[stop-1], x[start]], [y[stop-1], y[start]])`，样式与主段一致、无 label、不产生 legend 条目）。闭合弦与相邻弦等角距（`minimum_closed_curve_samples = 64`），几何上与拼接成 N+1 点折线画出完全相同的线段集合；区别仅在两个 artist 交于共享端点的亚像素抗锯齿合成差异。内存口径（BC-15A-01）：chord 正式绘图数据为常量 4 个 float64 = 32 bytes/item（每 item 至多一个 CLOSED segment 由审批契约结构性保证），由 sampler 返回后不再存活的 `validation_workspace_bytes` 批处理阶段复用覆盖——该阶段预算在渲染期已死，32 bytes 落在其容量之内，自动化测试断言 `32 <= validation_workspace_bytes`；不引入任何 O(N) 拼接拷贝，不修改任何预算公式、limits、plan 或 sampler（`render_plan.py` 与 `parameterized_budget.py` 对 15A 只读）。此前「阶段 8C-1」关于库内不可观测分配不计入上界的豁免句在此仅作类比引用：chord 数据是项目自建并传入的第二份绘图数据，其覆盖依据是上述阶段复用论证而非该豁免句。

### Stage 15B 统一 executor 与结果契约

唯一 production 链为 `PlotSceneRequest → 单项/manual/requested-kind 门禁 → analyze_plot_item → PlotSceneSpec → resolve_single_item_viewport → RenderPlanBuilder.build → exact typed sampler → render_sampled_curve_png → PlotSceneResult`。`ExplicitFunctionSpec` 只允许 exact `ExplicitRenderItemPlan` 和 `sample_explicit_function`；`LineSpec | CircleSpec | EllipseSpec | HyperbolaSpec | ParabolaSpec` 只允许 exact `GeometryRenderItemPlan` 和 `sample_parameterized_curve`。Spec、plan、outcome 或 item identity 不一致一律形成绑定当前 item 的不可恢复 `internal_error`；不调用错误 sampler 或 renderer。`render_explicit_png` 保留公共兼容 wrapper，但不再有 production caller。

结果以 `ConcretePlotType` 正交细分粗粒度 `PlotKind`：`EXPLICIT_FUNCTION`、`GENERAL_LINE`、`CIRCLE`、`ELLIPSE`、`HYPERBOLA`、`PARABOLA`。`PlotItemDiagnostics` 登记计划/实际采样点、sampled segment 和 visible segment；`PlotSceneDiagnostics` 登记计划/实际总采样点、获批 `memory_budget.total_bytes` 和最终 PNG byte count。production 成功必须携带完整 item/scene diagnostics；plan 成功后的 sampling failure 只保留 planned 部分，sampling 成功后的 render failure 保留完整采样诊断但不登记 PNG count。结果不携带 RenderPlan、receipt、NumPy array 或 Matplotlib 对象。

warning 所有权固定为：viewport warning 只属于 scene，sampling warning 属于 item；scene 先 viewport 后 sampling，跨来源 code 稳定保留首次，同一 sampler outcome 内重复 code 是 `internal_error`。Builder 或 sampler 的 `no_visible_curve` 都是 typed scene/item failure，后续 renderer 不运行，也不生成空白成功 PNG。item 已知后的 ErrorInfo 必须精确绑定 item_id；缺失时复制补绑，冲突时改为绑定当前 item 的 `internal_error`，scene 与 item 共享同一 ErrorInfo 对象。

`elapsed_ms` 使用单调高分辨率时钟并固定六阶段顺序：`request_validation`、`analysis`、`viewport_resolution`、`render_plan`、`sampling`、`rendering`；失败只保留到失败阶段的有序前缀。合法 `SamplingCancelled`/`RenderCancelled` 必须匹配当前 item，统一返回完全中性的无 error/item/viewport/warning/diagnostics/timing sentinel；错误 identity 不得伪装取消。该 timing 是运行诊断，不是 Stage 15F 正式性能证据。

### 明确未实现与门禁

Stage 14E 已完成，P0-06 已关闭，Stage 14 已完成并允许进入 Stage 15。Stage 15-0 已冻结执行章程；Stage 15A 统一 renderer 已完成；Stage 15B 统一 executor 与公共结果契约候选实施已完成，等待真正独立只读审核和总架构师验收。contour 后备链路、多 item、RenderActor/AppController/UI 的 M1.5 真实组合与 GUI 整合仍未实现；15C 及后续子步尚未开始。

该结论不宣称 P0-07、真实教材验收、正式 P50/P95、M1.5 checkpoint 或核心 MVP 完成；这些仍受 Stage 15 及后续门禁约束。
