# 01 需求

## 用户与目标

- **用户**：短视频创作者（尤其是新手），需要快速产出可编辑的脚本初稿。
- **目标**：给定主题、受众、平台、目标时长、风格，生成**有事实依据**（可追溯到素材 ID）、
  **满足时长限制**的脚本，并明确标注风险与任务状态。

## 输入与输出

- 输入（JSON）：`topic`、`audience`、`platform`、`target_duration`（秒）、`style`；
  测试用途字段 `task_id`、`simulate_tool_failure`。
- 输出（JSON）：`title`、`scenes`（分镜画面、旁白、素材 ID 列表）、
  `per_scene_seconds` / `total_seconds`、`material_ids`、`risks`、`status`、`trace`、
  失败时附 `missing_fields`。

## 范围

- 做：素材检索、脚本生成、时长估算与压缩修正、品牌规则检查、失败状态的明确报告。
- 不做：真实视频渲染、线上部署、多 Agent 协作、界面（CLI 即可）。

## 成功标准（验收点）

| # | 场景 | 期望 |
|---|---|---|
| 1 | 正常生成 | `success`，时长 ≤ 目标，每个分镜可追溯到素材 ID |
| 2 | 缺关键信息 | `needs_input`，列出缺失字段，不强行生成 |
| 3 | 无素材 | 改写查询重试一次后仍无结果 → `failed_no_material`，不输出脚本 |
| 4 | 工具失败 | 重试一次仍失败 → `failed_tool` |
| 5 | 超时长 | 首稿超时 → 压缩 → 重新估算达标；多次修正仍失败则 `failed_constraints` |

任何场景下都不得编造素材中不存在的产品事实（如「效率提升 80%」）。
执行步数达到上限（8 步）时返回 `unfinished_step_limit`。
