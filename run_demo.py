import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.batches import BatchArchive
from archive.revisions import RevisionStore
from calibration.response import CalibrationStore
from delivery.export import export_handoff
from delivery.readback import receive_report
from delivery.transactions import ReportStore
from issue.catalog import IssueCatalog
from issue.packet import encode_packet
from issue.publication import issue_packet
from review.requests import submit_review


def station_issue(path, sample, parent=None):
    with closing(sqlite3.connect(path)) as db:
        db.execute('PRAGMA foreign_keys = ON')
        revisions = RevisionStore(db)
        calibrations = CalibrationStore(db, revisions)
        catalog = IssueCatalog(db)
        revisions.initialize()
        calibrations.initialize()
        catalog.initialize()
        archive = BatchArchive(revisions)
        anchors = sample['scenario_inputs']
        if parent is None:
            ref = archive.submit(sample['batch'], sample['observations'], anchors)
        else:
            ref = archive.correct(parent, sample['corrected_observations'], anchors)
        model = calibrations.register(ref, sample['calibration'])
        packet = issue_packet(calibrations, catalog, batch=ref.batch, calibration_id=model.number, version=model.version)
        stored = catalog.get(packet.ref.packet_id)
        if stored != packet:
            raise RuntimeError('发行件无法按原号领取')
        return ref, stored.ref, encode_packet(stored)


def offline_sign(path, sample, ref, text):
    with closing(sqlite3.connect(path)) as db:
        db.execute('PRAGMA foreign_keys = ON')
        store = ReportStore(db)
        store.initialize()
        return submit_review(store, batch=sample['batch'], packet_id=ref.packet_id, packet_text=text, **sample['review'])


def check_handoff(signed, handoff, parent, expected, marker):
    actual = {key: handoff[key] for key in expected}
    if actual != expected or handoff['parent'] != parent.as_dict() or handoff['number'] != signed.number:
        raise SystemExit(f'{marker} 预期 {expected}，实得 {handoff}')
    return actual


def main():
    sample_path = Path(__file__).with_name('samples') / 'shift.json'
    sample = json.loads(sample_path.read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='optical-shift-') as folder:
        station = Path(folder) / 'station.sqlite3'
        reports = Path(folder) / 'reports.sqlite3'
        original, old_ref, old_text = station_issue(station, sample)
        old = offline_sign(reports, sample, old_ref, old_text)
        _, new_ref, new_text = station_issue(station, sample, original)
        new = offline_sign(reports, sample, new_ref, new_text)
        with closing(sqlite3.connect(reports)) as db:
            store = ReportStore(db)
            new_handoff = export_handoff(receive_report(store, new.number))
            old_handoff = export_handoff(receive_report(store, old.number))
    expected = {'selected': '1/4', 'passed': '1/16', 'rate': '1/4', 'status': 'measured'}
    actual = check_handoff(old, old_handoff, old_ref, expected, 'SATURATED_BAND')
    new_expected = {'selected': '1/4', 'passed': '0', 'rate': '0', 'status': 'measured'}
    check_handoff(new, new_handoff, new_ref, new_expected, 'CORRECTED_HANDOFF')
    record = {
        'case_id': 'v4',
        'input': {'batch': sample['batch'], 'scenario': sample['calibration'], 'review': sample['review'],
                  'observations': sample['observations'], 'scenario_inputs': sample['scenario_inputs']},
        'expected': expected,
        'actual': actual,
        'downstream_expected': {'number': old.number, 'parent': old_ref.as_dict(), **expected},
        'downstream_actual': {key: old_handoff[key] for key in ('number', 'parent', *expected)},
        'code_paths': ['issue/evidence.py', 'review/conditional.py', 'delivery/transactions.py', 'delivery/readback.py'],
        'oracle': '单位直角三角形满足 P(u≥t)=(1−t)²，代入 1/2 和 3/4 后以联合质量除以筛选质量。',
    }
    print('POINTWISE_SCENARIO ' + json.dumps(record, ensure_ascii=False, sort_keys=True))
    print(json.dumps(new_handoff, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
