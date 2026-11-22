from calibration.response import CalibrationRecord, evaluate_pair
from issue.partition import partition_scenario
from issue.pieces import EvidencePiece, validate_evidence


def build_evidence(calibration: CalibrationRecord) -> tuple[EvidencePiece, ...]:
    evidence = []
    for model in calibration.scenarios:
        weight = model.scenario.weight
        if not weight:
            continue
        for source in partition_scenario(model):
            a, b, c = source.vertices
            image = evaluate_pair(model, a), evaluate_pair(model, b), evaluate_pair(model, c)
            evidence.append(EvidencePiece(weight * source.area_fraction, image))
    pieces = tuple(evidence)
    validate_evidence(pieces)
    return pieces
