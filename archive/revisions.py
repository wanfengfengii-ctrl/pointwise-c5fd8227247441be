import json
import sqlite3
from dataclasses import dataclass

from archive.observations import (
    Observation,
    ScenarioInput,
    parse_observations,
    parse_scenario_inputs,
    validate_label,
    validate_number,
)


@dataclass(frozen=True)
class RevisionRef:
    batch: str
    number: int

    def __post_init__(self) -> None:
        validate_label(self.batch, '批次')
        validate_number(self.number, '修订号')


@dataclass(frozen=True)
class Revision:
    ref: RevisionRef
    parent: int | None
    observations: tuple[Observation, ...]
    scenario_inputs: tuple[ScenarioInput, ...]


def _decode(row) -> Revision | None:
    if row is None:
        return None
    batch, number, parent, text = row
    payload = json.loads(text)
    observations = parse_observations(payload['observations'])
    scenario_inputs = parse_scenario_inputs(payload['scenario_inputs'], observations)
    return Revision(RevisionRef(batch, number), parent, observations, scenario_inputs)


class RevisionStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('BEGIN')
        with self.db:
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS revisions (
                    batch TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    parent INTEGER,
                    snapshot TEXT NOT NULL,
                    PRIMARY KEY (batch, revision),
                    FOREIGN KEY (batch, parent) REFERENCES revisions (batch, revision)
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS batch_heads (
                    batch TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    FOREIGN KEY (batch, revision) REFERENCES revisions (batch, revision)
                )
            ''')

    def append(self, batch: str, observations, scenario_inputs=(), *, parent: int | None = None) -> RevisionRef:
        validate_label(batch, '批次')
        if parent is not None:
            validate_number(parent, '勘误父修订号')
        records = parse_observations(observations)
        anchors = parse_scenario_inputs(scenario_inputs, records)
        payload = json.dumps({
            'observations': [record.as_input() for record in records],
            'scenario_inputs': [anchor.as_input() for anchor in anchors],
        }, ensure_ascii=False, sort_keys=True)

        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            head = self.db.execute(
                'SELECT revision FROM batch_heads WHERE batch = ?', (batch,)
            ).fetchone()
            current = None if head is None else head[0]
            if current != parent:
                raise ValueError('批次已存在或勘误父版与当前修订失配')
            ref = RevisionRef(batch, 1 if current is None else current + 1)
            self.db.execute('''
                INSERT INTO revisions (batch, revision, parent, snapshot) VALUES (?, ?, ?, ?)
            ''', (batch, ref.number, parent, payload))
            self.db.execute('''
                INSERT INTO batch_heads (batch, revision) VALUES (?, ?)
                ON CONFLICT (batch) DO UPDATE SET revision = excluded.revision
            ''', (batch, ref.number))
        return ref

    def read_exact(self, ref: RevisionRef) -> Revision | None:
        row = self.db.execute('''
            SELECT batch, revision, parent, snapshot FROM revisions
            WHERE batch = ? AND revision = ?
        ''', (ref.batch, ref.number)).fetchone()
        return _decode(row)

    def read_current(self, batch: str) -> Revision | None:
        validate_label(batch, '批次')
        row = self.db.execute('''
            SELECT r.batch, r.revision, r.parent, r.snapshot
            FROM batch_heads AS h JOIN revisions AS r
              ON r.batch = h.batch AND r.revision = h.revision
            WHERE h.batch = ?
        ''', (batch,)).fetchone()
        return _decode(row)
