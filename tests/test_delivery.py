import sqlite3
from fractions import Fraction as F

from archive.batches import BatchArchive
from archive.queries import get_current_revision, get_revision
from archive.revisions import RevisionRef
from delivery.export import export_handoff
from delivery.readback import ReportNotFound, receive_report
from issue.publication import issue_packet
from tests.support import ProjectCase, count_rows, observation, scenario, window


class TestDelivery(ProjectCase):
    def publish_history(self):
        batch = 'CG-041'
        with self.station() as (_, revisions, calibrations, catalog):
            first = BatchArchive(revisions).submit(batch, [observation(raw=('1/9', 0))])
            old_calibration = calibrations.register(first, [scenario()])
            old_packet = issue_packet(calibrations, catalog, batch=batch,
                                      calibration_id=old_calibration.number, version=first.number)
        with self.reports() as store:
            old = self.review(store, old_packet, window(), '1/3')
        with self.station(initialize=False) as (_, revisions, calibrations, catalog):
            second = BatchArchive(revisions).correct(first, [observation(raw=('2/9', 0))])
            new_calibration = calibrations.register(second, [scenario(b=('1/2', 0, 0))])
            new_packet = issue_packet(calibrations, catalog, batch=batch,
                                      calibration_id=new_calibration.number, version=second.number)
        with self.reports(initialize=False) as store:
            new = self.review(store, new_packet, window(), '1/3')
        return old, new, old_packet, new_packet

    def test_read_after_correction(self):
        old, new, old_packet, new_packet = self.publish_history()
        self.assertNotEqual(old.number, new.number)
        self.assertNotEqual(old_packet.ref.packet_id, new_packet.ref.packet_id)
        self.assertEqual((old_packet.ref.revision, new_packet.ref.revision), (1, 2))
        with self.reports(initialize=False) as store:
            for original, parent, expected in [(new, new_packet.ref, F(1, 9)), (old, old_packet.ref, F(4, 9))]:
                with self.subTest(number=original.number):
                    received = receive_report(store, original.number)
                    self.assertEqual(received, original)
                    self.assertEqual(received.draft.parent, parent)
                    self.assert_masses(received, F(1), expected, expected)
                    self.assertEqual(received.draft.threshold, F(1, 3))
                    handoff = export_handoff(received)
                    self.assertEqual(handoff['parent'], parent.as_dict())
                    self.assertEqual(handoff['window'], window('0', '1'))
                    self.assertEqual((handoff['passed'], handoff['rate']), (str(expected), str(expected)))
            receipts = store.db.execute('SELECT report_number FROM receipts ORDER BY number').fetchall()
            self.assertEqual(receipts, [(new.number,), (old.number,)])

    def test_unknown_number(self):
        _, latest, _, _ = self.publish_history()
        with self.reports(initialize=False) as store:
            with self.assertRaisesRegex(ReportNotFound, '未找到'):
                receive_report(store, latest.number + 1)
            self.assertEqual(count_rows(store.db, 'receipts'), 0)

    def test_reinitialize(self):
        old, new, old_packet, new_packet = self.publish_history()
        with self.reports(initialize=False) as store:
            self.assertEqual(receive_report(store, old.number), old)
            self.assertEqual(receive_report(store, new.number), new)
            store.initialize()
            store.initialize()
        with self.station() as (_, revisions, calibrations, catalog):
            revisions.initialize()
            calibrations.initialize()
            catalog.initialize()
        with self.station(initialize=False) as (db, revisions, calibrations, catalog):
            self.assertEqual(count_rows(db, 'revisions'), 2)
            self.assertEqual(count_rows(db, 'calibrations'), 2)
            self.assertEqual(count_rows(db, 'packets'), 2)
            self.assertEqual(get_current_revision(revisions, new_packet.ref.batch).ref.number, 2)
            for packet, raw in [(old_packet, F(1, 9)), (new_packet, F(2, 9))]:
                ref = packet.ref
                self.assertEqual(catalog.get(ref.packet_id), packet)
                self.assertEqual(get_revision(revisions, RevisionRef(ref.batch, ref.revision)).observations[0].raw[0], raw)
                self.assertIsNotNone(calibrations.read_exact(ref.batch, ref.calibration_id, ref.revision))
        with self.reports(initialize=False) as store:
            self.assertEqual(count_rows(store.db, 'reports'), 2)
            self.assertEqual(count_rows(store.db, 'receipts'), 2)
            self.assertEqual(store.read_signed(old.number), old)
            self.assertEqual(store.read_signed(new.number), new)
            self.assertEqual(store.db.execute('SELECT report_number FROM receipts ORDER BY number').fetchall(),
                             [(old.number,), (new.number,)])

    def test_failed_commit(self):
        packet = self.packet()
        with self.reports() as store:
            existing = self.review(store, packet, window(), 0)
            # The deferred constraint fires at the actual SQLite commit, after the report insert.
            store.db.executescript('''
                CREATE TABLE test_authorized (number INTEGER PRIMARY KEY);
                CREATE TABLE test_commit_guard (
                    number INTEGER REFERENCES test_authorized (number) DEFERRABLE INITIALLY DEFERRED
                );
                CREATE TRIGGER test_guard_after_report AFTER INSERT ON reports BEGIN
                    INSERT INTO test_commit_guard (number) VALUES (NEW.number);
                END;
            ''')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
                self.review(store, packet, window(1, 1), '3/4')
        with self.reports(initialize=False) as store:
            self.assertEqual(count_rows(store.db, 'reports'), 1)
            self.assertEqual(count_rows(store.db, 'test_commit_guard'), 0)
            self.assertIsNone(store.read_signed(existing.number + 1))
            self.assertEqual(receive_report(store, existing.number), existing)
            store.db.execute('DROP TRIGGER test_guard_after_report')
            retry = self.review(store, packet, window(1, 1), '3/4')
        with self.reports(initialize=False) as store:
            self.assertEqual(count_rows(store.db, 'reports'), 2)
            received = receive_report(store, retry.number)
            self.assertEqual(received.draft.parent, packet.ref)
            self.assert_masses(received, F(1, 4), F(1, 16), F(1, 4))
