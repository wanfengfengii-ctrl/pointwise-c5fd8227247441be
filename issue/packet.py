import hashlib
import json
import re
from dataclasses import dataclass
from fractions import Fraction

from archive.observations import validate_label, validate_number
from archive.rationals import encode_rational, parse_rational
from issue.pieces import EvidencePiece, validate_evidence


@dataclass(frozen=True)
class PacketRef:
    packet_id: str
    batch: str
    calibration_id: int
    revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.packet_id, str) or re.fullmatch(r'[0-9a-f]{64}', self.packet_id) is None:
            raise ValueError('固定件号格式非法')
        validate_label(self.batch, '来源批次')
        validate_number(self.calibration_id, '来源校准号')
        validate_number(self.revision, '来源修订号')

    def as_dict(self) -> dict:
        return {
            'packet_id': self.packet_id,
            'batch': self.batch,
            'calibration_id': self.calibration_id,
            'revision': self.revision,
        }


@dataclass(frozen=True)
class IssuedPacket:
    ref: PacketRef
    pieces: tuple[EvidencePiece, ...]


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def _body(pieces: tuple[EvidencePiece, ...]) -> list[dict]:
    validate_evidence(pieces)
    return [
        {
            'mass': encode_rational(piece.mass),
            'vertices': [[encode_rational(x), encode_rational(y)] for x, y in piece.vertices],
        }
        for piece in pieces
    ]


def _identity(source: dict, body: list[dict]) -> str:
    material = {'version': 1, 'source': source, 'evidence': body}
    return hashlib.sha256(_dump(material).encode('ascii')).hexdigest()


def make_packet(batch: str, calibration_id: int, revision: int, pieces: tuple[EvidencePiece, ...]) -> IssuedPacket:
    source = {'batch': batch, 'calibration_id': calibration_id, 'revision': revision}
    packet_id = _identity(source, _body(pieces))
    return IssuedPacket(PacketRef(packet_id, batch, calibration_id, revision), pieces)


def _check_identity(ref: PacketRef, body: list[dict]) -> None:
    source = ref.as_dict()
    packet_id = source.pop('packet_id')
    if _identity(source, body) != packet_id:
        raise ValueError('固定件号与实际来源或证据不匹配')


def encode_packet(packet: IssuedPacket) -> str:
    body = _body(packet.pieces)
    _check_identity(packet.ref, body)
    return _dump({'version': 1, 'source': packet.ref.as_dict(), 'evidence': body})


def _unique_fields(items: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f'固定件包含重复字段 {key!r}')
        result[key] = value
    return result


def _read_fraction(raw: object) -> Fraction:
    if not isinstance(raw, str):
        raise ValueError('固定件数值须采用精确有理文本')
    value = parse_rational(raw)
    if encode_rational(value) != raw:
        raise ValueError('固定件数值须采用约分形式')
    return value


def _read_piece(raw: object) -> EvidencePiece:
    if not isinstance(raw, dict) or set(raw) != {'mass', 'vertices'}:
        raise ValueError('证据片字段非法')
    vertices = raw['vertices']
    if not isinstance(vertices, list) or len(vertices) != 3:
        raise ValueError('证据片须有三个输出顶点')
    points = []
    for point in vertices:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError('输出顶点须有甲乙两项')
        points.append((_read_fraction(point[0]), _read_fraction(point[1])))
    a, b, c = points
    return EvidencePiece(_read_fraction(raw['mass']), (a, b, c))


def decode_packet(text: str) -> IssuedPacket:
    if not isinstance(text, str):
        raise ValueError('固定件须为 JSON 文本')
    payload = json.loads(text, object_pairs_hook=_unique_fields)
    if not isinstance(payload, dict) or set(payload) != {'version', 'source', 'evidence'}:
        raise ValueError('固定件外层字段非法')
    if type(payload['version']) is not int or payload['version'] != 1:
        raise ValueError('不支持的固定件版本')
    source, body = payload['source'], payload['evidence']
    if not isinstance(source, dict) or set(source) != {'packet_id', 'batch', 'calibration_id', 'revision'}:
        raise ValueError('固定件来源字段非法')
    ref = PacketRef(**source)
    if not isinstance(body, list):
        raise ValueError('固定件证据须为数组')
    pieces = tuple(_read_piece(raw) for raw in body)
    validate_evidence(pieces)
    _check_identity(ref, body)
    return IssuedPacket(ref, pieces)
