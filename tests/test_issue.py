import json
from fractions import Fraction as F

from archive.batches import BatchArchive
from issue.packet import decode_packet, encode_packet
from issue.publication import issue_packet
from tests.support import ProjectCase, count_rows, observation, scenario, window


class TestIssue(ProjectCase):
    def test_revision_binding(self):
        with self.station() as (db, revisions, calibrations, catalog):
            archive = BatchArchive(revisions)
            ref = archive.submit('A', [observation(name='station-only-measurement', raw=('47/99', 0))])
            archive.correct(ref, [observation(raw=(1, 0))])
            calibration = calibrations.register(ref, [scenario()])
            args = dict(batch='A', calibration_id=calibration.number, version=ref.number)
            packet = issue_packet(calibrations, catalog, **args)
            self.assertEqual(packet.ref.revision, ref.number)
            self.assertEqual(packet.ref.calibration_id, calibration.number)
            self.assertEqual(issue_packet(calibrations, catalog, **args), packet)
            self.assertEqual(count_rows(db, 'packets'), 1)
            self.assertEqual(catalog.get(packet.ref.packet_id), packet)
        text = encode_packet(packet)
        envelope = json.loads(text)
        self.assertEqual(set(envelope), {'version', 'source', 'evidence'})
        self.assertEqual(envelope['source'], packet.ref.as_dict())
        self.assertEqual(envelope['version'], 1)
        self.assertNotIn('station-only-measurement', text)
        self.assertNotIn('47/99', text)
        self.assertEqual(decode_packet(text).ref, packet.ref)
        with self.reports() as store:
            self.assert_masses(self.review(store, packet, window(), 0), F(1), F(1), F(1))

    def test_binding_mismatch(self):
        with self.station() as (db, revisions, calibrations, catalog):
            archive = BatchArchive(revisions)
            first = archive.submit('A', [observation()])
            second = archive.correct(first, [observation()])
            archive.submit('B', [observation()])
            calibration = calibrations.register(first, [scenario()])
            for batch, number, version in [('B', calibration.number, 1), ('A', calibration.number, second.number),
                                            ('A', calibration.number + 1, 1)]:
                with self.subTest(batch=batch, number=number, version=version):
                    with self.assertRaisesRegex(ValueError, '绑定失配'):
                        issue_packet(calibrations, catalog, batch=batch, calibration_id=number, version=version)
            self.assertEqual(count_rows(db, 'packets'), 0)

    def test_boundary_constant(self):
        packet = self.packet([scenario(a=(0, 0, 1))])
        with self.reports() as store:
            self.assert_masses(self.review(store, packet, window(1, 1), '1/2'), F(1), F(1, 4), F(1, 4))

    def test_clipping_and_overlapping_mixture(self):
        packet = self.packet([
            scenario(a=(2, 0, '-1/2'), b=(0, 0, 0), weight='1/3'),
            scenario(a=(2, 0, '-1/2'), b=(0, 0, 0), name='same', weight='2/3'),
        ])
        with self.reports() as store:
            self.assert_masses(self.review(store, packet, window(0, 0), 0), F(7, 16), F(7, 16), F(1))
            self.assert_masses(self.review(store, packet, window(1, 1), 0), F(1, 16), F(1, 16), F(1))
            self.assert_masses(self.review(store, packet, window(0, 1, include_low=False, include_high=False), 0),
                               F(1, 2), F(1, 2), F(1))
