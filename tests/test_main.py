"""短视频脚本生成 Agent 的自动化测试。

运行：python -m unittest discover -s tests -v
覆盖：正常生成（超时修正）、缺关键信息、无素材（改写查询后失败）、
工具失败（重试后明确失败）、步数上限、CLI 非法输入退出码。
"""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import OfflineMockModel, load_db, run_agent  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(BASE, "examples")


def load_input(name):
    with open(os.path.join(EXAMPLES, f"{name}.input.json"), encoding="utf-8") as f:
        return json.load(f)


def actions(output):
    return [t["action"] for t in output["trace"]]


class AgentFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = load_db()

    def test_normal_success_with_duration_fix(self):
        out = run_agent(load_input("normal"), self.db)
        self.assertEqual(out["status"], "success")
        self.assertLessEqual(out["total_seconds"], out["target_duration"])
        # 首稿超时被估算发现后，模型决定压缩并重新估算
        self.assertEqual(actions(out),
                         ["search", "draft", "estimate", "revise", "estimate", "check_rules", "finish"])
        first_estimate = out["trace"][2]["observation"]
        self.assertIn("45 秒", first_estimate)  # 首稿 45 秒 > 目标 30 秒
        self.assertIn("P01", out["material_ids"])
        for scene in out["scenes"]:
            self.assertTrue(scene["material_ids"], "每个分镜都必须可追溯到素材 ID")
        # 不得编造素材中没有的效果承诺
        for scene in out["scenes"]:
            self.assertNotIn("效率提升", scene["narration"])

    def test_missing_info_requests_input(self):
        out = run_agent(load_input("missing"), self.db)
        self.assertEqual(out["status"], "needs_input")
        self.assertEqual(sorted(out["missing_fields"]), ["audience", "target_duration", "topic"])
        self.assertEqual(actions(out), ["finish"])

    def test_no_material_rewrite_then_fail(self):
        out = run_agent(load_input("no-material"), self.db)
        self.assertEqual(out["status"], "failed_no_material")
        searches = [t for t in out["trace"] if t["action"] == "search"]
        self.assertEqual(len(searches), 2, "首次无结果后应改写查询重试一次")
        self.assertFalse(searches[0]["args"]["is_rewrite"])
        self.assertTrue(searches[1]["args"]["is_rewrite"])
        self.assertNotEqual(searches[0]["args"]["query"], searches[1]["args"]["query"])
        self.assertEqual(out["scenes"], [], "无素材时不得输出脚本")

    def test_tool_failure_retried_then_failed(self):
        out = run_agent(load_input("tool-failure"), self.db)
        self.assertEqual(out["status"], "failed_tool")
        searches = [t for t in out["trace"] if t["action"] == "search"]
        self.assertEqual(len(searches), 2, "工具失败后应重试一次再放弃")
        self.assertTrue(all("工具错误" in t["observation"] for t in searches))

    def test_step_limit_returns_unfinished(self):
        out = run_agent(load_input("normal"), self.db, max_steps=3)
        self.assertEqual(out["status"], "unfinished_step_limit")
        self.assertEqual(len(out["trace"]), 3)

    def test_cli_invalid_json_exits_nonzero(self):
        bad = os.path.join(EXAMPLES, "_bad.input.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("{not json")
        try:
            env = dict(os.environ, PYTHONUTF8="1")
            proc = subprocess.run(
                [sys.executable, os.path.join("src", "main.py"), "--input", bad],
                cwd=BASE, capture_output=True, env=env)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("输入格式错误", proc.stderr.decode("utf-8"))
        finally:
            os.remove(bad)


if __name__ == "__main__":
    unittest.main()
