import sqlite3
from fractions import Fraction

from archive.observations import validate_number
from archive.rationals import encode_rational, parse_rational
from delivery.reports import (
    ReportDraft,
    SignedReport,
    SignedThresholdReport,
    ThresholdDraft,
    validate_report,
    validate_threshold_report,
)
from issue.packet import PacketRef
from review.roots import make_quadratic_root
from review.windows import ReviewWindow


_REPORT_COLUMNS = '''
    packet_id, batch, calibration_id, revision,
    window_low, window_high, include_low, include_high, threshold,
    selected, passed, rate, status
'''

_THRESHOLD_COLUMNS = '''
    packet_id, batch, calibration_id, revision,
    window_low, window_high, include_low, include_high,
    minimum_rate, selected, status,
    threshold_kind, threshold, quad_a, quad_b, quad_c, quad_root
'''


def _values(draft: ReportDraft) -> tuple:
    parent = draft.parent
    window = draft.window
    return (
        parent.packet_id, parent.batch, parent.calibration_id, parent.revision,
        encode_rational(window.low), encode_rational(window.high),
        int(window.include_low), int(window.include_high), encode_rational(draft.threshold),
        encode_rational(draft.selected), encode_rational(draft.passed),
        None if draft.rate is None else encode_rational(draft.rate), draft.status,
    )


def _read_draft(row) -> ReportDraft:
    (packet_id, batch, calibration_id, revision, low, high, include_low, include_high,
     threshold, selected, passed, rate, status) = row
    window = ReviewWindow(parse_rational(low), parse_rational(high), bool(include_low), bool(include_high))
    draft = ReportDraft(
        PacketRef(packet_id, batch, calibration_id, revision), window, parse_rational(threshold),
        parse_rational(selected), parse_rational(passed), None if rate is None else parse_rational(rate),
    )
    validate_report(draft)
    if draft.status != status:
        raise ValueError('已签状态与报告快照失配')
    return draft


def _threshold_values(draft: ThresholdDraft) -> tuple:
    parent = draft.parent
    window = draft.window
    threshold = draft.threshold
    if threshold is None:
        kind, text, quad = 'none', None, (None, None, None, None)
    elif isinstance(threshold, Fraction):
        kind, text, quad = 'rational', encode_rational(threshold), (None, None, None, None)
    else:
        kind, text = 'quadratic', None
        quad = (encode_rational(threshold.a), encode_rational(threshold.b),
                encode_rational(threshold.c), threshold.root)
    return (
        parent.packet_id, parent.batch, parent.calibration_id, parent.revision,
        encode_rational(window.low), encode_rational(window.high),
        int(window.include_low), int(window.include_high),
        encode_rational(draft.minimum_rate), encode_rational(draft.selected), draft.status,
        kind, text, *quad,
    )


def _read_threshold_draft(row) -> ThresholdDraft:
    (packet_id, batch, calibration_id, revision, low, high, include_low, include_high,
     minimum_rate, selected, status, kind, threshold, quad_a, quad_b, quad_c, quad_root) = row
    window = ReviewWindow(parse_rational(low), parse_rational(high), bool(include_low), bool(include_high))
    if kind == 'none':
        value = None
    elif kind == 'rational':
        value = parse_rational(threshold)
    elif kind == 'quadratic':
        value = make_quadratic_root(quad_a, quad_b, quad_c, quad_root)
    else:
        raise ValueError('已签门槛类别非法')
    draft = ThresholdDraft(
        PacketRef(packet_id, batch, calibration_id, revision), window,
        parse_rational(minimum_rate), parse_rational(selected), value,
    )
    validate_threshold_report(draft)
    if draft.status != status:
        raise ValueError('已签状态与反查报告快照失配')
    return draft


class ReportStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('BEGIN')
        with self.db:
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    number INTEGER PRIMARY KEY,
                    packet_id TEXT NOT NULL,
                    batch TEXT NOT NULL,
                    calibration_id INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    window_low TEXT NOT NULL,
                    window_high TEXT NOT NULL,
                    include_low INTEGER NOT NULL CHECK (include_low IN (0, 1)),
                    include_high INTEGER NOT NULL CHECK (include_high IN (0, 1)),
                    threshold TEXT NOT NULL,
                    selected TEXT NOT NULL,
                    passed TEXT NOT NULL,
                    rate TEXT,
                    status TEXT NOT NULL CHECK (
                        (status = 'no_evidence' AND rate IS NULL) OR
                        (status = 'measured' AND rate IS NOT NULL)
                    )
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS receipts (
                    number INTEGER PRIMARY KEY,
                    report_number INTEGER NOT NULL REFERENCES reports (number)
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS threshold_reports (
                    number INTEGER PRIMARY KEY,
                    packet_id TEXT NOT NULL,
                    batch TEXT NOT NULL,
                    calibration_id INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    window_low TEXT NOT NULL,
                    window_high TEXT NOT NULL,
                    include_low INTEGER NOT NULL CHECK (include_low IN (0, 1)),
                    include_high INTEGER NOT NULL CHECK (include_high IN (0, 1)),
                    minimum_rate TEXT NOT NULL,
                    selected TEXT NOT NULL,
                    status TEXT NOT NULL,
                    threshold_kind TEXT NOT NULL CHECK (threshold_kind IN ('none', 'rational', 'quadratic')),
                    threshold TEXT,
                    quad_a TEXT,
                    quad_b TEXT,
                    quad_c TEXT,
                    quad_root TEXT,
                    CHECK (
                        (threshold_kind = 'none' AND threshold IS NULL AND quad_a IS NULL
                         AND quad_b IS NULL AND quad_c IS NULL AND quad_root IS NULL) OR
                        (threshold_kind = 'rational' AND threshold IS NOT NULL AND quad_a IS NULL
                         AND quad_b IS NULL AND quad_c IS NULL AND quad_root IS NULL) OR
                        (threshold_kind = 'quadratic' AND threshold IS NULL AND quad_a IS NOT NULL
                         AND quad_b IS NOT NULL AND quad_c IS NOT NULL AND quad_root IN ('low', 'high'))
                    ),
                    CHECK (
                        (status = 'no_evidence' AND threshold_kind = 'none') OR
                        (status = 'measured' AND threshold_kind IN ('rational', 'quadratic'))
                    )
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS threshold_receipts (
                    number INTEGER PRIMARY KEY,
                    report_number INTEGER NOT NULL REFERENCES threshold_reports (number)
                )
            ''')

    def publish(self, draft: ReportDraft) -> SignedReport:
        validate_report(draft)
        values = _values(draft)
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            cursor = self.db.execute(f'''
                INSERT INTO reports ({_REPORT_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', values)
            signed = SignedReport(cursor.lastrowid, draft)
        return signed

    def read_signed(self, number: int) -> SignedReport | None:
        validate_number(number, '报告号')
        row = self.db.execute(
            f'SELECT {_REPORT_COLUMNS} FROM reports WHERE number = ?', (number,)
        ).fetchone()
        if row is None:
            return None
        return SignedReport(number, _read_draft(row))

    def record_receipt(self, number: int) -> int:
        validate_number(number, '报告号')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            cursor = self.db.execute('''
                INSERT INTO receipts (report_number) SELECT number FROM reports WHERE number = ?
            ''', (number,))
            if cursor.rowcount != 1:
                raise ValueError('无法登记未知报告号的领取记录')
            receipt = cursor.lastrowid
        return receipt

    def publish_threshold(self, draft: ThresholdDraft) -> SignedThresholdReport:
        validate_threshold_report(draft)
        values = _threshold_values(draft)
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            cursor = self.db.execute(f'''
                INSERT INTO threshold_reports ({_THRESHOLD_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', values)
            signed = SignedThresholdReport(cursor.lastrowid, draft)
        return signed

    def read_threshold(self, number: int) -> SignedThresholdReport | None:
        validate_number(number, '反查报告号')
        row = self.db.execute(
            f'SELECT {_THRESHOLD_COLUMNS} FROM threshold_reports WHERE number = ?', (number,)
        ).fetchone()
        if row is None:
            return None
        return SignedThresholdReport(number, _read_threshold_draft(row))

    def record_threshold_receipt(self, number: int) -> int:
        validate_number(number, '反查报告号')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            cursor = self.db.execute('''
                INSERT INTO threshold_receipts (report_number)
                SELECT number FROM threshold_reports WHERE number = ?
            ''', (number,))
            if cursor.rowcount != 1:
                raise ValueError('无法登记未知反查报告号的领取记录')
            receipt = cursor.lastrowid
        return receipt
