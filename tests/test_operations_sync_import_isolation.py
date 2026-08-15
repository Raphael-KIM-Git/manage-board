import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class OperationsSyncImportIsolationTests(unittest.TestCase):
    def test_import_executes_server_from_the_active_checkout(self):
        source_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary_directory:
            checkout = Path(temporary_directory)
            shutil.copy2(source_root / "operations_sync.py", checkout / "operations_sync.py")
            # operations_sync 가 임포트 시점에 요구하는 형제 모듈
            shutil.copy2(source_root / "artifact_contract.py", checkout / "artifact_contract.py")
            (checkout / "operations_dashboard_server.py").write_text(
                "from pathlib import Path\n"
                "Path('local-server-imported.txt').write_text(__file__, encoding='utf-8')\n",
                encoding="utf-8",
            )

            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(checkout)
            result = subprocess.run(
                [sys.executable, "-c", "import operations_sync"],
                cwd=checkout,
                env=environment,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (checkout / "local-server-imported.txt").read_text(encoding="utf-8"),
                str(checkout / "operations_dashboard_server.py"),
            )


if __name__ == "__main__":
    unittest.main()
