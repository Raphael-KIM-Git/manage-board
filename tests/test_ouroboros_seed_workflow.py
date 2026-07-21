import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SERVER_PATH = Path('/home/raphael/myproject/operations_dashboard_server.py')
spec = importlib.util.spec_from_file_location('operations_dashboard_server', SERVER_PATH)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class OuroborosSeedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.original = {
            'BRIEFS_DIR': server.BRIEFS_DIR,
            'INTERVIEWS_DIR': getattr(server, 'INTERVIEWS_DIR', None),
            'SEEDS_DIR': getattr(server, 'SEEDS_DIR', None),
        }
        server.BRIEFS_DIR = root / 'briefs'
        server.INTERVIEWS_DIR = root / 'interviews'
        server.SEEDS_DIR = root / 'seeds'
        for folder in (server.BRIEFS_DIR, server.INTERVIEWS_DIR, server.SEEDS_DIR):
            folder.mkdir(parents=True, exist_ok=True)
        self.task = {
            'task_id': 'T-20260721-001',
            'created_at': '2026-07-21T12:00:00',
            'updated_at': '2026-07-21T12:00:00',
            'title': 'D2-WORK 파일럿 기능',
            'objective': '승인된 명세와 검증 기준으로 기능을 구현한다.',
            'context': '기존 D2-WORK 구조를 유지한다.',
            'constraints': 'main 브랜치 직접 push 금지',
            'deliverable': '코드, 테스트, 변경 요약',
            'reviewer': 'HermesVerifier',
            'artifacts': {},
        }
        self.task_path = server.BRIEFS_DIR / 'T-20260721-001-pilot.json'
        self.task_path.write_text(json.dumps(self.task, ensure_ascii=False), encoding='utf-8')

    def tearDown(self):
        for name, value in self.original.items():
            if value is not None:
                setattr(server, name, value)
        self.tmp.cleanup()

    def test_creates_interview_then_versioned_seed_then_approves_it(self):
        interview = server.create_interview_artifact(
            self.task,
            questions=['대상 사용자는 누구인가?', '완료 기준은 무엇인가?'],
            answers=['내부 운영자', '목록·상세·테스트가 동작한다'],
        )
        self.assertEqual(interview['status'], 'completed')
        self.assertTrue(Path(interview['json_path']).is_file())

        seed = server.create_seed_artifact(
            self.task,
            acceptance_criteria=['목록과 상세 흐름이 동작한다', '자동 테스트가 통과한다'],
            included_scope=['고객 목록', '고객 상세'],
            excluded_scope=['외부 CRM 연동'],
            assumptions=['초기 대상은 내부 운영자다'],
        )
        self.assertEqual(seed['version'], 1)
        self.assertEqual(seed['status'], 'awaiting_approval')
        self.assertTrue(Path(seed['json_path']).is_file())

        approved = server.approve_seed_artifact(seed['json_path'], approver='Raphael')
        self.assertEqual(approved['status'], 'approved')
        self.assertEqual(approved['approved_by'], 'Raphael')


if __name__ == '__main__':
    unittest.main()
