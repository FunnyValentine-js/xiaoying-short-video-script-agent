# 02 方案

## 总体流程（ReAct 循环）

`src/main.py` 的 `run_agent` 实现「模型选择动作 → 执行工具 → 观察结果 → 模型调整下一步」：

```
        ┌────────────────────────────────────────────┐
        ▼                                            │
  模型 decide(task, state) → {action, args, rationale}
        │
        ├─ search        → 素材检索工具      ─┐
        ├─ draft         → 生成/重写脚本      │ 观察结果写入 state
        ├─ estimate      → 时长估算工具       │ 与 trace
        ├─ revise        → 压缩/修正脚本      │
        ├─ check_rules   → 品牌规则检查      ─┘
        └─ finish        → 输出结果与状态
```

步数上限 `MAX_STEPS = 8`，超限返回 `unfinished_step_limit`。

## 工具（本地函数 Mock）

| 工具 | 职责 | 实现 |
|---|---|---|
| `tool_search_materials` | 按关键词检索素材库 | 匹配 `data/materials.json` 的 `keywords`；`simulate_tool_failure` 时抛 `ToolError` |
| `tool_estimate_duration` | 估算分镜/总时长 | 旁白字数 ÷ 语速（约 5 字/秒），向上取整 |
| `tool_check_rules` | 品牌规则检查 | 禁止素材无依据的宣传词（如「效率提升」），检查必需品牌元素（「小影」） |

## 动态决策（模型如何根据结果调整动作）

决策方是 `model.decide(task, state)`，执行骨架只负责调用工具和记录 trace，**决策本身由模型做出**：

- 检索无结果 → 决定**改写查询**（追加同义描述）重试一次；仍无结果 → `failed_no_material`；
- 检索工具报错 → 决定重试一次；连续失败 → `failed_tool`；
- 估算超出目标时长 → 决定 `revise` 压缩，压缩后**必须重新估算**；修正 2 次仍超标 → `failed_constraints`；
- 规则检查未通过 → 决定修正违规表述后重新检查；
- 缺关键输入 → 直接 `needs_input`，不浪费工具调用。

默认决策器 `OfflineMockModel` 是**离线确定性 Mock**（显式策略），只验证流程；
`--model openai` 切换 `OpenAIModel` 后，以上决策全部由真实模型以 JSON 形式自主返回，
代码仅约束动作空间与状态摘要。Mock 结果不能证明真实模型的决策质量。

## 技术取舍

- **零依赖、单文件**：3 小时时限内优先把决策循环、错误路径与可追溯性做扎实，
  而非引入 LangGraph 等框架；动作空间小（6 个动作），框架收益低、调试成本高。
- **时长按字数估算**：比 TTS/分镜表精确估算粗糙，但确定性高、可测试；
  已在 `risks` 中标注「估算值，以成片为准」。
- **素材检索用关键词匹配**：合成数据量级下足够；真实场景应换向量检索，
  接口（query → hits）保持不变。
