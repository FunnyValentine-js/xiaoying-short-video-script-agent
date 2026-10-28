# 短视频脚本生成 Agent（题目一）

帮助创作者生成**有事实依据、满足时长限制**的可编辑短视频脚本。

> **模型边界说明**：本仓库默认使用**离线确定性 Mock 决策器**（`OfflineMockModel`），
> 不调用真实大模型。Mock 只验证 Agent 流程、工具调用链与错误处理，
> **不代表真实模型的生成质量**。真实模型接入见下文「可选：真实模型」。

## 快速运行

Python 3.10+，无第三方依赖，默认无需密钥。在仓库根目录执行：

```sh
python src/main.py --input examples/normal.input.json
python src/main.py --input examples/missing.input.json
python src/main.py --input examples/no-material.input.json
python src/main.py --input examples/tool-failure.input.json
python -m unittest discover -s tests -v
```

程序向 stdout 输出 JSON；业务异常以 JSON 中的 `status` 字段返回；
输入文件格式错误返回非零退出码（2）。界面采用 CLI。

> Windows 下若控制台中文乱码，设 `PYTHONUTF8=1` 后再运行，不影响输出文件内容。

## 可选：真实模型

```sh
set OPENAI_API_KEY=sk-...            # 必需
set OPENAI_BASE_URL=https://.../v1   # 可选，OpenAI 兼容接口
set MODEL_NAME=gpt-4o-mini           # 可选
python src/main.py --input examples/normal.input.json --model openai
```

真实模型（`OpenAIModel`）自主做出全部 ReAct 决策，代码只提供工具与状态。

## 项目目录

```text
.
├── README.md
├── requirements.txt              # 无第三方依赖的声明
├── .env.example                  # 仅真实模型需要；Mock 模式无需配置
├── .gitignore
├── docs/
│   ├── 01-requirements.md
│   ├── 02-solution.md
│   ├── 03-evaluation.md
│   ├── 04-ai-usage.md
│   └── 05-retrospective.md
├── src/
│   ├── __init__.py
│   └── main.py                   # CLI、ReAct 主循环、工具、Mock/真实模型
├── tests/test_main.py
├── data/materials.json           # 合成素材与品牌规则
└── examples/                     # 4 组输入、实际输出、测试记录
```

## 评审导航

| 检查项 | 入口 |
|---|---|
| 业务目标 | [需求](docs/01-requirements.md) |
| 流程与调用链 | [方案](docs/02-solution.md) |
| 测试、预期、结果 | [评估](docs/03-evaluation.md) |
| AI 辅助边界 | [AI 使用](docs/04-ai-usage.md) |
| 不足及改进 | [复盘](docs/05-retrospective.md) |

输出 JSON 中 `trace` 记录每一步的动作、工具参数、返回摘要与决策依据；
`scenes[].material_ids` 引用 `data/materials.json` 的素材 ID。
`examples/*.output.json` 是离线 Mock 的实际运行结果，不是真实模型调用记录。
