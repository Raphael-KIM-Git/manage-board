import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path('/home/raphael/myproject/ensure-agent-hub-services.sh')


class EnsureAgentHubServicesTests(unittest.TestCase):
    def test_restarts_dashboard_after_two_failed_health_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            calls = root / 'tmux-calls.log'

            tmux = bin_dir / 'tmux'
            tmux.write_text(
                '#!/usr/bin/env bash\n'
                'printf "%s\\n" "$*" >> "$FAKE_TMUX_CALLS"\n'
                'if [[ "$1" == "has-session" ]]; then exit 0; fi\n'
                'exit 0\n'
            )
            curl = bin_dir / 'curl'
            curl.write_text('#!/usr/bin/env bash\nexit 1\n')
            pm_start = root / 'pm-start.sh'
            pm_start.write_text('#!/usr/bin/env bash\nexit 0\n')
            tmux.chmod(0o755)
            curl.chmod(0o755)
            pm_start.chmod(0o755)

            env = os.environ.copy()
            env.update({
                'PATH': f'{bin_dir}:' + env['PATH'],
                'FAKE_TMUX_CALLS': str(calls),
                'DASHBOARD_HEALTH_FAILURES_FILE': str(root / 'failures'),
                'DASHBOARD_SUPERVISOR': '/bin/true',
                'HERMES_PM_START': str(pm_start),
            })

            subprocess.run(['bash', str(SCRIPT)], env=env, check=True, capture_output=True, text=True)
            first_calls = calls.read_text()
            self.assertNotIn('kill-session', first_calls)

            subprocess.run(['bash', str(SCRIPT)], env=env, check=True, capture_output=True, text=True)
            second_calls = calls.read_text()
            self.assertIn('kill-session -t agent-hub-dashboard', second_calls)
            self.assertIn('new-session -d -s agent-hub-dashboard', second_calls)


if __name__ == '__main__':
    unittest.main()
