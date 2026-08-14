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

    def test_canonical_runtime_requires_exact_opt_in_flag(self):
        base = {
            'OPS_DASHBOARD_RUNTIME_ROOT': str(ROOT),
            'OPS_DASHBOARD_STATIC_ROOT': str(self.static),
        }
        for flag in (None, '', 'true', 'TRUE', 'yes', '0', '01', ' 1'):
            env = {**base}
            if flag is not None:
                env['OPS_DASHBOARD_ALLOW_CANONICAL_RUNTIME'] = flag
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                server.resolve_runtime_paths(env=env)

        env = {
            **base,
            'OPS_DASHBOARD_ALLOW_CANONICAL_RUNTIME': '1',
        }
        paths = server.resolve_runtime_paths(env=env)
        self.assertEqual(paths.runtime_root, ROOT)
        self.assertEqual(paths.static_root, self.static)
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(server.configure_runtime(paths), paths)

    def test_symlink_canonical_runtime_accepts_exact_opt_in_flag(self):
        link = Path(self.temp.name) / 'canonical-link'
        link.symlink_to(ROOT, target_is_directory=True)
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(env={
                'OPS_DASHBOARD_RUNTIME_ROOT': str(link),
                'OPS_DASHBOARD_STATIC_ROOT': str(self.static),
            })
        paths = server.resolve_runtime_paths(env={
            'OPS_DASHBOARD_RUNTIME_ROOT': str(link),
            'OPS_DASHBOARD_STATIC_ROOT': str(self.static),
            'OPS_DASHBOARD_ALLOW_CANONICAL_RUNTIME': '1',
        })
        self.assertEqual(paths.runtime_root, link)

    def test_canonical_runtime_accepts_clean_worktree_static_root(self):
        canonical = Path(self.temp.name) / 'canonical'
        canonical.mkdir()
        source = canonical / '.worktrees' / 'source'
        source.parent.mkdir(parents=True)
        subprocess.run(['git', 'init', str(canonical)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(canonical), 'config', 'user.email', 'test@example.com'], check=True)
        subprocess.run(['git', '-C', str(canonical), 'config', 'user.name', 'Test'], check=True)
        (canonical / 'README').write_text('source')
        source_assets = canonical / 'operations_dashboard'
        source_assets.mkdir()
        for name in ('index.html', 'app.js', 'styles.css', 'detail.html'):
            (source_assets / name).write_bytes((STATIC / name).read_bytes())
        subprocess.run(['git', '-C', str(canonical), 'add', 'README', 'operations_dashboard'], check=True)
        subprocess.run(['git', '-C', str(canonical), 'commit', '-m', 'init'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(canonical), 'worktree', 'add', str(source)], check=True, capture_output=True)
        static = source / 'operations_dashboard'
        with mock.patch.object(server, 'CANONICAL_ROOT', canonical):
            paths = server.resolve_runtime_paths(env={
                'OPS_DASHBOARD_RUNTIME_ROOT': str(canonical),
                'OPS_DASHBOARD_STATIC_ROOT': str(static),
                'OPS_DASHBOARD_ALLOW_CANONICAL_RUNTIME': '1',
            })
        self.assertEqual(paths.static_root, static)

    def test_arbitrary_nested_and_operational_static_roots_rejected(self):
        nested = ROOT / '.worktrees' / 'not-a-worktree' / 'operations_dashboard'
        operational = ROOT / '.worktrees' / 't_de1e1a6b' / 'operations'
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(env={
                'OPS_DASHBOARD_RUNTIME_ROOT': str(ROOT),
                'OPS_DASHBOARD_STATIC_ROOT': str(nested),
                'OPS_DASHBOARD_ALLOW_CANONICAL_RUNTIME': '1',
            })
        with self.assertRaises(ValueError):
            server.resolve_runtime_paths(env={
                'OPS_DASHBOARD_RUNTIME_ROOT': str(ROOT),
                'OPS_DASHBOARD_STATIC_ROOT': str(operational),
                'OPS_DASHBOARD_ALLOW_CANONICAL_RUNTIME': '1',
            })

    def test_unrelated_repository_worktree_nested_under_canonical_rejected(self):
        canonical = Path(self.temp.name) / 'canonical'
        foreign = Path(self.temp.name) / 'foreign'
        nested_foreign = canonical / '.worktrees' / 'foreign'
        for repository in (canonical, foreign):
            repository.mkdir()
            subprocess.run(['git', 'init', str(repository)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(repository), 'config', 'user.email', 'test@example.com'], check=True)
            subprocess.run(['git', '-C', str(repository), 'config', 'user.name', 'Test'], check=True)
        foreign_assets = foreign / 'operations_dashboard'
        foreign_assets.mkdir()
        for name in ('index.html', 'app.js', 'styles.css', 'detail.html'):
            (foreign_assets / name).write_bytes((STATIC / name).read_bytes())
        subprocess.run(['git', '-C', str(foreign), 'add', 'operations_dashboard'], check=True)
        subprocess.run(['git', '-C', str(foreign), 'commit', '-m', 'init'], check=True, capture_output=True)
        nested_foreign.parent.mkdir(parents=True)
        subprocess.run(
            ['git', '-C', str(foreign), 'worktree', 'add', str(nested_foreign)],
            check=True, capture_output=True,
        )
        with mock.patch.object(server, 'CANONICAL_ROOT', canonical):
            with self.assertRaises(ValueError):
                server.resolve_runtime_paths(env={
                    'OPS_DASHBOARD_RUNTIME_ROOT': str(canonical),
                    'OPS_DASHBOARD_STATIC_ROOT': str(nested_foreign / 'operations_dashboard'),
                    'OPS_DASHBOARD_ALLOW_CANONICAL_RUNTIME': '1',
                })

    def test_nested_static_symlink_escape_rejected(self):
        canonical = Path(self.temp.name) / 'canonical'
        canonical.mkdir()
        worktree = canonical / '.worktrees' / 'source'
        worktree.mkdir(parents=True)
        escaped = Path(self.temp.name) / 'escaped'
        escaped.mkdir()
        for name in ('index.html', 'app.js', 'styles.css', 'detail.html'):
            (escaped / name).write_bytes(b'asset')
        static_link = worktree / 'operations_dashboard'
        static_link.symlink_to(escaped, target_is_directory=True)
        with mock.patch.object(server, 'CANONICAL_ROOT', canonical):
            with self.assertRaises(ValueError):
                server.resolve_runtime_paths(env={
                    'OPS_DASHBOARD_RUNTIME_ROOT': str(canonical),
                    'OPS_DASHBOARD_STATIC_ROOT': str(static_link),
                    'OPS_DASHBOARD_ALLOW_CANONICAL_RUNTIME': '1',
                })

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