"""Verified algorithm curriculum for training the local Tiny LLM."""

from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path
from typing import Any

from _paths import data_dir, module_root


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
CURRICULUM_DIR = DATA_DIR / "algorithm_curriculum"
DATASET_FILE = CURRICULUM_DIR / "verified_algorithm_training.jsonl"
VERIFICATION_CACHE_FILE = CURRICULUM_DIR / "verification_cache.json"


COURSE: list[dict[str, Any]] = [
    {
        "title": "Two Sum",
        "topic": "哈希表",
        "prompt": "给定整数数组和目标值，返回两个和为目标值的下标。",
        "plan": "从左到右扫描，用哈希表记录已见数字的下标；当前位置需要的补数已出现时立即返回。时间 O(n)，空间 O(n)。",
        "method": "twoSum",
        "code": """class Solution:\n    def twoSum(self, nums, target):\n        seen = {}\n        for index, value in enumerate(nums):\n            need = target - value\n            if need in seen:\n                return [seen[need], index]\n            seen[value] = index\n        return []\n""",
        "tests": [(([2, 7, 11, 15], 9), [0, 1]), (([3, 2, 4], 6), [1, 2])],
    },
    {
        "title": "Longest Substring Without Repeating Characters",
        "topic": "滑动窗口",
        "prompt": "返回不含重复字符的最长子串长度。",
        "plan": "维护窗口左端和每个字符的最后位置；重复字符落在窗口内时移动左端。时间 O(n)，空间 O(k)。",
        "method": "lengthOfLongestSubstring",
        "code": """class Solution:\n    def lengthOfLongestSubstring(self, s):\n        last = {}\n        left = best = 0\n        for right, char in enumerate(s):\n            if char in last and last[char] >= left:\n                left = last[char] + 1\n            last[char] = right\n            best = max(best, right - left + 1)\n        return best\n""",
        "tests": [(("abcabcbb",), 3), (("bbbbb",), 1), (("",), 0)],
    },
    {
        "title": "Balanced Binary Tree",
        "topic": "树与后序遍历",
        "prompt": "判断二叉树是否高度平衡。",
        "plan": "后序递归同时计算高度；任一子树失衡就返回 -1 向上传播，避免重复计算高度。时间 O(n)，空间 O(h)。",
        "method": "isBalanced",
        "code": """class Solution:\n    def isBalanced(self, root):\n        def height(node):\n            if node is None:\n                return 0\n            left = height(node.left)\n            if left < 0:\n                return -1\n            right = height(node.right)\n            if right < 0 or abs(left - right) > 1:\n                return -1\n            return max(left, right) + 1\n        return height(root) >= 0\n""",
        "tests": [(([3, 9, 20, None, None, 15, 7],), True), (([1, 2, 2, 3, 3, None, None, 4, 4],), False)],
    },
    {
        "title": "Two Sum (C#)",
        "topic": "哈希表",
        "language": "csharp",
        "prompt": "给定整数数组和目标值，返回两个和为目标值的下标。",
        "plan": "使用 Dictionary 保存已见数字的位置；扫描到当前数字时查询补数。时间 O(n)，空间 O(n)。",
        "method": "TwoSum",
        "code": """using System;\nusing System.Collections.Generic;\npublic class Solution {\n    public int[] TwoSum(int[] nums, int target) {\n        var seen = new Dictionary<int, int>();\n        for (int i = 0; i < nums.Length; i++) {\n            int need = target - nums[i];\n            if (seen.TryGetValue(need, out int index)) return new[] { index, i };\n            seen[nums[i]] = i;\n        }\n        return Array.Empty<int>();\n    }\n}\npublic class Program {\n    static void Main() {\n        var answer = new Solution().TwoSum(new[] { 2, 7, 11, 15 }, 9);\n        if (answer.Length != 2 || answer[0] != 0 || answer[1] != 1) throw new Exception(\"test failed\");\n    }\n}\n""",
        "tests": [(([2, 7, 11, 15], 9), [0, 1])],
    },
    {
        "title": "Two Sum (C++)",
        "topic": "哈希表",
        "language": "cpp",
        "prompt": "给定整数数组和目标值，返回两个和为目标值的下标。",
        "plan": "使用 unordered_map 保存已见数字的位置；扫描到当前数字时查询补数。时间 O(n)，空间 O(n)。",
        "method": "twoSum",
        "code": """#include <stdexcept>\n#include <unordered_map>\n#include <vector>\nusing namespace std;\nclass Solution {\npublic:\n    vector<int> twoSum(vector<int>& nums, int target) {\n        unordered_map<int, int> seen;\n        for (int i = 0; i < static_cast<int>(nums.size()); ++i) {\n            int need = target - nums[i];\n            auto it = seen.find(need);\n            if (it != seen.end()) return {it->second, i};\n            seen[nums[i]] = i;\n        }\n        return {};\n    }\n};\nint main() {\n    vector<int> nums{2, 7, 11, 15};\n    vector<int> answer = Solution().twoSum(nums, 9);\n    if (answer.size() != 2 || answer[0] != 0 || answer[1] != 1) throw runtime_error(\"test failed\");\n    return 0;\n}\n""",
        "tests": [(([2, 7, 11, 15], 9), [0, 1])],
    },
]


def _toolchain_signature(language: str) -> str:
    if language == "csharp":
        paths = [shutil.which("dotnet") or "", shutil.which("csc") or ""]
    elif language == "cpp":
        paths = [shutil.which("g++") or "", shutil.which("clang++") or "", shutil.which("cl") or ""]
    else:
        paths = [shutil.which("python") or ""]
    return "|".join(paths)


def _sample_cache_key(sample: dict[str, Any]) -> str:
    language = str(sample.get("language") or "python")
    content = "\n".join((language, str(sample.get("title") or ""), str(sample.get("code") or ""), _toolchain_signature(language)))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_verification_cache() -> dict[str, bool]:
    try:
        payload = json.loads(VERIFICATION_CACHE_FILE.read_text(encoding="utf-8"))
        # Only persist passes. A failed run may simply mean that a compiler was
        # installed after the last check, and must not hide a newly ready course.
        return {str(key): True for key, value in payload.items() if value is True} if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_verification_cache(cache: dict[str, bool]) -> None:
    try:
        CURRICULUM_DIR.mkdir(parents=True, exist_ok=True)
        VERIFICATION_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _verify_sample(sample: dict[str, Any]) -> bool:
    language = str(sample.get("language") or "python")
    if language in {"cpp", "csharp"}:
        try:
            from code_lab import run_code
            return bool(run_code(language, sample["code"]).get("ok"))
        except Exception:
            return False

    class Node:
        def __init__(self, value: object) -> None:
            self.val = value
            self.left = None
            self.right = None

    def build_tree(values: list[object]):
        if not values or values[0] is None:
            return None
        nodes = [Node(value) if value is not None else None for value in values]
        child = 1
        for node in nodes:
            if node is None:
                continue
            if child < len(nodes):
                node.left = nodes[child]
                child += 1
            if child < len(nodes):
                node.right = nodes[child]
                child += 1
        return nodes[0]

    namespace: dict[str, Any] = {}
    try:
        exec(sample["code"], namespace)
        solver = namespace["Solution"]()
        method = getattr(solver, sample["method"])
        tests = sample.get("tests", [])
        if not tests:
            return False
        for args, expected in tests:
            if sample["method"] == "isBalanced":
                args = (build_tree(args[0]),)
            if method(*args) != expected:
                return False
        return True
    except Exception:
        return False


def verified_samples() -> list[dict[str, Any]]:
    cache = _load_verification_cache()
    changed = False
    verified: list[dict[str, Any]] = []
    for sample in COURSE:
        key = _sample_cache_key(sample)
        if key not in cache:
            if _verify_sample(sample):
                cache[key] = True
                changed = True
        if cache.get(key):
            verified.append(sample)
    if changed:
        _save_verification_cache(cache)
    return verified


def build_training_texts() -> list[str]:
    texts = []
    for sample in verified_samples():
        language = str(sample.get("language") or "python")
        texts.append(
            f"用户：算法题：{sample['prompt']}\n"
            f"助手：解题计划：{sample['plan']}\n"
            f"{language} 代码：\n```{language}\n{sample['code'].strip()}\n```"
        )
    return texts


def export_curriculum_dataset() -> dict[str, Any]:
    texts = build_training_texts()
    CURRICULUM_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATASET_FILE, "w", encoding="utf-8") as handle:
        for text in texts:
            handle.write(json.dumps({"text": text, "source": "verified_algorithm_curriculum"}, ensure_ascii=False) + "\n")
    return {"ok": True, "samples": len(texts), "path": str(DATASET_FILE)}


def train_algorithm_tiny_llm(epochs: int = 8) -> dict[str, Any]:
    texts = build_training_texts()
    if not texts:
        return {"ok": False, "error": "算法课程样本验证失败，未开始训练。"}
    export_curriculum_dataset()
    # PyTorch is intentionally not bundled in CompanionAI.exe. Training must
    # run in the managed component environment, never in the frozen launcher.
    from tiny_llm import train_tiny_llm_in_runtime
    return train_tiny_llm_in_runtime(
        texts=texts,
        epochs=max(1, min(int(epochs), 50)),
        batch_size=min(8, len(texts)),
        max_seq_len=256,
        config={"embed_dim": 192, "num_heads": 4, "num_layers": 3},
    )


def curriculum_status_text() -> str:
    verified = verified_samples()
    verified_languages: dict[str, int] = {}
    for sample in verified:
        language = str(sample.get("language") or "python")
        verified_languages[language] = verified_languages.get(language, 0) + 1
    language_summary = "、".join(
        f"{label} {verified_languages.get(language, 0)} 题"
        for language, label in (("python", "Python"), ("csharp", "C#"), ("cpp", "C++"))
    )
    return (
        "算法课程组件：\n"
        f"  内置课程：{len(COURSE)} 题\n"
        f"  可验证样本：{len(verified)} 题\n"
        f"  分语言：{language_summary}\n"
        f"  训练集：{DATASET_FILE}\n\n"
        "命令：\n"
        "  /algorithm_curriculum_dataset 导出已验证训练集\n"
        "  /algorithm_curriculum_train 8 训练本地 Tiny LLM"
    )


def handle_algorithm_curriculum_command(message: str) -> str | None:
    if message in {"/algorithm_curriculum", "/algorithm_curriculum_status"}:
        return curriculum_status_text()
    if message == "/algorithm_curriculum_dataset":
        result = export_curriculum_dataset()
        return f"算法课程训练集已导出：{result['samples']} 条\n{result['path']}"
    if message == "/algorithm_curriculum_train" or message.startswith("/algorithm_curriculum_train "):
        parts = message.split()
        epochs = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 8
        result = train_algorithm_tiny_llm(epochs)
        if not result.get("ok"):
            return f"算法课程训练失败：{result.get('error', '未知错误')}"
        return f"算法课程训练完成：样本 {result.get('samples', len(build_training_texts()))}，loss {result.get('final_loss', result.get('loss', '?'))}"
    return None
