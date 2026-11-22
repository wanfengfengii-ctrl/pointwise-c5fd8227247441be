import sqlite3
import unittest
from fractions import Fraction as F

import threshold_examples
from delivery.export import export_threshold_handoff
from delivery.readback import (
    ReportNotFound,
    receive_report,
    receive_threshold_review,
    threshold_allows,
)
from delivery.reports import SignedThresholdReport, ThresholdDraft, validate_threshold_report
from issue.packet import encode_packet
from review.requests import submit_threshold_review
from review.roots import QuadraticRoot, compare_root, make_quadratic_root
from review.windows import ReviewWindow
from tests.support import ProjectCase, count_rows, observation, scenario, window
from threshold_examples import CUT_WINDOW, EMPTY_WINDOW, FULL_SCALE, example_packets


CONTINUOUS_ROOT = make_quadratic_root(2, -4, 1, 'low')
TWO_ROOTS_ROOT = make_quadratic_root(32, -32, 7, 'low')

SAMPLE_CASES = (
    ('continuous', FULL_SCALE, '1/2'),
    ('saturated', FULL_SCALE, '1/8'),
    ('plateau', FULL_SCALE, '1/2'),
    ('two-roots', FULL_SCALE, '1/2'),
    ('window-cut', CUT_WINDOW, '1/20'),
    ('continuous', EMPTY_WINDOW, 0),
    ('continuous', FULL_SCALE, 0),
)


class TestThresholdSamples(ProjectCase):
    def sign_samples(self):
        packets = example_packets()
        signed = []
        with self.reports() as store:
            for batch, bounds, rate in SAMPLE_CASES:
                ref, text = packets[batch]
                signed.append(submit_threshold_review(
                    store, batch=batch, packet_id=ref.packet_id, packet_text=text,
                    window=bounds, minimum_rate=rate))
        return packets, signed

    def test_forward_examples_still_hold(self):
        threshold_examples.main()

    def test_business_table(self):
        packets, signed = self.sign_samples()
        expected = [
            ('continuous', F(1), CONTINUOUS_ROOT),
            ('saturated', F(1), F(1)),
            ('plateau', F(1), F(3, 4)),
            ('two-roots', F(1), TWO_ROOTS_ROOT),
            ('window-cut', F(5, 16), F(5, 8)),
            ('continuous', F(0), None),
            ('continuous', F(1), F(1)),
        ]
        for report, (batch, selected, threshold) in zip(signed, expected):
            with self.subTest(batch=batch, minimum_rate=report.draft.minimum_rate):
                draft = report.draft
                self.assertEqual(draft.parent, packets[batch][0])
                self.assertEqual(draft.selected, selected)
                self.assertEqual(draft.threshold, threshold)
                self.assertEqual(draft.status, 'no_evidence' if threshold is None else 'measured')
        continuous = signed[0].draft
        self.assertEqual(continuous.window, ReviewWindow(F(1), F(1), True, True))
        self.assertEqual(continuous.minimum_rate, F(1, 2))
        self.assertEqual(signed[4].draft.window, ReviewWindow(F(1, 4), F(1, 2), True, False))
        self.assertEqual(signed[4].draft.minimum_rate, F(1, 20))

    def test_receive_after_reopen(self):
        _, signed = self.sign_samples()
        with self.reports(initialize=False) as store:
            for report in signed:
                with self.subTest(number=report.number):
                    self.assertEqual(receive_threshold_review(store, report.number), report)
            receipts = store.db.execute(
                'SELECT report_number FROM threshold_receipts ORDER BY number').fetchall()
            self.assertEqual(receipts, [(report.number,) for report in signed])

    def test_threshold_allows_from_held_report(self):
        _, signed = self.sign_samples()
        continuous, saturated, plateau, two_roots, window_cut, empty, zero_target = signed
        self.assertIs(threshold_allows(continuous, '29/100'), True)
        self.assertIs(threshold_allows(continuous, '73/250'), True)
        self.assertIs(threshold_allows(continuous, '3/10'), False)
        self.assertIs(threshold_allows(continuous, F(1, 4)), True)
        self.assertIs(threshold_allows(saturated, 1), True)
        self.assertIs(threshold_allows(plateau, '1/2'), True)
        self.assertIs(threshold_allows(plateau, '3/4'), True)
        self.assertIs(threshold_allows(plateau, '4/5'), False)
        self.assertIs(threshold_allows(two_roots, '3/10'), True)
        self.assertIs(threshold_allows(two_roots, '2/5'), False)
        self.assertIs(threshold_allows(window_cut, '5/8'), True)
        self.assertIs(threshold_allows(window_cut, '2/3'), False)
        self.assertIsNone(threshold_allows(empty, '1/2'))
        self.assertIsNone(threshold_allows(empty, 0))
        self.assertIs(threshold_allows(zero_target, 1), True)

    def test_export_threshold_handoff(self):
        _, signed = self.sign_samples()
        continuous, _, plateau, _, _, empty, _ = signed
        handoff = export_threshold_handoff(continuous)
        self.assertEqual(handoff['number'], continuous.number)
        self.assertEqual(handoff['parent'], continuous.draft.parent.as_dict())
        self.assertEqual(handoff['window'], window('1', '1'))
        self.assertEqual(handoff['minimum_rate'], '1/2')
        self.assertEqual(handoff['selected'], '1')
        self.assertEqual(handoff['status'], 'measured')
        self.assertEqual(handoff['threshold'],
                         {'kind': 'quadratic', 'a': '2', 'b': '-4', 'c': '1', 'root': 'low'})
        self.assertEqual(export_threshold_handoff(plateau)['threshold'],
                         {'kind': 'rational', 'value': '3/4'})
        empty_handoff = export_threshold_handoff(empty)
        self.assertEqual(empty_handoff['status'], 'no_evidence')
        self.assertEqual(empty_handoff['threshold'], {'kind': 'none'})


class TestThresholdStore(ProjectCase):
    def threshold_review(self, store, packet, bounds, minimum_rate, *, batch=None, packet_id=None, text=None):
        return submit_threshold_review(
            store,
            batch=packet.ref.batch if batch is None else batch,
            packet_id=packet.ref.packet_id if packet_id is None else packet_id,
            packet_text=encode_packet(packet) if text is None else text,
            window=bounds, minimum_rate=minimum_rate,
        )

    def test_independent_numbering(self):
        packet = self.packet()
        with self.reports() as store:
            forward = self.review(store, packet, window(), 0)
            inverse = self.threshold_review(store, packet, window(), 0)
            self.assertEqual((forward.number, inverse.number), (1, 1))
            self.assertEqual(count_rows(store.db, 'reports'), 1)
            self.assertEqual(count_rows(store.db, 'threshold_reports'), 1)
        with self.reports(initialize=False) as store:
            self.assertEqual(receive_report(store, forward.number), forward)
            self.assertEqual(receive_threshold_review(store, inverse.number), inverse)
            self.assertEqual(count_rows(store.db, 'receipts'), 1)
            self.assertEqual(count_rows(store.db, 'threshold_receipts'), 1)

    def test_unknown_or_invalid_number(self):
        packet = self.packet()
        with self.reports() as store:
            report = self.threshold_review(store, packet, window(), 0)
            with self.assertRaisesRegex(ReportNotFound, '未找到'):
                receive_threshold_review(store, report.number + 1)
            for bad in (0, -1, 1.5, '1', True, None):
                with self.subTest(number=bad), self.assertRaises(ValueError):
                    receive_threshold_review(store, bad)
            self.assertEqual(count_rows(store.db, 'threshold_receipts'), 0)
            self.assertEqual(receive_threshold_review(store, report.number), report)

    def test_invalid_requests_leave_no_report(self):
        packet = self.packet()
        with self.reports() as store:
            for bounds, rate in [(window(), '5/4'), (window(), -1), (window(), 0.5),
                                 (window(), True), (window(), '1/0'), (window(), None),
                                 (window(1, 0), 0), ({'low': 0}, 0), (window(include_high=1), 0)]:
                with self.subTest(bounds=bounds, rate=rate), self.assertRaises(ValueError):
                    self.threshold_review(store, packet, bounds, rate)
            self.assertEqual(count_rows(store.db, 'threshold_reports'), 0)

    def test_high_root_selector(self):
        packet = self.packet([scenario(a=(0, 0, 1), b=(-1, 0, 1))])
        with self.reports() as store:
            report = self.threshold_review(store, packet, window(1, 1), '1/2')
            self.assertEqual(report.draft.threshold, make_quadratic_root(2, 0, -1, 'high'))
        with self.reports(initialize=False) as store:
            received = receive_threshold_review(store, report.number)
            self.assertEqual(received, report)
        self.assertIs(threshold_allows(received, '7/10'), True)
        self.assertIs(threshold_allows(received, '5/7'), False)

    def test_step_edges(self):
        saturated = self.packet([scenario(a=(0, 0, 1), b=(2, 0, 0))])
        plateau = self.packet([
            scenario(a=(0, 0, 1), b=(0, 0, '1/4'), name='low', weight='1/2'),
            scenario(a=(0, 0, 1), b=(0, 0, '3/4'), name='high', weight='1/2'),
        ], batch='CG-042')
        with self.reports() as store:
            # 满量程点质量恰为目标时签 1
            top = self.threshold_review(store, saturated, window(1, 1), '1/4')
            self.assertEqual(top.draft.threshold, F(1))
            # 目标 1 时落在平台左端点质量上
            left_edge = self.threshold_review(store, plateau, window(1, 1), 1)
            self.assertEqual(left_edge.draft.threshold, F(1, 4))
            # 目标恰低于点质量率时仍签 1
            just_above = self.threshold_review(store, saturated, window(1, 1), '1/5')
            self.assertEqual(just_above.draft.threshold, F(1))
        self.assertIs(threshold_allows(top, 1), True)
        self.assertIs(threshold_allows(left_edge, '1/4'), True)
        self.assertIs(threshold_allows(left_edge, '1/3'), False)

    def test_wrong_packet_or_batch(self):
        left = self.packet(batch='A')
        right = self.packet(batch='B')
        with self.reports() as store:
            existing = self.threshold_review(store, left, window(), 0)
            with self.assertRaisesRegex(ValueError, '失配'):
                self.threshold_review(store, right, window(), 0, batch='A')
            with self.assertRaisesRegex(ValueError, '失配'):
                self.threshold_review(store, right, window(), 0, packet_id=left.ref.packet_id)
            with self.assertRaises(ValueError):
                self.threshold_review(store, left, window(), 0, packet_id='z' * 64)
            self.assertEqual(count_rows(store.db, 'threshold_reports'), 1)
        with self.reports(initialize=False) as store:
            self.assertEqual(receive_threshold_review(store, existing.number).draft.parent, left.ref)

    def test_malformed_packet_text(self):
        packet = self.packet()
        with self.reports() as store:
            for bad in ('{', '', '[]', encode_packet(packet).replace('"version":1', '"version":2')):
                with self.subTest(text=bad), self.assertRaises(ValueError):
                    self.threshold_review(store, packet, window(), 0, text=bad)
            self.assertEqual(count_rows(store.db, 'threshold_reports'), 0)

    def test_threshold_allows_rejects_bad_input(self):
        packet = self.packet()
        with self.reports() as store:
            report = self.threshold_review(store, packet, window(1, 1), '1/4')
            forward = self.review(store, packet, window(), 0)
        for bad in ('3/2', -1, 0.5, True, 'x', None):
            with self.subTest(setting=bad), self.assertRaises(ValueError):
                threshold_allows(report, bad)
        with self.assertRaises(ValueError):
            threshold_allows(forward, '1/2')
        with self.assertRaises(ValueError):
            threshold_allows('not-a-report', '1/2')
        self.assertIs(threshold_allows(report, '3/4'), True)
        self.assertIs(threshold_allows(report, '4/5'), False)

    def test_failed_commit_and_retry(self):
        packet = self.packet()
        with self.reports() as store:
            existing = self.threshold_review(store, packet, window(), 0)
            store.db.executescript('''
                CREATE TABLE test_authorized (number INTEGER PRIMARY KEY);
                CREATE TABLE test_commit_guard (
                    number INTEGER REFERENCES test_authorized (number) DEFERRABLE INITIALLY DEFERRED
                );
                CREATE TRIGGER test_guard_after_threshold AFTER INSERT ON threshold_reports BEGIN
                    INSERT INTO test_commit_guard (number) VALUES (NEW.number);
                END;
            ''')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
                self.threshold_review(store, packet, window(1, 1), '1/4')
        with self.reports(initialize=False) as store:
            self.assertEqual(count_rows(store.db, 'threshold_reports'), 1)
            self.assertEqual(count_rows(store.db, 'test_commit_guard'), 0)
            self.assertIsNone(store.read_threshold(existing.number + 1))
            self.assertEqual(receive_threshold_review(store, existing.number), existing)
            store.db.execute('DROP TRIGGER test_guard_after_threshold')
            retry = self.threshold_review(store, packet, window(1, 1), '1/4')
        with self.reports(initialize=False) as store:
            self.assertEqual(count_rows(store.db, 'threshold_reports'), 2)
            received = receive_threshold_review(store, retry.number)
            self.assertEqual(received.draft.parent, packet.ref)
            self.assertEqual(received.draft.selected, F(1, 4))
            self.assertEqual(received.draft.threshold, F(3, 4))

    def publish_history(self):
        batch = 'CG-041'
        with self.station() as (_, revisions, calibrations, catalog):
            from archive.batches import BatchArchive
            from issue.publication import issue_packet
            first = BatchArchive(revisions).submit(batch, [observation(raw=('1/9', 0))])
            old_calibration = calibrations.register(first, [scenario()])
            old_packet = issue_packet(calibrations, catalog, batch=batch,
                                      calibration_id=old_calibration.number, version=first.number)
        with self.reports() as store:
            old = self.threshold_review(store, old_packet, window(), '1/4')
        with self.station(initialize=False) as (_, revisions, calibrations, catalog):
            from archive.batches import BatchArchive
            from issue.publication import issue_packet
            second = BatchArchive(revisions).correct(first, [observation(raw=('2/9', 0))])
            new_calibration = calibrations.register(second, [scenario(b=('1/2', 0, 0))])
            new_packet = issue_packet(calibrations, catalog, batch=batch,
                                      calibration_id=new_calibration.number, version=second.number)
        with self.reports(initialize=False) as store:
            new = self.threshold_review(store, new_packet, window(), '1/4')
        return old, new, old_packet, new_packet

    def test_read_after_correction(self):
        old, new, old_packet, new_packet = self.publish_history()
        self.assertNotEqual(old.number, new.number)
        with self.reports(initialize=False) as store:
            for report, parent, threshold in [(old, old_packet.ref, F(1, 2)), (new, new_packet.ref, F(1, 4))]:
                with self.subTest(number=report.number):
                    received = receive_threshold_review(store, report.number)
                    self.assertEqual(received, report)
                    self.assertEqual(received.draft.parent, parent)
                    self.assertEqual(received.draft.selected, F(1))
                    self.assertEqual(received.draft.threshold, threshold)
                    self.assertIs(threshold_allows(received, threshold), True)

    def test_reinitialize_keeps_everything(self):
        old, new, _, _ = self.publish_history()
        with self.reports(initialize=False) as store:
            store.initialize()
            store.initialize()
            self.assertEqual(receive_threshold_review(store, old.number), old)
            self.assertEqual(receive_threshold_review(store, new.number), new)
            self.assertEqual(count_rows(store.db, 'threshold_reports'), 2)
            self.assertEqual(count_rows(store.db, 'threshold_receipts'), 2)


class TestQuadraticRoot(unittest.TestCase):
    def test_normalization(self):
        root = make_quadratic_root(1, -2, '1/2', 'low')
        self.assertEqual(root, QuadraticRoot(F(2), F(-4), F(1), 'low'))
        self.assertEqual(root, make_quadratic_root('-2', 4, -1, 'low'))
        self.assertEqual(root, make_quadratic_root(F(4, 2), -4, 1, 'low'))

    def test_invalid_coefficients(self):
        for args in [(0, 1, 1, 'low'), (1, 0, 1, 'low'), (1, -3, 2, 'low'),
                     (1, -2, '1/2', 'mid'), (1, -2, '1/2', None)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                make_quadratic_root(*args)
        with self.assertRaises(ValueError):
            QuadraticRoot(F(1), F(0), F(1), 'low')
        with self.assertRaises(ValueError):
            QuadraticRoot(F(1), F(-3), F(2), 'low')

    def test_root_out_of_range(self):
        with self.assertRaisesRegex(ValueError, '闭量程'):
            make_quadratic_root(1, -4, 1, 'high')
        self.assertEqual(make_quadratic_root(1, -4, 1, 'low'),
                         QuadraticRoot(F(1), F(-4), F(1), 'low'))

    def test_compare_root(self):
        root = make_quadratic_root(2, -4, 1, 'low')
        self.assertEqual(compare_root(root, F(29, 100)), 1)
        self.assertEqual(compare_root(root, F(3, 10)), -1)
        self.assertEqual(compare_root(root, F(0)), 1)
        self.assertEqual(compare_root(root, F(1)), -1)
        high = make_quadratic_root(2, -2, F(1, 4), 'high')
        self.assertEqual(compare_root(high, F(4, 5)), 1)
        self.assertEqual(compare_root(high, F(9, 10)), -1)
        with self.assertRaises(ValueError):
            compare_root(root, '1/2')

    def test_validate_threshold_report(self):
        packet_window = ReviewWindow(F(0), F(1), True, True)
        from issue.packet import PacketRef
        parent = PacketRef('0' * 64, 'B', 1, 1)
        with self.assertRaises(ValueError):
            validate_threshold_report(ThresholdDraft(parent, packet_window, F(1, 2), F(0), F(1)))
        with self.assertRaises(ValueError):
            validate_threshold_report(ThresholdDraft(parent, packet_window, F(1, 2), F(1), None))
        with self.assertRaises(ValueError):
            validate_threshold_report(ThresholdDraft(parent, packet_window, F(5, 4), F(1), F(1)))
        with self.assertRaises(ValueError):
            validate_threshold_report(ThresholdDraft(parent, packet_window, F(1, 2), F(1), F(3, 2)))
        validate_threshold_report(ThresholdDraft(parent, packet_window, F(1, 2), F(0), None))


if __name__ == '__main__':
    unittest.main()
