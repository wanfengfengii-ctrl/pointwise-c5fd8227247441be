import json
import sqlite3
from dataclasses import dataclass
from fractions import Fraction

from archive.observations import validate_label, validate_number
from archive.queries import get_revision
from archive.rationals import encode_rational, parse_rational
from archive.revisions import Revision, RevisionRef, RevisionStore
from calibration.geometry import AffineForm, Point
from calibration.range import clamp_reading
from calibration.scenarios import Scenario, normalize_scenarios


@dataclass(frozen=True)
class CalibratedScenario:
    scenario: Scenario
    a: AffineForm
    b: AffineForm

    def as_input(self) -> dict:
        return {
            **self.scenario.as_input(),
            'a': _encode_form(self.a),
            'b': _encode_form(self.b),
        }


@dataclass(frozen=True)
class CalibrationRecord:
    number: int
    revision: RevisionRef
    scenarios: tuple[CalibratedScenario, ...]

    @property
    def version(self) -> int:
        return self.revision.number


def _parse_form(value: object) -> AffineForm:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError('通道响应须给出 u 系数、v 系数和常数项')
    u, v, constant = (parse_rational(part) for part in value)
    return AffineForm(u, v, constant)


def _encode_form(form: AffineForm) -> list[str]:
    return [encode_rational(value) for value in (form.u, form.v, form.constant)]


def _at_origin(form: AffineForm, origin: Point, adjustment: Fraction) -> AffineForm:
    u0, v0 = origin
    constant = form.constant + adjustment - form.u * u0 - form.v * v0
    return AffineForm(form.u, form.v, constant)


def _calibrate(revision: Revision, inputs) -> tuple[CalibratedScenario, ...]:
    scenarios = normalize_scenarios(inputs)
    entries = {entry['name']: entry for entry in inputs}
    observations = {record.name: record for record in revision.observations}
    anchors = {anchor.name: anchor for anchor in revision.scenario_inputs}
    required = {'name', 'vertices', 'weight', 'a', 'b'}
    models = []
    for scenario in scenarios:
        entry = entries[scenario.name]
        if not required <= entry.keys() or entry.keys() - required - {'anchor'}:
            raise ValueError('校准情景须给出双通道响应，且只可附一个情景锚点')
        a, b = _parse_form(entry['a']), _parse_form(entry['b'])
        if 'anchor' in entry:
            name = validate_label(entry['anchor'], '情景锚点引用')
            anchor = anchors.get(name)
            if anchor is None:
                raise ValueError(f'指定修订缺少情景锚点 {name!r}')
            record = observations[anchor.observation]
            a = _at_origin(a, anchor.origin, record.reference[0] - record.raw[0])
            b = _at_origin(b, anchor.origin, record.reference[1] - record.raw[1])
        models.append(CalibratedScenario(scenario, a, b))
    return tuple(models)


def evaluate_pair(model: CalibratedScenario, point: Point) -> Point:
    return clamp_reading(model.a.evaluate(point)), clamp_reading(model.b.evaluate(point))


class CalibrationStore:
    def __init__(self, db: sqlite3.Connection, revisions: RevisionStore):
        if revisions.db is not db:
            raise ValueError('归档和校准须使用同一站库连接')
        self.db = db
        self.revisions = revisions

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS calibrations (
                number INTEGER PRIMARY KEY,
                batch TEXT NOT NULL,
                revision INTEGER NOT NULL,
                model TEXT NOT NULL,
                FOREIGN KEY (batch, revision) REFERENCES revisions (batch, revision)
            )
        ''')

    def register(self, ref: RevisionRef, inputs) -> CalibrationRecord:
        revision = get_revision(self.revisions, ref)
        if revision is None:
            raise ValueError('指定校准修订不存在')
        models = _calibrate(revision, inputs)
        payload = json.dumps([model.as_input() for model in models], ensure_ascii=False, sort_keys=True)
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            cursor = self.db.execute('''
                INSERT INTO calibrations (batch, revision, model) VALUES (?, ?, ?)
            ''', (revision.ref.batch, revision.ref.number, payload))
            record = CalibrationRecord(cursor.lastrowid, revision.ref, models)
        return record

    def read_exact(self, batch: str, number: int, version: int) -> CalibrationRecord | None:
        validate_label(batch, '批次')
        validate_number(number, '校准号')
        validate_number(version, '校准版本')
        row = self.db.execute('''
            SELECT model FROM calibrations WHERE batch = ? AND number = ? AND revision = ?
        ''', (batch, number, version)).fetchone()
        if row is None:
            return None
        inputs = json.loads(row[0])
        entries = {entry['name']: entry for entry in inputs}
        models = tuple(
            CalibratedScenario(scenario, _parse_form(entries[scenario.name]['a']), _parse_form(entries[scenario.name]['b']))
            for scenario in normalize_scenarios(inputs)
        )
        return CalibrationRecord(number, RevisionRef(batch, version), models)
