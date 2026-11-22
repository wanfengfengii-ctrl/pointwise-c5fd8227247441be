from dataclasses import dataclass
from fractions import Fraction

from archive.rationals import encode_rational, parse_rational


Pair = tuple[Fraction, Fraction]


def validate_label(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{field}必须是非空文本且首尾无空白')
    return value


def validate_number(value: object, field: str) -> int:
    if type(value) is not int or not 0 < value < 2**63:
        raise ValueError(f'{field}必须是有效的正整数编号')
    return value


def parse_pair(value: object) -> Pair:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('必须给出两项有理值')
    first, second = value
    return parse_rational(first), parse_rational(second)


@dataclass(frozen=True)
class Observation:
    name: str
    raw: Pair
    reference: Pair

    def as_input(self) -> dict:
        return {
            'name': self.name,
            'raw': [encode_rational(value) for value in self.raw],
            'reference': [encode_rational(value) for value in self.reference],
        }


@dataclass(frozen=True)
class ScenarioInput:
    name: str
    observation: str
    origin: Pair

    def as_input(self) -> dict:
        return {
            'name': self.name,
            'observation': self.observation,
            'origin': [encode_rational(value) for value in self.origin],
        }


def parse_observations(values: object) -> tuple[Observation, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError('每个修订须包含至少一项具名原测')
    records = []
    names = set()
    for entry in values:
        if not isinstance(entry, dict) or set(entry) != {'name', 'raw', 'reference'}:
            raise ValueError('原测须包含 name、raw 和 reference')
        name = validate_label(entry['name'], '测次名')
        if name in names:
            raise ValueError(f'重复测次 {name!r}')
        names.add(name)
        records.append(Observation(name, parse_pair(entry['raw']), parse_pair(entry['reference'])))
    return tuple(sorted(records, key=lambda record: record.name))


def parse_scenario_inputs(values: object, observations: tuple[Observation, ...]) -> tuple[ScenarioInput, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError('情景输入须为数组')
    observation_names = {observation.name for observation in observations}
    names = set()
    records = []
    for entry in values:
        if not isinstance(entry, dict) or set(entry) != {'name', 'observation', 'origin'}:
            raise ValueError('情景锚点须包含 name、observation 和 origin')
        name = validate_label(entry['name'], '情景锚点名')
        observation = validate_label(entry['observation'], '测次引用')
        if name in names or observation not in observation_names:
            raise ValueError('重复情景锚点或引用的测次不存在')
        names.add(name)
        records.append(ScenarioInput(name, observation, parse_pair(entry['origin'])))
    return tuple(sorted(records, key=lambda record: record.name))
