# 04 AI 使用记录

## 使用了 AI 辅助的部分

本项目整体在 AI 编码助手（Kimi Code CLI）对话中完成，AI 参与了：
需求拆解、目录组织、代码（`src/main.py`、`tests/test_main.py`）与文档初稿的生成。

## 个人修改与决策

- 验收点拆解与状态机设计（`success` / `needs_input` / `failed_no_material` /
  `failed_tool` / `failed_constraints` / `unfinished_step_limit`）由本人确定；
- 决策逻辑必须与「执行骨架」分离（动作由 `model.decide` 返回，循环只执行与记录），
  以满足「不是固定条件分支」的要求——这一取舍由本人提出，AI 按此实现；
- 时长估算口径（5 字/秒）、压缩策略分档（revise 次数对应不同旁白模板）、
  Mock 边界声明的写法由本人审定；
- 所有示例输出与测试均在本地实际运行核对，未直接采用 AI 声称的结果。

## 验证方式

- 4 组场景逐一运行并将实际输出保存至 `examples/*.output.json`，与本人口头预期比对
  （首稿 45 秒 → 压缩后 21 秒等关键数字逐一核对）；
- `python -m unittest discover -s tests -v` 实际执行，6 用例全绿，记录于
  `examples/test-results.txt`；
- 人工抽查 `normal.output.json` 中每个分镜的 `material_ids` 与 `data/materials.json`
  的 `facts` 一一对应，确认无编造产品事实。
