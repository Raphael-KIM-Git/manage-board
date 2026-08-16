import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "run_dashboard_tailscale.sh"


class DashboardLauncherContractTests(unittest.TestCase):
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