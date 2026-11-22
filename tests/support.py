import sqlite3
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.batches import BatchArchive
from archive.revisions import RevisionStore
from calibration.response import CalibrationStore
from delivery.transactions import ReportStore
from issue.catalog import IssueCatalog
from issue.packet import encode_packet
from issue.publication import issue_packet
from review.requests import submit_review


def observation(name='m1', raw=(0, 0), reference=(0, 0)):
    return {'name': name, 'raw': raw, 'reference': reference}


def scenario(a=(2, 0, 0), b=(1, 0, 0), *, name='s1', weight=1, vertices=((0, 0), (1, 0), (0, 1))):
    return {'name': name, 'vertices': vertices, 'weight': weight, 'a': a, 'b': b}


def window(low=0, high=1, *, include_low=True, include_high=True):
    return {'low': low, 'high': high, 'include_low': include_low, 'include_high': include_high}


def count_rows(db, table):
    return db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]


class ProjectCase(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.station_path = Path(folder) / 'station.sqlite3'
        self.report_path = Path(folder) / 'reports.sqlite3'

    @contextmanager
    def station(self, *, initialize=True):
        with closing(sqlite3.connect(self.station_path)) as db:
            db.execute('PRAGMA foreign_keys = ON')
            revisions = RevisionStore(db)
            calibrations = CalibrationStore(db, revisions)
            catalog = IssueCatalog(db)
            if initialize:
                revisions.initialize()
                calibrations.initialize()
                catalog.initialize()
            yield db, revisions, calibrations, catalog

    @contextmanager
    def reports(self, *, initialize=True):
        with closing(sqlite3.connect(self.report_path)) as db:
            db.execute('PRAGMA foreign_keys = ON')
            store = ReportStore(db)
            if initialize:
                store.initialize()
            yield store

    def packet(self, inputs=None, *, batch='CG-041'):
        with self.station() as (_, revisions, calibrations, catalog):
            ref = BatchArchive(revisions).submit(batch, [observation()])
            calibration = calibrations.register(ref, [scenario()] if inputs is None else inputs)
            return issue_packet(calibrations, catalog, batch=batch,
                                calibration_id=calibration.number, version=calibration.version)

    def review(self, store, packet, bounds, threshold, *, batch=None, packet_id=None):
        return submit_review(
            store,
            batch=packet.ref.batch if batch is None else batch,
            packet_id=packet.ref.packet_id if packet_id is None else packet_id,
            packet_text=encode_packet(packet), window=bounds, threshold=threshold,
        )

    def assert_masses(self, report, selected, passed, rate, *, msg=None):
        draft = report.draft
        self.assertEqual((draft.selected, draft.passed, draft.rate), (selected, passed, rate), msg)
