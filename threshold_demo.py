"""乙门槛反查演示：固定件断源签发、重开领取、凭领回报告核对设点（见 THRESHOLD.md）。

先完整运行 V1 演示，再在关站后仅凭固定件正文签出反查报告，
重开报告库按号领取，并仅凭领回报告核对拟用设点。
"""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import run_demo
from delivery.export import export_threshold_handoff
from delivery.readback import receive_threshold_review, threshold_allows
from delivery.transactions import ReportStore
from review.requests import submit_threshold_review
from threshold_examples import CUT_WINDOW, EMPTY_WINDOW, FULL_SCALE, example_packets


# (样例, 甲窗, 通过率底线, 拟核对设点)
CASES = (
    ('continuous', FULL_SCALE, '1/2', ('29/100', '73/250', '3/10')),
    ('plateau', FULL_SCALE, '1/2', ('1/2', '3/4', '4/5')),
    ('two-roots', FULL_SCALE, '1/2', ('3/10', '2/5')),
    ('window-cut', CUT_WINDOW, '1/20', ('5/8', '2/3')),
    ('continuous', EMPTY_WINDOW, 0, ('1/2',)),
)


def main():
    run_demo.main()
    packets = example_packets()  # 站库随发行结束关闭，此后仅凭固定件正文作业
    with TemporaryDirectory(prefix='optical-threshold-') as folder:
        report_path = Path(folder) / 'reports.sqlite3'
        signed = []
        with closing(sqlite3.connect(report_path)) as db:
            # 断源签发：站库已关闭，仅凭固定件正文和本次口径签出反查报告
            db.execute('PRAGMA foreign_keys = ON')
            store = ReportStore(db)
            store.initialize()
            for batch, bounds, rate, _ in CASES:
                ref, text = packets[batch]
                signed.append(submit_threshold_review(
                    store, batch=batch, packet_id=ref.packet_id, packet_text=text,
                    window=bounds, minimum_rate=rate))
        record = {'case_id': 'threshold-handoff', 'reports': []}
        with closing(sqlite3.connect(report_path)) as db:
            # 重开报告库，按号领取当时签定的反查报告
            store = ReportStore(db)
            for (batch, _, _, settings), report in zip(CASES, signed):
                received = receive_threshold_review(store, report.number)
                if received != report:
                    raise SystemExit(f'{batch} 重开领取与签发值失配')
                handoff = export_threshold_handoff(received)
                allows = {setting: threshold_allows(received, setting) for setting in settings}
                record['reports'].append({
                    'batch': batch,
                    'number': received.number,
                    'parent': handoff['parent'],
                    'window': handoff['window'],
                    'minimum_rate': handoff['minimum_rate'],
                    'selected': handoff['selected'],
                    'status': handoff['status'],
                    'threshold': handoff['threshold'],
                    'allows': allows,
                })
        # 报告库已关闭，以下仅凭领回值核对设点
        print('POINTWISE_THRESHOLD ' + json.dumps(record, ensure_ascii=False, sort_keys=True))
        for entry in record['reports']:
            print(json.dumps(entry, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
