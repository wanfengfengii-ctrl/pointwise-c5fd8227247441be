import sqlite3

from issue.packet import IssuedPacket, decode_packet, encode_packet


class IssueCatalog:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('BEGIN')
        with self.db:
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS packets (
                    packet_id TEXT PRIMARY KEY,
                    batch TEXT NOT NULL,
                    calibration_id INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY (calibration_id) REFERENCES calibrations (number),
                    FOREIGN KEY (batch, revision) REFERENCES revisions (batch, revision)
                )
            ''')
            self.db.execute('''
                CREATE INDEX IF NOT EXISTS packet_source ON packets (batch, calibration_id, revision)
            ''')

    def store(self, packet: IssuedPacket) -> None:
        text = encode_packet(packet)
        ref = packet.ref
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            self.db.execute('''
                INSERT INTO packets (packet_id, batch, calibration_id, revision, payload)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT (packet_id) DO NOTHING
            ''', (ref.packet_id, ref.batch, ref.calibration_id, ref.revision, text))
            saved = self.db.execute('SELECT payload FROM packets WHERE packet_id = ?', (ref.packet_id,)).fetchone()
            if saved[0] != text:
                raise ValueError('同号固定件已登记不同正文')

    def get(self, packet_id: str) -> IssuedPacket | None:
        row = self.db.execute('''
            SELECT batch, calibration_id, revision, payload FROM packets WHERE packet_id = ?
        ''', (packet_id,)).fetchone()
        if row is None:
            return None
        batch, calibration, revision, text = row
        packet = decode_packet(text)
        ref = packet.ref
        if (ref.packet_id, ref.batch, ref.calibration_id, ref.revision) != (packet_id, batch, calibration, revision):
            raise ValueError('固定件正文与发行索引失配')
        return packet
