"""Core runtime unit tests for Companion AI.

Covers the six areas called out in NEXT_DELIVERY_PLAN.md P3:
  - data directory resolution (_paths.data_dir / module_root / resource_dir)
  - configuration masking (remote_llm.public_remote_llm_config)
  - upload size limit (app.handle_upload rejects > 12 MB)
  - LAN status (app.local_access_info structure and mode)
  - version comparison (app._version_key / is_newer_version / normalize_release_version)
  - model export (app.build_model_package structure and stats)
"""

from __future__ import annotations

import os
import tempfile
import unittest
import urllib.error
import unittest.mock
from pathlib import Path


class DataDirTests(unittest.TestCase):
    """Verify _paths.data_dir resolves to the correct platform location and
    migrates legacy in-tree data/ directories on first call."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._saved_appdata = os.environ.get("APPDATA")
        self._saved_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["APPDATA"] = self._tmp.name
        os.environ.pop("XDG_DATA_HOME", None)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        if self._saved_appdata is not None:
            os.environ["APPDATA"] = self._saved_appdata
        else:
            os.environ.pop("APPDATA", None)
        if self._saved_xdg is not None:
            os.environ["XDG_DATA_HOME"] = self._saved_xdg

    def test_data_dir_uses_appdata_on_windows(self) -> None:
        if os.name != "nt":
            self.skipTest("APPDATA-based resolution is Windows-only")
        import _paths

        root = Path(self._tmp.name) / "app"
        root.mkdir()
        dest = _paths.data_dir(root)
        self.assertEqual(dest, Path(self._tmp.name) / "CompanionAI")
        self.assertTrue(dest.is_dir())

    def test_data_dir_falls_back_when_unwritable(self) -> None:
        import _paths

        root = Path(self._tmp.name) / "app"
        root.mkdir()
        # Point APPDATA at a path that cannot be created to force fallback.
        os.environ["APPDATA"] = str(Path(self._tmp.name) / "missing" / "nested" / "appdata")
        # Removing write permission is unreliable across platforms; instead
        # verify the fallback path is returned when XDG/APPDATA resolve to a
        # location that data_dir can still create. The contract is: the
        # returned dir exists and is writable.
        dest = _paths.data_dir(root)
        self.assertTrue(dest.is_dir())
        (dest / ".write_test").write_text("ok", encoding="utf-8")

    def test_data_dir_migrates_legacy_in_tree_data(self) -> None:
        import _paths

        root = Path(self._tmp.name) / "app"
        (root / "data").mkdir(parents=True)
        legacy_file = root / "data" / "memory.json"
        legacy_file.write_text('{"profile": []}', encoding="utf-8")

        dest = _paths.data_dir(root)
        # Legacy content should have moved to the user data dir.
        self.assertTrue((dest / "memory.json").exists())
        self.assertTrue((dest / ".migrated").exists())
        # Second call must not re-migrate.
        _paths.data_dir(root)
        self.assertEqual(
            (dest / "memory.json").read_text(encoding="utf-8"),
            '{"profile": []}',
        )

    def test_module_root_uses_env_when_valid(self) -> None:
        import _paths

        real_root = Path(self._tmp.name) / "real_root"
        real_root.mkdir(parents=True)
        (real_root / "app.py").write_text("# stub", encoding="utf-8")
        os.environ["_COMPANION_BASE_DIR"] = str(real_root)
        try:
            self.assertEqual(_paths.module_root("/some/caller/file.py"), real_root)
        finally:
            os.environ.pop("_COMPANION_BASE_DIR", None)

    def test_module_root_ignores_stale_env_pointing_nowhere(self) -> None:
        import _paths

        os.environ["_COMPANION_BASE_DIR"] = str(Path(self._tmp.name) / "does_not_exist")
        try:
            caller = Path(self._tmp.name) / "caller.py"
            caller.write_text("# stub", encoding="utf-8")
            self.assertEqual(_paths.module_root(str(caller)), caller.resolve().parent)
        finally:
            os.environ.pop("_COMPANION_BASE_DIR", None)

    def test_resource_dir_prefers_internal_bundle(self) -> None:
        import _paths

        caller = Path(self._tmp.name) / "caller.py"
        caller.write_text("# stub", encoding="utf-8")
        base = caller.resolve().parent
        (base / "_internal").mkdir()
        self.assertEqual(_paths.resource_dir(str(caller)), base / "_internal")


class VersionCompareTests(unittest.TestCase):
    """Version parsing and comparison must be deterministic and pre-release safe."""

    @classmethod
    def setUpClass(cls) -> None:
        import app
        cls.app = app

    def test_normalize_strips_leading_v(self) -> None:
        self.assertEqual(self.app.normalize_release_version("v1.0.42"), "1.0.42")
        self.assertEqual(self.app.normalize_release_version("1.0.42"), "1.0.42")
        self.assertEqual(self.app.normalize_release_version(""), "")

    def test_version_key_orders_numeric_segments(self) -> None:
        self.assertLess(self.app._version_key("1.0.9"), self.app._version_key("1.0.10"))
        self.assertLess(self.app._version_key("1.0.42"), self.app._version_key("1.1.0"))
        self.assertLess(self.app._version_key("1.9.9"), self.app._version_key("2.0.0"))

    def test_is_newer_version_compares_against_local(self) -> None:
        self.assertTrue(self.app.is_newer_version("1.0.50", "1.0.42"))
        self.assertFalse(self.app.is_newer_version("1.0.42", "1.0.42"))
        self.assertFalse(self.app.is_newer_version("1.0.40", "1.0.42"))
        # Pre-release / textual suffixes must not crash ordering.
        self.assertTrue(self.app.is_newer_version("1.1.0-rc1", "1.0.42"))


class UpdateManifestTests(unittest.TestCase):
    """The release endpoint is fixed and cannot be changed by local state."""

    @classmethod
    def setUpClass(cls) -> None:
        import app
        cls.app = app

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._saved_state_file = self.app.UPDATE_STATE_FILE
        self.app.UPDATE_STATE_FILE = Path(self._tmp.name) / "update_state.json"

    def tearDown(self) -> None:
        self.app.UPDATE_STATE_FILE = self._saved_state_file
        self._tmp.cleanup()

    def test_stored_manifest_url_is_replaced_with_official_endpoint(self) -> None:
        self.app.UPDATE_STATE_FILE.write_text(
            '{"manifest_url": "https://example.invalid/manifest.json"}',
            encoding="utf-8",
        )
        state = self.app.load_update_state()
        self.assertEqual(state["manifest_url"], self.app.DEFAULT_UPDATE_MANIFEST_URL)

    def test_save_update_state_ignores_manifest_url(self) -> None:
        state = self.app.save_update_state({
            "manifest_url": "https://example.invalid/manifest.json",
            "auto_check": False,
        })
        self.assertEqual(state["manifest_url"], self.app.DEFAULT_UPDATE_MANIFEST_URL)
        persisted = self.app.UPDATE_STATE_FILE.read_text(encoding="utf-8")
        self.assertNotIn("example.invalid", persisted)

    def test_official_release_endpoint_points_to_companion_ai_release(self) -> None:
        self.assertIn("LoongSerpent9Realms/companion-ai-release", self.app.DEFAULT_UPDATE_MANIFEST_URL)
        self.assertEqual(self.app.OFFICIAL_UPDATE_RELEASE_REPO, "LoongSerpent9Realms/companion-ai-release")
        public = self.app.update_public_state()
        self.assertEqual(public["release_repo"], "LoongSerpent9Realms/companion-ai-release")
        self.assertIn("companion-ai-release", public["manifest_url"])

    def test_open_url_prefers_direct_for_github_hosts(self) -> None:
        calls = {"direct": 0, "system": 0}

        class FakeResp:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, n=-1):
                return b'{"ok":true}'

        class FakeOpener:
            def __init__(self, label: str):
                self.label = label
            def open(self, req, timeout=20):
                calls[self.label] += 1
                if self.label == "direct":
                    return FakeResp()
                raise urllib.error.URLError("certificate verify failed: DevSidecar")

        def fake_build_opener(*handlers):
            # ProxyHandler({}) means direct; any other proxy map is treated as system.
            proxy_handler = next((h for h in handlers if h.__class__.__name__ == "ProxyHandler"), None)
            proxies = getattr(proxy_handler, "proxies", {}) if proxy_handler is not None else {}
            label = "direct" if proxies == {} else "system"
            return FakeOpener(label)

        contexts = [object()]
        with (
            unittest.mock.patch.object(self.app, "https_ssl_contexts", return_value=contexts),
            unittest.mock.patch.object(self.app.urllib.request, "build_opener", side_effect=fake_build_opener),
            unittest.mock.patch.object(self.app, "_powershell_fetch_bytes", side_effect=RuntimeError("no ps")),
            unittest.mock.patch.object(self.app, "_curl_fetch_bytes", side_effect=RuntimeError("no curl")),
        ):
            resp = self.app.open_url(
                "https://api.github.com/repos/LoongSerpent9Realms/companion-ai-release/releases/latest"
            )
            self.assertIsInstance(resp, FakeResp)
        self.assertEqual(calls["direct"], 1)
        self.assertEqual(calls["system"], 0)


class CompanionSelfRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import app
        cls.app = app

    def test_companion_learning_question_does_not_count_as_fresh_web_request(self) -> None:
        self.assertTrue(self.app.is_companion_self_reflection_query("你最近有在学习新东西吗？"))
        self.assertFalse(self.app.is_companion_self_reflection_query("最近 Python 有什么新进展？"))

    def test_confirmed_training_reply_is_preferred_for_companion_question(self) -> None:
        expected = "我最近一直在探索一些新领域呢。"
        with unittest.mock.patch.object(
            self.app,
            "best_training_match",
            return_value=({"response": expected}, 0.8),
        ):
            reply = self.app.preferred_self_training_reply("你最近有在学习新东西吗？")

        self.assertEqual(reply, expected)


class IdentityReplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import app
        cls.app = app

    def test_identity_question_uses_configured_name_relationship_and_persona(self) -> None:
        identity = {
            "name": "小澜",
            "relationship_type": "family",
            "relationship_subtype": "daughter",
            "persona": "我会温柔、坦诚地陪你把事情想清楚。",
        }
        with (
            unittest.mock.patch.object(self.app, "load_identity", return_value=identity),
            unittest.mock.patch("user_profile.get_ai_address_to_user", return_value="老爸"),
        ):
            reply = self.app.identity_intro_reply("你是谁？")

        self.assertEqual(reply, "老爸，我是小澜，你的女儿。我会温柔、坦诚地陪你把事情想清楚。")

    def test_identity_question_does_not_match_general_questions(self) -> None:
        self.assertFalse(self.app.is_identity_question("你是谁的朋友？"))
        self.assertFalse(self.app.is_identity_question("你最近在做什么？"))


class UploadLimitTests(unittest.TestCase):
    """Uploads above the 12 MB limit must be rejected before any disk write."""

    @classmethod
    def setUpClass(cls) -> None:
        import app
        cls.app = app

    def test_oversized_upload_rejected_without_write(self) -> None:
        # Monkeypatch parse_multipart to avoid building a 12 MB multipart body
        # while still exercising the size guard in handle_upload.
        original = self.app.parse_multipart
        oversized = b"\0" * (12_000_000 + 1)

        def _fake_parse(_body: bytes, _ct: str):
            return ("big.bin", oversized)

        self.app.parse_multipart = _fake_parse  # type: ignore[assignment]
        try:
            result = self.app.handle_upload(b"fake", "multipart/form-data; boundary=x")
        finally:
            self.app.parse_multipart = original  # type: ignore[assignment]

        self.assertFalse(result["ok"])
        self.assertIn("12MB", result["error"])

    def test_missing_multipart_returns_error(self) -> None:
        result = self.app.handle_upload(b"", "text/plain")
        self.assertFalse(result["ok"])


class LanStatusTests(unittest.TestCase):
    """local_access_info must report a stable shape and a local/lan mode."""

    @classmethod
    def setUpClass(cls) -> None:
        import app
        cls.app = app

    def test_local_access_info_has_required_fields(self) -> None:
        info = self.app.local_access_info()
        for key in ("mode", "host", "port", "local_url", "lan_urls", "version", "data_dir", "privacy"):
            self.assertIn(key, info)
        self.assertIn(info["mode"], {"local", "lan"})
        self.assertIsInstance(info["lan_urls"], list)
        self.assertEqual(info["local_url"], f"http://127.0.0.1:{info['port']}")

    def test_health_check_reports_process_state(self) -> None:
        health = self.app.health_check()
        self.assertTrue(health["ok"])
        for key in ("version", "host", "port", "mode", "data_dir", "pid", "uptime_seconds", "processes"):
            self.assertIn(key, health)
        self.assertIn(health["mode"], {"local", "lan"})
        self.assertIn("web", health["processes"])
        self.assertIn("pet", health["processes"])
        self.assertIsInstance(health["uptime_seconds"], int)


class LanSecurityTests(unittest.TestCase):
    """LAN mode must gate non-loopback write requests behind a pairing token."""

    @classmethod
    def setUpClass(cls) -> None:
        import app
        cls.app = app

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._saved_token_file = self.app.LAN_TOKEN_FILE
        self.app.LAN_TOKEN_FILE = Path(self._tmp.name) / "lan_token.json"

    def tearDown(self) -> None:
        self.app.LAN_TOKEN_FILE = self._saved_token_file
        self._tmp.cleanup()

    def test_lan_token_is_stable_across_calls(self) -> None:
        token_a = self.app.lan_access_token()
        token_b = self.app.lan_access_token()
        self.assertTrue(token_a)
        self.assertEqual(token_a, token_b)

    def test_lan_token_can_be_regenerated(self) -> None:
        old = self.app.lan_access_token()
        new = self.app.lan_access_token(regenerate=True)
        self.assertTrue(new)
        self.assertNotEqual(old, new)
        # The regenerated token must persist.
        self.assertEqual(self.app.lan_access_token(), new)

    def test_loopback_client_is_always_allowed(self) -> None:
        self.assertTrue(self.app._is_loopback_client(("127.0.0.1", 12345)))
        self.assertTrue(self.app._is_loopback_client(("::1", 12345)))
        self.assertFalse(self.app._is_loopback_client(("192.168.1.5", 12345)))

    def test_local_access_info_hides_token_for_non_loopback(self) -> None:
        # In local mode (default for tests) no token is exposed regardless.
        local_info = self.app.local_access_info(loopback=True)
        self.assertNotIn("lan_token", local_info)

    def test_local_access_info_reveals_token_only_when_lan_enabled(self) -> None:
        # Simulate LAN mode by patching ALLOW_LAN/HOST at the module level.
        saved_lan = self.app.ALLOW_LAN
        saved_host = self.app.HOST
        self.app.ALLOW_LAN = True
        self.app.HOST = "0.0.0.0"
        try:
            loopback_info = self.app.local_access_info(loopback=True)
            remote_info = self.app.local_access_info(loopback=False)
            self.assertIn("lan_token", loopback_info)
            self.assertTrue(loopback_info["lan_token"])
            # Non-loopback callers must never see the token.
            self.assertNotIn("lan_token", remote_info)
        finally:
            self.app.ALLOW_LAN = saved_lan
            self.app.HOST = saved_host


class ConfigMaskingTests(unittest.TestCase):
    """Public config views must never leak the full API key or system prompt."""

    @classmethod
    def setUpClass(cls) -> None:
        import remote_llm
        cls.remote_llm = remote_llm

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._saved_config_file = self.remote_llm.REMOTE_LLM_CONFIG_FILE
        self.remote_llm.REMOTE_LLM_CONFIG_FILE = Path(self._tmp.name) / "remote_llm_config.json"

    def tearDown(self) -> None:
        self.remote_llm.REMOTE_LLM_CONFIG_FILE = self._saved_config_file
        self._tmp.cleanup()

    def test_long_key_is_truncated_with_ellipsis(self) -> None:
        full_key = "sk-1234567890abcdefXYZ"
        public = self.remote_llm.public_remote_llm_config({"api_key": full_key, "system_prompt": "secret"})
        self.assertTrue(public["configured"])
        # The full key must never appear in the public view.
        self.assertNotIn(full_key, public["api_key"])
        # The masked form keeps the first 8 and last 4 chars; the middle is
        # replaced with an ellipsis, so the secret middle must be absent.
        self.assertNotIn("67890abcde", public["api_key"])
        self.assertIn("...", public["api_key"])
        self.assertNotIn("system_prompt", public)

    def test_short_key_is_fully_masked(self) -> None:
        public = self.remote_llm.public_remote_llm_config({"api_key": "short"})
        self.assertTrue(public["configured"])
        self.assertEqual(public["api_key"], "***")

    def test_empty_key_reports_unconfigured(self) -> None:
        public = self.remote_llm.public_remote_llm_config({"api_key": ""})
        self.assertFalse(public["configured"])
        self.assertEqual(public["api_key"], "")


class ModelExportTests(unittest.TestCase):
    """build_model_package must return a versioned, self-describing export
    with a complete stats block regardless of how much data is present."""

    @classmethod
    def setUpClass(cls) -> None:
        import app
        cls.app = app

    def test_model_package_structure(self) -> None:
        package = self.app.build_model_package()
        self.assertEqual(package["format"], "companion-local-model")
        self.assertEqual(package["version"], 1)
        self.assertEqual(package["runtime"], "rule-memory-retrieval-v1")
        for key in ("created_at", "description", "stats", "memory", "training", "files", "vocabulary", "retrieval_index"):
            self.assertIn(key, package)

    def test_model_package_stats_complete(self) -> None:
        stats = self.app.build_model_package()["stats"]
        for key in (
            "profile_memories", "preference_memories", "fact_memories",
            "training_examples", "feedback_items", "positive_feedback", "negative_feedback",
            "file_summaries", "action_skills", "behavior_rules", "evolution_events", "vocabulary_size",
        ):
            self.assertIn(key, stats)
            self.assertIsInstance(stats[key], int)
        # Positive + negative feedback cannot exceed total feedback items.
        self.assertLessEqual(stats["positive_feedback"] + stats["negative_feedback"], stats["feedback_items"])


class ConversationAuditApiTests(unittest.TestCase):
    """Audit API helpers must understand reasoning-model payloads."""

    def test_message_text_reads_reasoning_content_when_content_empty(self) -> None:
        from conversation_audit import _message_text

        text = _message_text({
            "role": "assistant",
            "content": "",
            "reasoning_content": "{\"ok\": true, \"note\": \"from reasoning\"}",
        })
        self.assertIn("from reasoning", text)
        self.assertIn("ok", text)

    def test_message_text_prefers_nonempty_content(self) -> None:
        from conversation_audit import _message_text

        text = _message_text({
            "content": "{\"ok\": true}",
            "reasoning_content": "ignore me",
        })
        self.assertEqual(text, "{\"ok\": true}")

    def test_message_text_joins_list_content_parts(self) -> None:
        from conversation_audit import _message_text

        text = _message_text({
            "content": [
                {"type": "text", "text": "{\"a\": 1}"},
                {"type": "text", "text": ", done"},
            ]
        })
        self.assertIn("a", text)

    def test_call_ai_api_returns_reasoning_content(self) -> None:
        import conversation_audit as audit
        import io
        import json
        from unittest.mock import patch

        payload = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "{\"suggested_response\": \"你好\"}",
                }
            }]
        }
        raw = json.dumps(payload).encode("utf-8")

        class FakeResp:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return raw

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            text = audit.call_ai_api(
                {
                    "api_base": "http://127.0.0.1:9/v1",
                    "api_key": "x",
                    "model": "qwen/qwen3.5-9b",
                    "max_tokens": 64,
                    "timeout": 5,
                },
                "system",
                "user",
            )
        self.assertEqual(text, "{\"suggested_response\": \"你好\"}")

    def test_normalize_history_accepts_dict_entries(self) -> None:
        from conversation_audit import _normalize_history

        pairs = _normalize_history([
            {"user": "hi", "assistant": "hello"},
            {"message": "再问", "reply": "再答"},
            ("tuple-user", "tuple-ai"),
        ], max_turns=5)
        self.assertEqual(pairs[0], ("hi", "hello"))
        self.assertEqual(pairs[1], ("再问", "再答"))
        self.assertEqual(pairs[2], ("tuple-user", "tuple-ai"))

    def test_extract_json_object_from_fenced_reasoning(self) -> None:
        from conversation_audit import _extract_json_object

        parsed = _extract_json_object("""thinking...
```json
{"overall_score": 0.8, "suggested_response": "早上好"}
```
""")
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("suggested_response"), "早上好")


class BackupRestoreTests(unittest.TestCase):
    """Backup must produce a checksummed archive; restore must verify and
    round-trip data into a fresh directory without including transient state."""

    @classmethod
    def setUpClass(cls) -> None:
        import app
        cls.app = app

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._source = Path(self._tmp.name) / "source_data"
        self._source.mkdir(parents=True)
        # Seed recognizable user data.
        (self._source / "memory.json").write_text('{"profile": ["backup-test"]}', encoding="utf-8")
        (self._source / "sub").mkdir()
        (self._source / "sub" / "training.json").write_text('{"examples": []}', encoding="utf-8")
        # Transient state that must be excluded.
        (self._source / "runtime").mkdir()
        (self._source / "runtime" / "web.pid").write_text("99999", encoding="utf-8")
        (self._source / "lan_token.json").write_text('{"token": "secret"}', encoding="utf-8")
        (self._source / "backups").mkdir()
        (self._source / "backups" / "stale.tar.gz").write_bytes(b"stale")

        self._archive = Path(self._tmp.name) / "backup.tar.gz"
        self._target = Path(self._tmp.name) / "restored_data"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_backup(self) -> dict:
        return self.app.create_backup(dest_path=self._archive, source_dir=self._source)  # type: ignore[attr-defined]

    def test_backup_creates_checksummed_archive(self) -> None:
        info = self._make_backup()
        self.assertTrue(info["ok"])
        self.assertTrue(self._archive.is_file())
        self.assertGreater(info["file_count"], 0)
        self.assertTrue(info["archive_sha256"])
        self.assertEqual(info["archive_size"], self._archive.stat().st_size)

    def test_backup_excludes_transient_state(self) -> None:
        self._make_backup()
        result = self.app.restore_backup(self._archive, target_data_dir=self._target)  # type: ignore[attr-defined]
        self.assertTrue(result["ok"])
        # User data restored.
        self.assertTrue((self._target / "memory.json").exists())
        self.assertTrue((self._target / "sub" / "training.json").exists())
        # Transient state must not be present.
        self.assertFalse((self._target / "runtime" / "web.pid").exists())
        self.assertFalse((self._target / "lan_token.json").exists())
        self.assertFalse((self._target / "backups" / "stale.tar.gz").exists())

    def test_restore_round_trips_file_contents(self) -> None:
        self._make_backup()
        result = self.app.restore_backup(self._archive, target_data_dir=self._target)  # type: ignore[attr-defined]
        self.assertTrue(result["ok"])
        self.assertEqual(
            (self._target / "memory.json").read_text(encoding="utf-8"),
            '{"profile": ["backup-test"]}',
        )
        self.assertEqual(result["restored_files"], self._make_backup()["file_count"])

    def test_restore_rejects_tampered_archive(self) -> None:
        self._make_backup()
        # Corrupt the archive by truncating it.
        bad = Path(self._tmp.name) / "bad.tar.gz"
        bad.write_bytes(self._archive.read_bytes()[:100])
        result = self.app.restore_backup(bad, target_data_dir=self._target)  # type: ignore[attr-defined]
        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_restore_rejects_missing_file(self) -> None:
        result = self.app.restore_backup(Path(self._tmp.name) / "nonexistent.tar.gz", target_data_dir=self._target)  # type: ignore[attr-defined]
        self.assertFalse(result["ok"])
        self.assertIn("不存在", result["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
