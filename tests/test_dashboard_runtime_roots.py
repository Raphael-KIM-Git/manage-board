import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import operations_dashboard_server as server


ROOT = Path('/home/raphael/myproject')
STATIC = ROOT / 'operations_dashboard'


class RuntimeRootsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'runtime'
        self.root.mkdir()
        self.static = Path(self.temp.name) / 'static'
        self.static.mkdir()
        for name in ('index.html', 'app.js', 'styles.css', 'detail.html'):
            (self.static / name).write_bytes((STATIC / name).read_bytes())

    def tearDown(self):
        self.temp.cleanup()
        server.configure_runtime(server.resolve_runtime_paths(), _allow_legacy_default=True)

    def test_default_mapping_is_pure(self):
        with mock.patch.object(Path, 'mkdir', side_effect=AssertionError('mkdir called')):
            with mock.patch.object(Path, 'write_text', side_effect=AssertionError('write called')):
                paths = server.resolve_runtime_paths(env={})
        self.assertEqual(paths.runtime_root, ROOT)
        self.assertEqual(paths.static_root, STATIC)

    def test_valid_isolated_paths_and_static_identity(self):
        paths = server.resolve_runtime_paths(injected={'runtime_root': self.root, 'static_root': self.static})
        self.assertTrue(paths.runtime_root.is_absolute())
        self.assertEqual(server.configure_runtime(paths).static_root, self.static)
        self.assertEqual(server.UI_DIR, self.static)
        self.assertEqual((server.UI_DIR / 'app.js').read_bytes(), (self.static / 'app.js').read_bytes())
        self.assertTrue(all(paths.runtime_root in directory.parents for directory in paths.operational_dirs))

    def test_initializer_alone_creates_layout_and_workers_config(self):
        paths = server.RuntimePaths(self.root, self.static)
        server.initialize_runtime(paths)
        self.assertTrue(all(directory.is_dir() for directory in paths.operational_dirs))
        self.assertEqual(json.loads(paths.workers_config_path.read_text()), server.DEFAULT_WORKERS)

    def test_paired_environment_initializes_isolated_runtime(self):
        with mock.patch.dict(os.environ, {
            'OPS_DASHBOARD_RUNTIME_ROOT': str(self.root),
            'OPS_DASHBOARD_STATIC_ROOT': str(self.static),
        }, clear=False):
            paths = server.initialize_runtime()
        self.assertEqual(paths.runtime_root, self.root)
        self.assertEqual(paths.static_root, self.static)
        self.assertTrue(all(directory.is_dir() for directory in paths.operational_dirs))
        self.assertEqual(json.loads(paths.workers_config_path.read_text()), server.DEFAULT_WORKERS)

    def test_partial_environment_rejected(self):
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(env={'OPS_DASHBOARD_RUNTIME_ROOT': str(self.root)})
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(env={'OPS_DASHBOARD_STATIC_ROOT': str(self.static)})

    def test_relative_paths_rejected(self):
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(injected={'runtime_root': 'relative', 'static_root': self.static})
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(injected={'runtime_root': self.root, 'static_root': 'relative'})

    def test_missing_and_invalid_roots_rejected(self):
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(injected={'runtime_root': self.root / 'missing', 'static_root': self.static})
        file_path = self.root / 'file'
        file_path.write_text('not a directory')
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(injected={'runtime_root': file_path, 'static_root': self.static})
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(injected={'runtime_root': self.root, 'static_root': self.root / 'missing-static'})

    def test_canonical_and_symlink_canonical_runtime_rejected(self):
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(injected={'runtime_root': ROOT, 'static_root': self.static})
        link = Path(self.temp.name) / 'canonical-link'
        link.symlink_to(ROOT, target_is_directory=True)
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(injected={'runtime_root': link, 'static_root': self.static})

    def test_static_inside_runtime_and_missing_assets_rejected(self):
        inside = self.root / 'static'
        inside.mkdir()
        for name in ('index.html', 'app.js', 'styles.css', 'detail.html'):
            (inside / name).write_bytes(b'asset')
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(injected={'runtime_root': self.root, 'static_root': inside})
        (self.static / 'styles.css').unlink()
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(injected={'runtime_root': self.root, 'static_root': self.static})

    def test_invalid_configuration_writes_nothing(self):
        with mock.patch.object(Path, 'mkdir', side_effect=AssertionError('mkdir called')):
            with self.assertRaises(ValueError):
                server.initialize_runtime(server.RuntimePaths(self.root / 'missing', self.static))

    def test_escaping_operational_symlink_rejected_before_writes(self):
        operations = self.root / 'operations'
        operations.mkdir()
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        (operations / 'briefs').symlink_to(outside, target_is_directory=True)
        paths = server.RuntimePaths(self.root, self.static)
        with mock.patch.object(Path, 'mkdir', side_effect=AssertionError('mkdir called')):
            with self.assertRaises(ValueError):
                server.initialize_runtime(paths)
        self.assertFalse((outside / 'results').exists())

    def test_import_has_no_filesystem_writes(self):
        code = """
import hashlib, json, os
from pathlib import Path
def snapshot(root):
    result = []
    for path in sorted(Path(root).rglob('*')):
        stat = path.lstat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        result.append((str(path), stat.st_mode, stat.st_size, stat.st_mtime_ns, digest))
    return result
root = '/home/raphael/myproject/operations'
before = snapshot(root)
import operations_dashboard_server as m
after = snapshot(root)
print(json.dumps({'ui': str(m.UI_DIR), 'before': before, 'after': after}, sort_keys=True))
"""
        env = os.environ.copy()
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['ui'], str(STATIC))
        self.assertEqual(payload['before'], payload['after'])
        self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()