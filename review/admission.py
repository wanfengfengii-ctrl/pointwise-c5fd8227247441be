from archive.observations import validate_label
from issue.packet import IssuedPacket, decode_packet


def admit_packet(batch: str, packet_id: str, packet_text: str) -> IssuedPacket:
    validate_label(batch, '预期批次')
    validate_label(packet_id, '指定固定件号')
    packet = decode_packet(packet_text)
    if packet.ref.batch != batch or packet.ref.packet_id != packet_id:
        raise ValueError('指定父件或预期批次与导入件失配')
    return packet
