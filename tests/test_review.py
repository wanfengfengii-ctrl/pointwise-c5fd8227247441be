import json
from fractions import Fraction as F

from delivery.export import export_handoff
from delivery.readback import receive_report
from issue.packet import encode_packet
from review.requests import submit_review
from tests.support import ProjectCase, count_rows, scenario, window


class TestReview(ProjectCase):
    def test_saturated_band(self):
        packet = self.packet()
        bounds = window(1, 1)
        with self.reports() as store:
            report = self.review(store, packet, bounds, '3/4')
            self.assert_masses(report, F(1, 4), F(1, 16), F(1, 4), msg='SATURATED_BAND')
            self.assertEqual(report.draft.parent, packet.ref)
        with self.reports(initialize=False) as store:
            handoff = export_handoff(receive_report(store, report.number))
        self.assertEqual(handoff['parent'], packet.ref.as_dict())
        self.assertEqual(handoff['window'], window('1', '1'))
        self.assertEqual(handoff['threshold'], '3/4')
        self.assertEqual((handoff['selected'], handoff['passed'], handoff['rate']), ('1/4', '1/16', '1/4'))

    def test_shared_draw(self):
        diagonal = self.packet([scenario(a=(1, 0, 0), b=(1, 0, 0))], batch='together')
        triangle = self.packet([scenario(a=(1, 0, 0), b=(0, 1, 0))], batch='split')
        bounds = window('1/2', 1)
        with self.reports() as store:
            for packet in (diagonal, triangle):
                self.assert_masses(self.review(store, packet, window(), '1/2'), F(1), F(1, 4), F(1, 4))
                self.assert_masses(self.review(store, packet, bounds, 0), F(1, 4), F(1, 4), F(1))
            self.assert_masses(self.review(store, diagonal, bounds, '1/2'), F(1, 4), F(1, 4), F(1))
            self.assert_masses(self.review(store, triangle, bounds, '1/2'), F(1, 4), F(0), F(0))

    def test_atom_window(self):
        packet = self.packet([scenario(b=(2, 0, 0))])
        with self.reports() as store:
            closed = self.review(store, packet, window(1, 1), 1)
            self.assert_masses(closed, F(1, 4), F(1, 4), F(1))
            opened = self.review(store, packet, window(1, 1, include_low=False), 1)
            self.assert_masses(opened, F(0), F(0), None)
        with self.reports(initialize=False) as store:
            self.assertEqual(export_handoff(receive_report(store, closed.number))['status'], 'measured')
            empty = export_handoff(receive_report(store, opened.number))
            self.assertEqual(empty['status'], 'no_evidence')
            self.assertIsNone(empty['rate'])
            self.assertEqual(empty['window'], window('1', '1', include_low=False))

    def test_full_range_open(self):
        packet = self.packet([scenario(b=(2, 0, 0))])
        with self.reports() as store:
            report = self.review(store, packet, window(0, 1, include_high=False), 1)
            self.assert_masses(report, F(3, 4), F(0), F(0))
            delivered = export_handoff(receive_report(store, report.number))
            self.assertEqual((delivered['status'], delivered['rate']), ('measured', '0'))

    def test_wrong_batch(self):
        left = self.packet(batch='A')
        right = self.packet(batch='B')
        with self.reports() as store:
            existing = self.review(store, left, window(), 0)
            with self.assertRaisesRegex(ValueError, '失配'):
                self.review(store, right, window(), 0, batch='A')
            with self.assertRaisesRegex(ValueError, '失配'):
                self.review(store, right, window(), 0, packet_id=left.ref.packet_id)
        with self.reports(initialize=False) as store:
            self.assertEqual(count_rows(store.db, 'reports'), 1)
            self.assertEqual(receive_report(store, existing.number).draft.parent, left.ref)

    def test_malformed(self):
        packet = self.packet()
        text = encode_packet(packet)
        missing_source_field = json.loads(text)
        del missing_source_field['source']['revision']
        empty_evidence = json.loads(text)
        empty_evidence['evidence'] = []
        altered_source = json.loads(text)
        altered_source['source']['revision'] += 1
        bad_texts = [json.dumps(item) for item in (missing_source_field, empty_evidence, altered_source)]
        bad_texts.extend(['{', text.replace('"version":1', '"version":1,"version":1')])
        with self.reports() as store:
            for bad in bad_texts:
                with self.subTest(text=bad), self.assertRaises(ValueError):
                    submit_review(store, batch=packet.ref.batch, packet_id=packet.ref.packet_id,
                                  packet_text=bad, window=window(), threshold=0)
            self.assertEqual(count_rows(store.db, 'reports'), 0)

    def test_invalid_or_outside_window(self):
        packet = self.packet()
        with self.reports() as store:
            for bounds, threshold in [(window(1, 0), 0), (window(), '1/0'), ({'low': 0}, 0),
                                      (window(include_high=1), 0)]:
                with self.subTest(bounds=bounds, threshold=threshold), self.assertRaises(ValueError):
                    self.review(store, packet, bounds, threshold)
            self.assertEqual(count_rows(store.db, 'reports'), 0)
            self.assert_masses(self.review(store, packet, window('3/2', 2), 0), F(0), F(0), None)
            self.assert_masses(self.review(store, packet, window(-1, 2), -1), F(1), F(1), F(1))
