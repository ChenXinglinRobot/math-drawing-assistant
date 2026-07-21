# 支持公式与横切契约

文档版本：stage-6-input-frontend-v1-worktree
状态：阶段 6 输入前端已在工作区实现并通过定向自动测试，等待项目所有者检查；本文不声明阶段验收通过
单一事实来源职责：本文件登记输入语法、转换表、token 白名单、limits 字段与当前值、稳定错误码及验收矩阵。限制数值的唯一可执行来源仍是 `math_drawing_assistant/config/limits.py`。

## 当前实现边界

当前输入前端只执行以下数据流：

```text
原始用户文本
→ normalize_input
→ NormalizedInput(text, SourceMap)
→ tokenize
→ tuple[Token, ...]
→ split_equation
→ ExpressionInput | EquationInput
```

它不构造 AST，不导入或调用 SymPy，不执行求值、化简、展开、移项、求解、函数参数语义检查或绘图分类。本文中的“支持”仅指阶段 6 可规范化、词法化和拆分，不表示公式已经能够绘图。

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

## equation_splitter 契约

`split_equation` 只接收 tokenizer 已完整消费的 `tuple[Token, ...]`：

- 没有等号：返回冻结的 `ExpressionInput`，保留完整 token tuple、规范化区间和原始区间；
- 恰好一个等号且两侧非空：返回冻结的 `EquationInput`，左右 token 顺序、规范化区间和原始区间分别保留；
- 拒绝空输入、`=x`、`x=` 和两个或更多等号；
- `<`、`>`、`<=`、`>=`、`!=`、`≤`、`≥`、`≠` 在 tokenizer 阶段以 `unsupported_relation` 拒绝；
- 不交换左右两侧，不判断哪侧是 `y`，不构造 `lhs-rhs`，不移项、不求解、不分类；
- 不从换行、逗号或分号拆分多条公式。

## SourceMap 数据契约

`SourceMap`、`NormalizedInput`、`Token` 和拆分结果均使用 `@dataclass(frozen=True, slots=True)`。所有区间复用 `models.errors.SourceSpan`，统一为零基半开区间 `[start, end)`。

- `character_spans[i]` 是产生规范化字符 `i` 的非空原始区间；
- 一对一替换保留原字符区间；
- 一对多展开为每个结果字符重复同一原始区间；
- 多对一替换保存完整原始区间；
- 非空规范化区间映射为首、末贡献字符覆盖的原始区间；
- 零长度边界在某字符之前时映射到该字符原始区间的 `start`，最终边界映射到最后字符原始区间的 `end`；空 SourceMap 的唯一边界映射到原始偏移 `0`；
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
版本：`limits-v1-initial-safety`
状态：`initial_safety`；这些值是初始安全上限，不是性能承诺。若代码值变化，必须在同一变更同步本表和边界测试。

<!-- LIMIT_FIELD_INDEX_START -->
| 字段 | 语义 | 当前值 | 阶段 6 使用 |
|---|---|---:|---|
| `version` | 稳定 limits 契约版本 | `limits-v1-initial-safety` | 读取 |
| `status` | 初始安全或基准冻结状态 | `initial_safety` | 读取 |
| `max_input_characters` | 原始输入最大字符数 | 4,096 | normalizer 在删除/展开前检查 |
| `max_tokens` | 最大 token 数 | 1,024 | tokenizer 每次追加前检查 |
| `max_ast_nodes` | 最大 AST 节点数 | 2,048 | 阶段 7 使用；阶段 6 不构造 AST |
| `max_nesting_depth` | 最大词法/AST 嵌套深度 | 64 | tokenizer 扫描左括号时检查 |
| `max_numeric_digits` | 单个数字最大数字位数 | 128 | tokenizer 数字扫描期间检查 |
| `max_decimal_places` | 最大小数位数 | 64 | tokenizer 数字扫描期间检查 |
| `max_rational_numerator_digits` | 有理数分子最大位数 | 128 | 阶段 7+ 使用 |
| `max_rational_denominator_digits` | 有理数分母最大位数 | 128 | 阶段 7+ 使用 |
| `max_absolute_exponent` | 指数绝对值上限 | 1,000 | 阶段 7 使用 |
| `max_function_arguments` | 单个函数最大参数数 | 8 | 阶段 7 使用 |
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
<!-- ERROR_CODE_REGISTRY_END -->

所有阶段 6 用户错误均返回中文 `user_message`、原始输入 `SourceSpan` 和 `recoverable=True`。`technical_message` 只包含脱敏类别、计数或 token kind，不包含完整原始公式，也不暴露内部规范化偏移。

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

随机健壮性测试只接受成功的冻结拆分结果或结构化 `ErrorInfo`，并断言不产生日志记录。它使用 Python 标准库固定种子，不引入 Hypothesis 或其他依赖。

## 版本与变更规则

1. 新增或改变公开语法、错误码或 limits 字段时，同一变更必须更新对应实现、行为测试和本文件。
2. 已发布错误码不得改变字符串值或含义。
3. 初始安全上限只有在冻结测量协议并取得基准证据后，才可改标为基准冻结；它们不是产品性能承诺。
4. 不在 UI、模型、测试或其他文档建立第二套独立阈值或错误码表。
5. 阶段 7 parser、AST、plot classifier 和 typed validators 尚未实现；不得把本阶段词法成功解释为数学语义有效或可绘图。
