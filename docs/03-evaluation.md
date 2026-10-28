# 03 评估

## 用例、预期与实际结果

运行命令见 README。以下均为**离线 Mock 的实际运行记录**（2026-10-28 执行），
输出全文在 `examples/*.output.json`。

| 用例 | 输入 | 预期 | 实际结果 | 验收点 |
|---|---|---|---|---|
| 正常 | `normal.input.json`（30 秒目标） | 首稿超时 → 压缩 → 达标交付 | `success`；首稿估算 **45 秒** → revise → **21 秒**；分镜 3 个，素材 P01/P02/P03 | 正常生成、超时长修正 |
| 缺信息 | `missing.input.json`（缺 topic/audience/target_duration） | 请求补充 | `needs_input`，`missing_fields` 列出 3 个缺失字段，未调用任何工具 | 缺关键信息 |
| 无素材 | `no-material.input.json`（量子计算云服务） | 改写查询重试后失败 | 两次 search（第 2 次 `is_rewrite: true` 且查询不同）→ `failed_no_material`，不输出脚本 | 无素材 |
| 工具失败 | `tool-failure.input.json`（模拟检索故障） | 重试后明确失败 | 两次 search 均「工具错误: 素材检索服务不可用（模拟故障）」→ `failed_tool` | 工具失败 |

两条以上不同执行路径（正常路径 7 步含 revise 调整；无素材路径 search→search→finish；
工具失败路径重试后放弃）体现了模型根据工具结果调整动作。trace 含步骤、工具参数、
返回摘要与决策依据（`rationale`），未包含模型内部思维过程。

## 关键核对点（对应审核要点）

- **素材 ID ↔ 分镜 ↔ 检查结果逐一对应**：`normal.output.json` 每个分镜带
  `material_ids`，旁白仅复述该素材 `facts`，无「效率提升 80%」类编造表述。
- **改变时长/检索结果，下一步动作随之调整**：首稿 45 秒 > 30 → 下一步是 `revise`；
  压缩后 21 秒 ≤ 30 → 下一步是 `check_rules`；检索为空 → 下一步是改写后的第二次 `search`。

## 自动化测试

`python -m unittest discover -s tests -v`：6 个用例全部通过，
实际执行记录见 `examples/test-results.txt`。覆盖：正常路径时长修正断言
（首稿 45 秒、动作序列、素材可追溯、无编造表述）、缺信息、无素材改写重试、
工具失败重试、步数上限（`max_steps=3` → `unfinished_step_limit`）、CLI 非法输入退出码非零。

## 已知限制

- 时长为字数/语速的估算，未考虑停顿、画面时长；Mock 决策器是确定性策略，
  真实模型下的决策质量未在本仓库验证（需配置密钥用 `--model openai` 实测）。
- 关键词检索对同义词覆盖有限；规则检查是字符串匹配，无法识别语义层面的夸大宣传。
