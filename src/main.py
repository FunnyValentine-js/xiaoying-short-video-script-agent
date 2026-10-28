"""短视频脚本生成 Agent：CLI 入口与完整执行流程。

模型接入说明（边界）：
- 默认使用 OfflineMockModel，一个离线、确定性的决策策略，不调用真实大模型。
  Mock 只用于验证 Agent 流程、工具调用链与错误处理，不代表真实模型的生成质量。
- 通过 `--model openai` 并配置环境变量 OPENAI_API_KEY（可选 OPENAI_BASE_URL、
  MODEL_NAME）可切换为真实的 OpenAI 兼容模型，由其自主做出 ReAct 决策。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request

MAX_STEPS = 8  # 执行步数上限，达到上限返回明确的未完成状态
CHARS_PER_SECOND = 5  # 语速估算：约 5 字/秒
MAX_REVISIONS = 2  # 超时/违规最多修正次数
REQUIRED_FIELDS = ["topic", "audience", "platform", "target_duration", "style"]

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "materials.json")


class ToolError(Exception):
    """工具执行失败（例如素材检索服务不可用）。"""


def load_db(path: str = DATA_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------- 业务工具（本地函数 / Mock） ----------

def tool_search_materials(query: str, db: dict, simulate_failure: bool = False) -> list[dict]:
    """素材检索：按关键词匹配素材库。"""
    if simulate_failure:
        raise ToolError("素材检索服务不可用（模拟故障）")
    return [m for m in db["materials"] if any(kw and kw in query for kw in m.get("keywords", []))]


def tool_estimate_duration(scenes: list[dict]) -> tuple[list[int], int]:
    """时长估算：按旁白字数 / 语速估算每个分镜秒数与总时长。"""
    per_scene = [max(1, math.ceil(len(s["narration"]) / CHARS_PER_SECOND)) for s in scenes]
    return per_scene, sum(per_scene)


def tool_check_rules(scenes: list[dict], db: dict) -> list[str]:
    """品牌规则检查：禁止素材中无依据的宣传表述，检查必需品牌元素。"""
    rules = db["brand_rules"]
    all_facts = [fact for m in db["materials"] for fact in m["facts"]]
    issues = []
    for i, s in enumerate(scenes):
        text = s["narration"]
        for bad in rules.get("forbidden_claims", []):
            if bad in text and not any(bad in fact for fact in all_facts):
                issues.append(f"分镜{i + 1} 含未经素材证实的表述「{bad}」")
        for req in rules.get("required_keywords", []):
            if req not in text:
                issues.append(f"分镜{i + 1} 缺少必需品牌元素「{req}」")
    return issues


def build_scenes(task: dict, materials: list[dict], revision_count: int) -> list[dict]:
    """生成/压缩脚本分镜。旁白仅引用素材事实，不添加无依据的效果承诺。"""
    scenes = []
    for m in materials[:3]:
        fact = m["facts"][0]
        if revision_count == 0:
            narration = (
                f"开场提问：还在为剪视频发愁吗？{m['product']}支持{fact}，"
                f"以{task['style']}风格呈现，专为{task['audience']}设计，"
                f"让小影陪你轻松完成每一条作品。"
            )
        elif revision_count == 1:
            narration = f"{m['product']}支持{fact}，小影出品，{task['style']}呈现。"
        else:
            narration = f"{m['product']}支持{fact}，小影出品。"
        scenes.append({
            "shot": f"展示{m['product']}「{fact}」功能界面，配{task['style']}风格字幕",
            "narration": narration,
            "material_ids": [m["id"]],
        })
    return scenes


# ---------- 动作执行 ----------

def execute_action(action: str, args: dict, task: dict, db: dict, state: dict) -> str:
    if action == "search":
        hits = tool_search_materials(args["query"], db, task.get("simulate_tool_failure", False))
        state["search_done"] = True
        state["rewritten"] = state["rewritten"] or args.get("is_rewrite", False)
        state["no_results"] = not hits
        state["materials"] = hits
        ids = [m["id"] for m in hits]
        return f"命中 {len(hits)} 条素材: {ids}" if hits else "未检索到相关素材"

    if action == "draft":
        state["scenes"] = build_scenes(task, state["materials"], state["revision_count"])
        state["needs_estimate"] = True
        return f"已生成 {len(state['scenes'])} 个分镜的初稿"

    if action == "estimate":
        per_scene, total = tool_estimate_duration(state["scenes"])
        state["estimate"] = total
        state["duration_ok"] = total <= int(task["target_duration"])
        state["needs_estimate"] = False
        return f"各分镜 {per_scene} 秒，总时长 {total} 秒（目标 {task['target_duration']} 秒）"

    if action == "revise":
        state["revision_count"] += 1
        state["scenes"] = build_scenes(task, state["materials"], state["revision_count"])
        state["needs_estimate"] = True
        state["rule_issues"] = None
        return f"第 {state['revision_count']} 次压缩/修正完成，需重新估算与检查"

    if action == "check_rules":
        issues = tool_check_rules(state["scenes"], db)
        state["rule_issues"] = issues
        state["needs_check"] = False
        return f"规则检查{'通过' if not issues else '未通过: ' + '；'.join(issues)}"

    raise ToolError(f"未知动作: {action}")


# ---------- 模型（决策方） ----------

class OfflineMockModel:
    """离线确定性 Mock 模型。

    注意：这不是真实大模型，只是用显式策略模拟「选择动作 → 观察结果 →
    调整下一步」的决策过程，用于离线验证流程。真实模型接入见 OpenAIModel。
    """

    def decide(self, task: dict, state: dict) -> dict:
        def R(action, rationale, args=None):
            return {"action": action, "args": args or {}, "rationale": rationale}

        if state["missing_fields"]:
            return R("finish", "缺少关键输入信息，向用户请求补充而非强行生成",
                     {"status": "needs_input"})
        if state["search_errors"] >= 2:
            return R("finish", "素材检索工具连续失败，重试无效，明确报告失败",
                     {"status": "failed_tool"})
        if not state["search_done"]:
            return R("search", "先检索与主题相关的素材，确保脚本有事实依据",
                     {"query": task["topic"], "is_rewrite": False})
        if state["no_results"] and not state["rewritten"]:
            return R("search", "首次检索无结果，改写查询（扩展同义描述）后再试一次",
                     {"query": f"{task['topic']} 功能 亮点", "is_rewrite": True})
        if state["no_results"] and state["rewritten"]:
            return R("finish", "改写查询后仍无素材，为避免编造产品事实而终止",
                     {"status": "failed_no_material"})
        if state["scenes"] is None:
            return R("draft", "素材充足，基于素材事实生成首版脚本")
        if state["needs_estimate"] or state["estimate"] is None:
            return R("estimate", "估算当前脚本总时长，核对是否满足时长限制")
        if not state["duration_ok"]:
            if state["revision_count"] >= MAX_REVISIONS:
                return R("finish", f"已压缩 {MAX_REVISIONS} 次仍超出目标时长，明确无法满足",
                         {"status": "failed_constraints"})
            return R("revise", "超出目标时长，压缩脚本后将重新估算")
        if state["needs_check"] or state["rule_issues"] is None:
            return R("check_rules", "时长达标，进行品牌规则检查")
        if state["rule_issues"]:
            if state["revision_count"] >= MAX_REVISIONS:
                return R("finish", "多次修正仍无法通过规则检查，明确失败",
                         {"status": "failed_constraints"})
            return R("revise", "规则检查未通过，去除无依据表述后重新检查")
        return R("finish", "时长与规则检查均通过，交付脚本", {"status": "success"})


class OpenAIModel:
    """真实模型接入（可选，OpenAI 兼容接口）。

    需要环境变量 OPENAI_API_KEY；OPENAI_BASE_URL 默认为 https://api.openai.com/v1，
    MODEL_NAME 默认为 gpt-4o-mini。要求模型输出 JSON：
    {"action": "search|draft|estimate|revise|check_rules|finish", "args": {...}, "rationale": "..."}
    """

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("使用 --model openai 需设置 OPENAI_API_KEY")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.environ.get("MODEL_NAME", "gpt-4o-mini")

    def decide(self, task: dict, state: dict) -> dict:
        public_state = {k: v for k, v in state.items() if k != "trace"}
        prompt = (
            "你是短视频脚本生成 Agent 的决策者。根据任务与当前状态，选择下一步动作。\n"
            "可选动作：search(args: query, is_rewrite)、draft、estimate、revise、"
            "check_rules、finish(args: status)。\n"
            "原则：先检索素材再写稿；检索无结果可改写查询重试一次；超出目标时长则压缩；"
            "只引用素材事实，不得编造；无法满足时 finish 并给出明确失败状态。\n"
            f"任务: {json.dumps(task, ensure_ascii=False)}\n"
            f"状态: {json.dumps(public_state, ensure_ascii=False, default=str)}\n"
            "只输出一行 JSON：{\"action\": ..., \"args\": {...}, \"rationale\": ...}"
        )
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps({
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            }).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = json.load(resp)["choices"][0]["message"]["content"]
        return json.loads(content[content.index("{"): content.rindex("}") + 1])


# ---------- Agent 主循环（选择动作 → 执行工具 → 观察 → 调整） ----------

def initial_state(task: dict) -> dict:
    return {
        "missing_fields": [f for f in REQUIRED_FIELDS if not task.get(f)],
        "search_done": False, "no_results": False, "rewritten": False,
        "search_errors": 0, "materials": [],
        "scenes": None, "revision_count": 0,
        "needs_estimate": False, "estimate": None, "duration_ok": False,
        "needs_check": False, "rule_issues": None, "status": None,
    }


def run_agent(task: dict, db: dict, model=None, max_steps: int = MAX_STEPS) -> dict:
    model = model or OfflineMockModel()
    state = initial_state(task)
    trace = []

    for step in range(1, max_steps + 1):
        decision = model.decide(task, state)
        action, args = decision.get("action"), decision.get("args", {})
        rationale = decision.get("rationale", "")
        if action == "finish":
            state["status"] = args.get("status", "success")
            trace.append({"step": step, "action": "finish", "args": args,
                          "observation": f"结束，状态 {state['status']}", "rationale": rationale})
            break
        try:
            observation = execute_action(action, args, task, db, state)
        except ToolError as e:
            observation = f"工具错误: {e}"
            state["search_errors"] += 1
        trace.append({"step": step, "action": action, "args": args,
                      "observation": observation, "rationale": rationale})
    else:
        state["status"] = "unfinished_step_limit"

    return build_output(task, state, trace)


def build_risks(task: dict, state: dict) -> list[str]:
    status = state["status"]
    if status == "success":
        return ["时长为按语速（约5字/秒）的估算值，实际以成片为准",
                "脚本仅引用素材库中的产品事实，未添加无依据的效果承诺"]
    if status == "needs_input":
        return ["缺少关键输入，请补充后重新提交"]
    if status == "failed_no_material":
        return ["素材库中没有相关事实，为避免编造产品事实而终止生成"]
    if status == "failed_tool":
        return ["素材检索服务不可用，已重试一次仍失败"]
    if status == "failed_constraints":
        return ["多次修正后仍无法满足时长或品牌规则约束"]
    return ["达到执行步数上限，任务未完成"]


def build_output(task: dict, state: dict, trace: list[dict]) -> dict:
    scenes = state["scenes"] or []
    per_scene, total = tool_estimate_duration(scenes) if scenes else ([], None)
    title = None
    if state["status"] == "success":
        title = f"{task['topic']}｜{task['platform']} {task['style']}风短视频脚本"
    return {
        "task_id": task.get("task_id"),
        "status": state["status"],
        "title": title,
        "target_duration": task.get("target_duration"),
        "scenes": scenes,
        "per_scene_seconds": per_scene,
        "total_seconds": total,
        "material_ids": sorted({mid for s in scenes for mid in s["material_ids"]}),
        "missing_fields": state["missing_fields"],
        "risks": build_risks(task, state),
        "trace": trace,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="短视频脚本生成 Agent")
    parser.add_argument("--input", required=True, help="任务输入 JSON 文件路径")
    parser.add_argument("--model", default="mock", choices=["mock", "openai"],
                        help="mock=离线确定性决策（默认）；openai=真实模型，需 OPENAI_API_KEY")
    args = parser.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            task = json.load(f)
        if not isinstance(task, dict):
            raise ValueError("输入须为 JSON 对象")
    except (OSError, json.JSONDecodeError, ValueError) as e:
        print(f"输入格式错误: {e}", file=sys.stderr)
        return 2

    model = OfflineMockModel() if args.model == "mock" else OpenAIModel()
    output = run_agent(task, load_db(), model)
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
