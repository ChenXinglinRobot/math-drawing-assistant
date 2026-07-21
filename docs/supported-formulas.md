# 支持公式与横切契约基线

文档版本：stage-5-baseline-v1
状态：阶段 5 初始基线；尚未发布任何数学输入能力
单一事实来源职责：本文件登记公式能力状态、limits 字段索引、已发布错误码及未来验收矩阵。限制数值的唯一可执行来源是 `math_drawing_assistant/config/limits.py`；本文不复制临时数值。

## 当前实现阶段

阶段 4 已完成固定 PNG 到 Qt 预览链路。阶段 5 只建立 limits、错误、耗时诊断、日志和工具无关类型政策。

当前已经实现的非数学能力包括：

- 不可变 Scene/Item、Viewport、RenderPlan 和结果模型；
- AppController 的 request/revision 与旧成功结果保护基础；
- 静态 Qt Widgets 界面及可访问性基线；
- 固定 PNG bytes 到 QImage/QPixmap 的所有权安全预览链路；
- 阶段 5 的横切基础设施。

## 当前公式支持状态

当前尚未实现 normalizer、tokenizer、parser、数学分类、采样或真实绘图。现阶段不能宣称支持 `y=x²`、`sin(x)`、圆、直线或圆锥曲线输入。阶段 4 的固定 PNG 预览只验证图片边界，不等于公式绘图能力。

未来语法只有在相应阶段实现、测试并更新本文件后才可进入“支持”状态。这里不提前定义 parser 行为、OCR 契约、密集振荡阈值、性能 P95、M1.6 最终项目数或采样预算。

## limits 配置索引

配置类型：`ApplicationLimits`
唯一默认实例：`DEFAULT_LIMITS`
版本读取：`DEFAULT_LIMITS.version`
当前状态读取：`DEFAULT_LIMITS.status`；当前为“初始安全上限”，尚未经过性能基准冻结。

<!-- LIMIT_FIELD_INDEX_START -->
| 字段 | 语义 | 当前状态 |
|---|---|---|
| `version` | 稳定 limits 契约版本 | 已建立 |
| `status` | 初始安全或基准冻结状态 | 初始安全 |
| `max_input_characters` | 输入最大字符数 | 临时上限 |
| `max_tokens` | 最大 token 数 | 临时上限 |
| `max_ast_nodes` | 最大 AST 节点数 | 临时上限 |
| `max_nesting_depth` | 最大嵌套深度 | 临时上限 |
| `max_numeric_digits` | 单个数字最大位数 | 临时上限 |
| `max_decimal_places` | 最大小数位数 | 临时上限 |
| `max_rational_numerator_digits` | 有理数分子最大位数 | 临时上限 |
| `max_rational_denominator_digits` | 有理数分母最大位数 | 临时上限 |
| `max_absolute_exponent` | 指数绝对值上限 | 临时上限 |
| `max_function_arguments` | 单个函数最大参数数 | 临时上限 |
| `max_scene_items` | 场景最大 item 数 | 临时上限 |
| `max_sample_points_per_item` | 单项最大采样点数 | 临时上限 |
| `max_total_sample_points` | 场景最大总采样点数 | 临时上限 |
| `max_branches_per_item` | 单项最大分支数 | 临时上限 |
| `max_total_branches` | 场景最大总分支数 | 临时上限 |
| `max_estimated_memory_bytes` | 预计内存上限 | 临时上限 |
| `max_png_bytes` | 输出 PNG 字节上限 | 临时上限 |
| `min_image_width` | 图片最小宽度 | 临时边界 |
| `max_image_width` | 图片最大宽度 | 临时边界 |
| `min_image_height` | 图片最小高度 | 临时边界 |
| `max_image_height` | 图片最大高度 | 临时边界 |
| `min_dpi` | DPI 最小值 | 临时边界 |
| `max_dpi` | DPI 最大值 | 临时边界 |
| `max_log_file_bytes` | 单个日志文件容量 | 初始安全上限 |
| `log_backup_count` | 日志轮转备份数量 | 初始安全上限 |
| `max_log_field_text_length` | 日志字段文本最大长度 | 初始安全上限 |
<!-- LIMIT_FIELD_INDEX_END -->

字段索引由自动测试与 dataclass 字段同步；数值不在文档中重复维护。

## 错误码注册表

<!-- ERROR_CODE_REGISTRY_START -->
| 稳定值 | 含义 | 首次用途 |
|---|---|---|
| `invalid_input` | 输入无效；保留阶段 2 已有值与含义 | 既有模型契约 |
| `render_failed` | 绘图任务失败；保留阶段 2 已有值与含义 | 既有控制器回退 |
| `invalid_request` | 请求级通用验证失败 | 阶段 5 基础设施 |
| `resource_limit_exceeded` | 通用资源限制被超过 | 阶段 5 基础设施 |
| `internal_error` | 已脱敏的内部错误 | 阶段 5 基础设施 |
<!-- ERROR_CODE_REGISTRY_END -->

错误码字符串不可复用为新含义。未来 parser、tokenizer、圆锥曲线、OCR 或供应商错误码只在对应阶段按实际需要增加。

## 未来语法契约占位

状态：空；等待阶段 6/7 实现和验证。此处不把 PRD 示例误写成已支持语法。

## 未来验收公式矩阵占位

状态：空；只有实现、自动测试和人工验收证据齐备后才登记公式。当前没有教材验收结果。

## 版本与变更规则

1. 新增或改变公开语法、错误码或 limits 字段时，同一变更必须更新对应实现、行为测试和本文件。
2. 已发布错误码不得改变字符串值或含义。
3. 初始安全上限只有在冻结测量协议并取得基准证据后，才可改标为基准冻结；它们不是产品性能承诺。
4. 不在 UI、模型、测试或其他文档建立第二套独立阈值。
