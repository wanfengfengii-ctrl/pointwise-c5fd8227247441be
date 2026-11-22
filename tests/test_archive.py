from fractions import Fraction as F

from archive.batches import BatchArchive
from archive.queries import get_current_revision, get_revision
from archive.revisions import RevisionRef
from tests.support import ProjectCase, count_rows, observation


class TestArchive(ProjectCase):
    def test_duplicate_observation(self):
        with self.station() as (db, revisions, _, _):
            archive = BatchArchive(revisions)
            original = archive.submit('A', [observation(raw=('1/9', 0))])
            duplicate = [observation(raw=(1, 0)), observation(raw=(2, 0))]
            with self.assertRaisesRegex(ValueError, '重复测次'):
                archive.correct(original, duplicate)
            with self.assertRaisesRegex(ValueError, '重复测次'):
                archive.submit('B', duplicate)
            self.assertEqual(count_rows(db, 'revisions'), 1)
            self.assertEqual(count_rows(db, 'batch_heads'), 1)
            current = get_current_revision(revisions, 'A')
            self.assertEqual(current.ref, original)
            self.assertEqual(current.observations[0].raw, (F(1, 9), F(0)))
            self.assertIsNone(get_current_revision(revisions, 'B'))

    def test_stale_parent(self):
        with self.station() as (_, revisions, _, _):
            archive = BatchArchive(revisions)
            first = archive.submit('A', [observation(raw=('0.125', 0))])
            second = archive.correct(first, [observation(raw=('2/7', 0))])
            with self.assertRaisesRegex(ValueError, '失配'):
                archive.correct(first, [observation(raw=(1, 0))])
            with self.assertRaisesRegex(ValueError, '已存在'):
                archive.submit('A', [observation()])
            self.assertEqual(get_current_revision(revisions, 'A').ref, second)
            self.assertEqual(get_revision(revisions, second).parent, first.number)
            self.assertEqual(get_revision(revisions, first).observations[0].raw[0], F(1, 8))
            self.assertIsNone(get_revision(revisions, RevisionRef('A', 3)))

    def test_invalid_input_leaves_no_revision(self):
        invalid_inputs = (
            [observation(raw=('1/0', 0))], [observation(raw=(False, 0))],
            [observation(raw=(0.1, 0))], [observation(name='')], [],
        )
        with self.station() as (db, revisions, _, _):
            archive = BatchArchive(revisions)
            for values in invalid_inputs:
                with self.subTest(values=values), self.assertRaises(ValueError):
                    archive.submit('A', values)
            with self.assertRaises(ValueError):
                archive.submit('A', [observation()], [
                    {'name': 'anchor', 'observation': 'unknown', 'origin': (0, 0)},
                ])
            self.assertEqual(count_rows(db, 'batch_heads'), 0)
            self.assertEqual(count_rows(db, 'revisions'), 0)
