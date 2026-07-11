"""Tests for the optional OpenAI-compatible remote LLM gateway."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    status_code = 200
    response_body: dict = {
        "choices": [{"message": {"content": "连接测试成功"}}],
    }

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8") or "{}")
        self.__class__.requests.append({
            "path": self.path,
            "authorization": self.headers.get("Authorization", ""),
            "payload": payload,
        })
        body = json.dumps(self.__class__.response_body, ensure_ascii=False).encode("utf-8")
        self.send_response(self.__class__.status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


class RemoteLlmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["APPDATA"] = cls._tmp.name

        global remote_llm
        import remote_llm

        cls.remote_llm = remote_llm
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAIHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.api_base = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()
        cls._tmp.cleanup()

    def setUp(self) -> None:
        FakeOpenAIHandler.requests.clear()
        FakeOpenAIHandler.status_code = 200
        FakeOpenAIHandler.response_body = {
            "choices": [{"message": {"content": "远程模型回复"}}],
        }
        config_path = Path(self.remote_llm.REMOTE_LLM_CONFIG_FILE)
        if config_path.exists():
            config_path.unlink()

    def ready_config(self) -> dict:
        return {
            "enabled": True,
            "api_base": self.api_base,
            "api_key": "sk-test-secret",
            "model": "fake-model",
            "temperature": 0.2,
            "max_tokens": 128,
            "timeout": 5,
            "system_prompt": "测试系统提示",
        }

    def test_call_remote_llm_sends_openai_compatible_request(self) -> None:
        reply = self.remote_llm.call_remote_llm(
            "你好",
            history=[("上一问", "上一答")],
            config=self.ready_config(),
        )

        self.assertEqual(reply, "远程模型回复")
        self.assertEqual(len(FakeOpenAIHandler.requests), 1)
        req = FakeOpenAIHandler.requests[0]
        self.assertEqual(req["path"], "/v1/chat/completions")
        self.assertEqual(req["authorization"], "Bearer sk-test-secret")
        payload = req["payload"]
        self.assertEqual(payload["model"], "fake-model")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["max_tokens"], 128)
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "测试系统提示"})
        self.assertEqual(payload["messages"][-1], {"role": "user", "content": "你好"})

    def test_connection_test_reports_success(self) -> None:
        result = self.remote_llm.test_remote_llm_connection(self.ready_config())

        self.assertTrue(result["ok"])
        self.assertIn("reply", result)
        self.assertIn("latency_ms", result)
        payload = FakeOpenAIHandler.requests[0]["payload"]
        self.assertLessEqual(payload["max_tokens"], 64)

    def test_http_error_is_reported_without_raising(self) -> None:
        FakeOpenAIHandler.status_code = 401
        FakeOpenAIHandler.response_body = {"error": {"message": "bad key"}}

        reply = self.remote_llm.call_remote_llm("你好", config=self.ready_config())

        self.assertIn("HTTP 401", reply)
        self.assertTrue(reply.startswith("[大模型接口请求失败"))

    def test_config_is_local_and_public_config_masks_key(self) -> None:
        saved = self.remote_llm.save_remote_llm_config(self.ready_config())
        loaded = self.remote_llm.load_remote_llm_config()
        public = self.remote_llm.public_remote_llm_config(loaded)

        self.assertTrue(saved["enabled"])
        self.assertEqual(loaded["api_key"], "sk-test-secret")
        self.assertTrue(public["configured"])
        self.assertNotEqual(public["api_key"], "sk-test-secret")
        self.assertTrue(str(self.remote_llm.REMOTE_LLM_CONFIG_FILE).startswith(self._tmp.name))


if __name__ == "__main__":
    unittest.main(verbosity=2)
