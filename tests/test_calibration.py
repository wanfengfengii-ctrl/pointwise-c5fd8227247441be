from fractions import Fraction as F

from archive.batches import BatchArchive
from archive.revisions import RevisionRef
from calibration.response import evaluate_pair
from tests.support import ProjectCase, count_rows, observation, scenario, window


class TestCalibration(ProjectCase):
    def test_invalid_weight(self):
        with self.station() as (db, revisions, calibrations, _):
            ref = BatchArchive(revisions).submit('A', [observation()])
            for left, right in [('1/4', '1/4'), ('-1/4', '5/4'), ('1/0', 0)]:
                with self.subTest(left=left, right=right), self.assertRaises(ValueError):
                    calibrations.register(ref, [scenario(weight=left), scenario(name='s2', weight=right)])
            self.assertEqual(count_rows(db, 'calibrations'), 0)

    def test_triangle_domain(self):
        with self.station() as (db, revisions, calibrations, _):
            ref = BatchArchive(revisions).submit('A', [observation()])
            with self.assertRaisesRegex(ValueError, '正面积'):
                calibrations.register(ref, [scenario(vertices=((0, 0), (1, 1), (2, 2)))])
            self.assertEqual(count_rows(db, 'calibrations'), 0)

    def test_zero_weight(self):
        packet = self.packet([
            scenario(a=(0, 0, 1), b=(0, 0, 0), name='ignored', weight=0),
            scenario(a=(0, 0, 0), b=(0, 0, 1), name='used', weight=1),
        ])
        with self.reports() as store:
            self.assert_masses(self.review(store, packet, window(), 1), F(1), F(1), F(1))
            self.assert_masses(self.review(store, packet, window(1, 1), 0), F(0), F(0), None)
        with self.station(initialize=False) as (_, _, calibrations, _):
            ref = packet.ref
            saved = calibrations.read_exact(ref.batch, ref.calibration_id, ref.revision)
            self.assertEqual([item.scenario.weight for item in saved.scenarios], [F(0), F(1)])

    def test_anchor_uses_exact_revision(self):
        anchor = {'name': 'origin', 'observation': 'm1', 'origin': ('1/4', '1/8')}
        model = scenario(a=(1, 0, '1/2'), b=(0, 1, '1/3'))
        model['anchor'] = 'origin'
        with self.station() as (db, revisions, calibrations, _):
            archive = BatchArchive(revisions)
            old = archive.submit('A', [observation(raw=('1/5', '1/4'), reference=('3/10', '1/4'))], [anchor])
            current = archive.correct(old, [observation()], [anchor])
            for missing in (RevisionRef('A', 3), RevisionRef('B', 1)):
                with self.assertRaisesRegex(ValueError, '修订不存在'):
                    calibrations.register(missing, [model])
            with self.assertRaisesRegex(ValueError, '缺少情景锚点'):
                calibrations.register(current, [{**model, 'anchor': 'absent'}])
            with self.assertRaises(ValueError):
                calibrations.register(current, [{**model, 'a': (1, 0)}])
            self.assertEqual(count_rows(db, 'calibrations'), 0)
            first = calibrations.register(old, [model])
            second = calibrations.register(current, [model])
            point = F(1, 4), F(1, 8)
            self.assertEqual(evaluate_pair(first.scenarios[0], point), (F(3, 5), F(1, 3)))
            self.assertEqual(evaluate_pair(second.scenarios[0], point), (F(1, 2), F(1, 3)))
            self.assertEqual(calibrations.read_exact('A', first.number, old.number), first)
