from calibration.response import CalibrationStore
from issue.catalog import IssueCatalog
from issue.evidence import build_evidence
from issue.packet import IssuedPacket, make_packet


def issue_packet(calibrations: CalibrationStore, catalog: IssueCatalog, *, batch: str, calibration_id: int,
                 version: int) -> IssuedPacket:
    if calibrations.db is not catalog.db:
        raise ValueError('校准和发行目录须使用同一站库连接')
    calibration = calibrations.read_exact(batch, calibration_id, version)
    if calibration is None:
        raise ValueError('固定件请求与确切校准绑定失配')
    source = calibration.revision
    packet = make_packet(source.batch, calibration.number, source.number, build_evidence(calibration))
    catalog.store(packet)
    return packet
