"""Language-scoped mock exams use synthetic submission metadata only."""
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from interview_forge.db.schema import SCHEMA
from interview_forge.services.study import mock_exam


class MockLanguagesTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'study.db'
        self.problems = {i: dict(id=i, title=str(i), category='A' if i < 6 else 'B', difficulty='简单', method='test') for i in range(1, 9)}
        self.addCleanup(patch.stopall)
        patch('interview_forge.services.study.PROBLEM_BY_ID', self.problems).start()
        patch('interview_forge.services.study.problem_note', return_value='').start()
        with sqlite3.connect(self.db) as con:
            con.executescript(SCHEMA)
            con.executemany('INSERT INTO submissions(problem_id,status,lang,submitted_at) VALUES (?,?,?,?)', [
                (1,'ac','Python3','2026-01-01T12:00:00Z'),
                (2,'ac','java17','2026-01-02T12:00:00Z'),
                (3,'ac','python','2026-01-02T12:00:00Z'),
                (3,'ac','Java','2026-01-02T12:00:00Z'),
                (4,'ac','','2026-01-02T12:00:00Z'),
                (5,'wa','python','2026-01-02T12:00:00Z'),
                (6,'ac','python','invalid-date'),
            ])
            con.execute("INSERT INTO study_events(problem_id,action,studied_at,study_date) VALUES (7,'view','2026-01-02T12:00:00Z','2026-01-02')")

    def exam(self, **kwargs):
        return mock_exam(count=50, scope='unseen', db_path=self.db, **kwargs)

    def test_language_independence_aliases_and_unknowns(self):
        for language, expected in [('Python3',{2,4,5,6,7,8}), ('PYTHON',{2,4,5,6,7,8}), ('java',{1,4,5,6,7,8})]:
            with self.subTest(language=language):
                preview = self.exam(language=language, preview=True)
                actual = self.exam(language=language)
                self.assertEqual({p['id'] for p in actual['problems']}, expected)
                self.assertEqual(preview['scope_pool'], len(expected))
                self.assertEqual(actual['scope_pool'], preview['scope_pool'])

    def test_legacy_scope_keeps_view_and_ac_exclusion(self):
        self.assertEqual({p['id'] for p in self.exam()['problems']}, {5,8})

    def test_preview_has_no_history_side_effects_and_zero_is_not_failure(self):
        for _ in range(2):
            self.assertEqual(self.exam(language='python', category='missing', preview=True)['scope_pool'], 0)
            self.exam(language='python', preview=True)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM mock_exam_records').fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM settings WHERE key LIKE '%mock%'").fetchone()[0], 0)
        with self.assertRaises(ValueError):
            self.exam(language='python', category='missing')

    def test_filters_and_invalid_language(self):
        self.assertEqual({p['id'] for p in self.exam(language='python', category='A')['problems']}, {2,4,5})
        self.assertEqual(self.exam(language='python', difficulty='困难', preview=True)['scope_pool'], 0)
        for kwargs in ({'language':'unknown'}, {'language':'rust'}):
            with self.assertRaises(ValueError):
                self.exam(**kwargs)
        with self.assertRaises(ValueError):
            mock_exam(scope='all', language='python', db_path=self.db)
        self.assertEqual(mock_exam(scope='all', preview=True, db_path=self.db)['scope_pool'], 8)
