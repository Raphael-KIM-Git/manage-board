import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import operations_dashboard_server as server
from operations_dashboard_console import project_console_snapshot


class PMAssistRunnerTests(unittest.TestCase):
    def test_hermes_bridge_uses_hermes_runtime_and_sanitized_envelope(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured.update(cmd=cmd, kwargs=kwargs)
            return 0, '{"reply":"ok"}', 'SECRET stderr'

        with patch.object(server, "run_command", side_effect=fake_run):
            result = server.pm_brief_assist_hermes({}, prompt="safe prompt")
        self.assertEqual(result, {"reply": "ok"})
        self.assertEqual(captured["cmd"][0], server.PM_HERMES_PYTHON)
        self.assertEqual(captured["cmd"][1], str(server.PM_HERMES_HELPER))
        self.assertEqual(captured["kwargs"]["input_text"], json.dumps(
            {"prompt": "safe prompt", "source": "dashboard-pm-assist"}, ensure_ascii=False
        ))
        self.assertFalse(captured["kwargs"]["env"].get("OPENAI_API_KEY"))

    def test_actual_hermes_runtime_bridge_has_no_sessiondb_or_provider_call(self):
        helper = Path(server.PM_HERMES_HELPER)
        with tempfile.TemporaryDirectory() as directory:
            # sitecustomize is loaded by the genuine Hermes interpreter before
            # the helper.  It imports the production run_agent module, guards
            # the real SessionDB, and mocks only the provider-facing conversation
            # execution.  This deliberately does not shadow run_agent.py.
            sitecustomize = Path(directory) / "sitecustomize.py"
            sitecustomize.write_text(
                "import sys\n"
                "from pathlib import Path\n"
                "hermes_root = Path('/home/raphael/.hermes/hermes-agent')\n"
                "sys.path.insert(0, str(hermes_root))\n"
                "import hermes_state\n"
                "import run_agent\n"
                "assert Path(run_agent.__file__).resolve() == hermes_root / 'run_agent.py'\n"
                "calls = []\n"
                "real_session_db = hermes_state.SessionDB\n"
                "class ExplodingSessionDB(real_session_db):\n"
                "    def __init__(self, *args, **kwargs):\n"
                "        calls.append('construct')\n"
                "        raise AssertionError('SessionDB must not be constructed')\n"
                "    def close(self):\n"
                "        calls.append('close')\n"
                "        raise AssertionError('SessionDB must not be closed')\n"
                "    def append_message(self, *args, **kwargs):\n"
                "        calls.append('append')\n"
                "        raise AssertionError('SessionDB must not be flushed')\n"
                "hermes_state.SessionDB = ExplodingSessionDB\n"
                "def no_provider_conversation(self, _prompt, *args, **kwargs):\n"
                "    assert self._session_db is None\n"
                "    assert self._persist_disabled is True\n"
                "    assert self._session_json_enabled is False\n"
                "    assert self._get_session_db_for_recall() is None\n"
                "    self._ensure_db_session()\n"
                "    self._flush_messages_to_session_db([{'role': 'user', 'content': 'safe'}])\n"
                "    assert calls == [], calls\n"
                "    return {'final_response': '{\\\"reply\\\":\\\"ok\\\"}'}\n"
                "run_agent.AIAgent.run_conversation = no_provider_conversation\n"
                "",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = directory
            env.pop("OPENAI_API_KEY", None)
            proc = subprocess.run(
                [server.PM_HERMES_PYTHON, str(helper)], input='{"prompt":"safe"}', text=True,
                capture_output=True, env=env, timeout=10,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {"reply": "ok"})
        self.assertNotIn("SessionDB", proc.stderr)

    def test_bridge_failure_and_timeout_circuit_fallback_are_sanitized(self):
        payload = {"message": "제목: 상태 점검", "draft": {}}
        server._pm_circuit_failures = 0
        server._pm_circuit_opened_at = 0.0
        with patch.object(server, "pm_brief_assist_hermes", side_effect=RuntimeError("SECRET stderr")):
            result = server.pm_brief_assist(payload)
        self.assertEqual(result["engine"], "heuristic-fallback")
        self.assertNotIn("SECRET", result["reply"])
        self.assertNotIn("claude", result["reply"].lower())
        server._pm_circuit_failures = 0
        server._pm_circuit_opened_at = 0.0

        with patch.object(server, "pm_brief_assist_hermes", side_effect=TimeoutError("timeout")) as runner:
            for _ in range(server.PM_CIRCUIT_FAILURE_LIMIT):
                server.pm_brief_assist(payload)
            server.pm_brief_assist(payload)
        self.assertEqual(runner.call_count, server.PM_CIRCUIT_FAILURE_LIMIT)

    def test_no_legacy_claude_route_or_auth_config(self):
        source = Path(server.__file__).read_text(encoding="utf-8")
        self.assertNotIn("PM_CLAUDE_BIN", source)
        self.assertNotIn("claude -p", source)
        self.assertNotIn("shell=True", source)


class AgentMetadataTests(unittest.TestCase):
    def test_profile_metadata_reads_only_safe_allowlist_and_omits_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.yaml").write_text("description: PM\nmodel: gpt-5.6-terra\nprovider: openai-codex\ntoken: SECRET\nbase_url: https://secret\n", encoding="utf-8")
            metadata = server.safe_profile_metadata(root)
            self.assertEqual(metadata, {"model": "gpt-5.6-terra", "provider": "openai-codex"})

    def test_profile_metadata_reads_nested_hermes_model_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.yaml").write_text(
                "model:\n  default: gpt-5.6-luna\n  provider: openai-codex\n"
                "  base_url: https://secret\napi_key: SECRET\n",
                encoding="utf-8",
            )
            self.assertEqual(server.safe_profile_metadata(root), {"model": "gpt-5.6-luna", "provider": "openai-codex"})

    def test_profile_metadata_rejects_malformed_or_sensitive_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.yaml").write_text(
                "model:\n  default: ../../secret\n  provider: openai codex\n"
                "token: SECRET\nbase_url: https://secret\n",
                encoding="utf-8",
            )
            self.assertEqual(server.safe_profile_metadata(root), {})

    def test_profile_metadata_rejects_nested_model_decoys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.yaml").write_text(
                "model:\n  routing:\n    default: gpt-5.6-terra\n    provider: openai-codex\n",
                encoding="utf-8",
            )
            self.assertEqual(server.safe_profile_metadata(root), {})

    def test_profile_metadata_ignores_indented_declarations_later_in_the_file(self):
        """Real Hermes profiles declare the active model at the top, then reuse
        `model:`/`provider:` keys inside unrelated nested blocks. Only the
        top-level declaration may win."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.yaml").write_text(
                "model:\n  default: gpt-5.6-terra\n  provider: openai-codex\n"
                "  base_url: https://chatgpt.com/backend-api/codex\n"
                "fallback_providers: []\n"
                "browser:\n  provider: local\n"
                "x_search:\n  model: grok-4.20-reasoning\n  timeout_seconds: 180\n",
                encoding="utf-8",
            )
            self.assertEqual(
                server.safe_profile_metadata(root),
                {"model": "gpt-5.6-terra", "provider": "openai-codex"},
            )

    def test_local_profile_registry_exposes_safe_labels_for_configured_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configs = {
                "pm": "gpt-5.6-terra",
                "developer": "gpt-5.6-luna",
                "qa": "gpt-5.6-luna",
            }
            for slug, model in configs.items():
                profile = root / slug
                profile.mkdir()
                (profile / "profile.yaml").write_text(f"description: {slug}\n", encoding="utf-8")
                (profile / "config.yaml").write_text(
                    f"model:\n  default: {model}\n  provider: openai-codex\n",
                    encoding="utf-8",
                )
            with patch.object(server, "PROFILES_DIR", root):
                registry = server.profile_agent_map()
            self.assertEqual(registry["HermesPM"]["model"], "gpt-5.6-terra")
            self.assertEqual(registry["HermesDeveloper"]["provider"], "openai-codex")
            self.assertEqual(registry["HermesQA"]["model"], "gpt-5.6-luna")

    def test_console_agent_rows_include_metadata_without_inventing_execution_state(self):
        snapshot = project_console_snapshot(
            [], agent_registry={"HermesPM": "configured"}, local_profile_agents={"HermesPM"},
            agent_metadata={"HermesPM": {"model": "gpt-5.6-terra", "provider": "openai-codex"}},
        )
        row = snapshot["panes"]["agents"]["items"][0]
        self.assertEqual(row["model"], "gpt-5.6-terra")
        self.assertEqual(row["provider"], "openai-codex")
        self.assertEqual(row["execution_state"], "idle")

    def test_console_agent_rows_drop_untrusted_metadata_shapes(self):
        snapshot = project_console_snapshot(
            [], agent_registry={"remote-worker": "configured", "HermesQA": "configured"},
            local_profile_agents={"HermesQA"},
            agent_metadata={
                "remote-worker": {"model": "gpt-5.6-terra"},
                "HermesQA": {"model": "<script>", "provider": "openai-codex", "token": "SECRET"},
            },
        )
        rows = {row["agent_id"]: row for row in snapshot["panes"]["agents"]["items"]}
        self.assertNotIn("model", rows["remote-worker"])
        self.assertNotIn("model", rows["HermesQA"])
        self.assertEqual(rows["HermesQA"]["provider"], "openai-codex")
        self.assertNotIn("token", rows["HermesQA"])


if __name__ == "__main__":
    unittest.main()
