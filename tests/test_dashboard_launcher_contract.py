import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "run_dashboard_tailscale.sh"


class DashboardLauncherContractTests(unittest.TestCase):
    def test_launcher_uses_script_directory_from_hostile_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            launcher = root / "run_dashboard_tailscale.sh"
            shutil.copy2(LAUNCHER, launcher)
            fake_python = bin_dir / "python3"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$PWD\" > \"$FAKE_PYTHON_PWD\"\n"
                "printf '%s\\n' \"$1\" >> \"$FAKE_PYTHON_ARGS\"\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            env["FAKE_PYTHON_PWD"] = str(root / "python-pwd")
            env["FAKE_PYTHON_ARGS"] = str(root / "python-args")

            result = subprocess.run(
                ["bash", str(launcher)],
                cwd="/tmp",
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "python-pwd").read_text().strip(), str(root))
            self.assertEqual(
                (root / "python-args").read_text().strip(),
                str(root / "operations_dashboard_server.py"),
            )

    def test_supervisor_runs_child_from_script_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            supervisor = root / "dashboard-supervisor.sh"
            shutil.copy2(ROOT / "dashboard-supervisor.sh", supervisor)
            child = root / "run_dashboard_tailscale.sh"
            child.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$PWD\" > \"$SUPERVISOR_CHILD_PWD\"\n",
                encoding="utf-8",
            )
            child.chmod(0o755)
            env = os.environ.copy()
            env["SUPERVISOR_CHILD_PWD"] = str(root / "child-pwd")

            process = subprocess.Popen(
                ["bash", str(supervisor)],
                cwd="/tmp",
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                for _ in range(50):
                    if (root / "child-pwd").exists():
                        break
                    process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
            finally:
                process.terminate()
                process.wait(timeout=5)

            self.assertEqual((root / "child-pwd").read_text().strip(), str(root))

    def test_launcher_defaults_to_loopback(self):
        text = LAUNCHER.read_text(encoding="utf-8")

        self.assertIn(
            'export OPS_DASHBOARD_HOST="${OPS_DASHBOARD_HOST:-127.0.0.1}"',
            text,
        )

    def test_non_loopback_override_fails_closed_before_listener_starts(self):
        env = os.environ.copy()
        env["OPS_DASHBOARD_HOST"] = "0.0.0.0"
        env["OPS_DASHBOARD_PORT"] = "0"

        result = subprocess.run(
            ["bash", str(LAUNCHER)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "operations dashboard follow-up listener must bind to loopback",
            result.stderr,
        )


if __name__ == "__main__":
    unittest.main()