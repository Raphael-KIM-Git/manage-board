import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import operations_dashboard_server as server
import operations_followup_requests as followups


class FollowUpReceiptTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(Path(server.__file__).resolve(), Path(__file__).resolve().parents[1] / 'operations_dashboard_server.py')
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.parent = 'T-RECEIPT-001'
        self.payload = {
            'target': {'kind': 'task', 'id': self.parent},
            'request_type': 'verification', 'title': '검증', 'desired_outcome': '결과',
            'context': '', 'constraints': '', 'priority_requested': 'medium',
            'verification_requested': [],
        }

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def request(self, headers=None, body=None):
        body = json.dumps(self.payload).encode() if body is None else body
        conn = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port)
        supplied = {
            'Content-Type': 'application/json', 'Content-Length': str(len(body)),
            'Origin': f'http://127.0.0.1:{self.httpd.server_port}',
            'Host': f'127.0.0.1:{self.httpd.server_port}', 'Idempotency-Key': 'receipt-1',
        }
        supplied.update(headers or {})
        with patch.object(server, 'FOLLOWUP_REQUESTS_DIR', self.root), patch.object(server, '_task_exists', return_value=True):
            conn.request('POST', f'/api/tasks/{self.parent}/follow-up-requests', body=body, headers=supplied)
            response = conn.getresponse()
            return response.status, json.loads(response.read())

    def test_exact_loopback_origin_and_header_guards(self):
        status, _ = self.request({'Origin': 'http://localhost:%d' % self.httpd.server_port})
        self.assertEqual(status, 403)
        status, _ = self.request({'Content-Type': 'application/json; charset=utf-8'})
        self.assertEqual(status, 400)
        status, _ = self.request({'Idempotency-Key': ''})
        self.assertEqual(status, 400)
        status, _ = self.request(body=b'{bad')
        self.assertEqual(status, 400)

    def test_followup_rejects_invalid_length_before_body_read(self):
        class BodyMustNotBeRead:
            def read(self, _length):
                self.read_called = True
                raise AssertionError('follow-up body was read before length validation')

        for declared_length, expected_status in [('999999999999', 413), ('not-an-integer', 400)]:
            handler = object.__new__(server.Handler)
            handler.path = f'/api/tasks/{self.parent}/follow-up-requests'
            handler.headers = {'Content-Length': declared_length}
            handler.rfile = BodyMustNotBeRead()
            with patch.object(handler, '_send_json', return_value=expected_status) as send_json:
                self.assertEqual(handler.do_POST(), expected_status)
            send_json.assert_called_once()
            self.assertEqual(handler.rfile.__dict__.get('read_called', False), False)

    def test_submit_replay_and_conflict_are_receipts_only(self):
        status, first = self.request()
        self.assertEqual(status, 201)
        self.assertEqual(first['request']['state'], 'pending_pm_review')
        status, replay = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(replay['request']['request_id'], first['request']['request_id'])
        status, conflict = self.request(body=json.dumps({**self.payload, 'title': '다름'}).encode())
        self.assertEqual(status, 409)
        self.assertFalse((self.root / 'T-RECEIPT-001.json').exists())
        self.assertEqual(len(list((self.root / self.parent).glob('*.json'))), 1)

    def test_symlink_parent_fails_closed(self):
        outside = self.root / 'outside'
        outside.mkdir()
        root = self.root / 'requests'
        root.mkdir()
        (root / self.parent).symlink_to(outside, target_is_directory=True)
        with self.assertRaises(followups.FollowUpError):
            followups.submit_request(self.parent, self.payload, 'safe', requests_dir=root, task_exists=lambda _: True)
        self.assertEqual(list(outside.iterdir()), [])

    def test_ipv6_origin_requires_bracketed_canonical_host(self):
        handler = object.__new__(server.Handler)
        handler.server = type('S', (), {'server_address': ('::1', 8765)})()
        handler.headers = {'Origin': 'http://[::1]:8765', 'Host': '[::1]:8765'}
        self.assertTrue(handler._followup_origin_allowed())
        handler.headers = {'Origin': 'http://::1:8765', 'Host': '::1:8765'}
        self.assertFalse(handler._followup_origin_allowed())

    def test_static_ui_contract_keeps_draft_on_stale_conflict(self):
        source = (Path(__file__).resolve().parents[1] / 'operations_dashboard' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('followUpStale', source)
        self.assertIn('error.status = response.status', source)
        self.assertIn('초안은 그대로 유지됩니다', source)
        self.assertIn('현재 이력 새로고침', source)
        self.assertNotIn('if (response.status === 409) await loadFollowUpHistory', source)


if __name__ == '__main__':
    unittest.main()
