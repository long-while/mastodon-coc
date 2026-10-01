"""
CoC 응답 메시지 포매터

판정 결과(CheckOutcome), 무기 공격 결과, 스탯 변동 결과를 사용자용 한국어
문자열로 변환한다.

`Config.MARKDOWN_ENABLED=False` (기본): 마스토돈 본가는 Markdown 을 렌더링하지
않으므로 별표 없이 평문으로 출력. `True` (한참 등): 판정 제목의 기능명을 `**볼드**` 로.

판정:
    관찰력 판정
    CC<=40/20/8
    ➤ 10
    ➤ 어려운 성공

보너스/패널티 (후보 d100 값을 굴린 순서대로 나열 후 채택값):
    근력 판정
    CC(+2)<=70/35/14
    ➤ 83,23,13
    ➤ 13
    ➤ 극단적 성공

무기 판정은 제목에 판정에 쓴 기능명, 성공 시 빈 줄 + 피해 다이스 블록 (무기명은 '피해' 앞):
    근접전(격투) 판정
    …
    1D3+2D6
    ➤ 1[1]+7[3,4]
    ➤ 단도 피해 8
최대 피해로 고정되는 경우(비관통 극단적 성공·대성공)는 `➤ 단도 피해 N` 한 줄.
실패/대실패 시 피해 블록은 생략.
"""

from __future__ import annotations

from typing import List, Optional

from config.settings import config

from .check_engine import CheckOutcome
from .damage_engine import WeaponDamage


def _bold(text: str) -> str:
    """`Config.MARKDOWN_ENABLED` 가 켜졌을 때만 `**…**` 로 감싼다."""
    if not config.MARKDOWN_ENABLED:
        return text
    return f"**{text}**"


def _check_lines(title: str, outcome: CheckOutcome) -> List[str]:
    t = outcome.thresholds
    rolled = outcome.rolled
    modifier = f"({rolled.modifier:+d})" if rolled.modifier else ""
    lines = [f"{_bold(title)} 판정", f"CC{modifier}<={t.regular}/{t.hard}/{t.extreme}"]
    if rolled.modifier:
        lines.append("➤ " + ",".join(str(v) for v in rolled.candidates))
    lines.append(f"➤ {rolled.d100}")
    lines.append(f"➤ {outcome.result.label}")
    return lines


def format_check(outcome: CheckOutcome) -> str:
    """일반 기능/능력치 판정 결과."""
    return "\n".join(_check_lines(outcome.skill_name, outcome))


def _damage_lines(weapon_name: str, damage: Optional[WeaponDamage]) -> List[str]:
    if damage is None:
        return []
    total_line = f"➤ {weapon_name} 피해 {damage.total}"
    if not damage.expression:
        return [total_line]
    return ["", damage.expression, f"➤ {damage.shown}", total_line]


def format_weapon_attack(weapon_name: str, outcome: CheckOutcome, damage: Optional[WeaponDamage]) -> str:
    """무기 판정 (제목은 판정에 쓴 기능명) + (성공 시) 무기명 붙은 피해 블록."""
    return "\n".join(_check_lines(outcome.skill_name, outcome) + _damage_lines(weapon_name, damage))


def format_stat_change(
    stat_label: str,
    before: Optional[int],
    after: int,
    delta: int,
    dice_detail: Optional[str] = None,
    clamped: bool = False,
    upper_bound: Optional[int] = None,
) -> str:
    """
    스탯 변화/변동 결과.

    예 1 (고정값):
        이성
        48 → 45 (-3)

    예 2 (다이스):
        이성
        -1d6(4) = -4 → 48 → 44

    예 3 (하한 clamp):
        체력
        2 → 0 (-5)  (0 미만 불가)

    예 4 (상한 clamp):
        체력
        12 → 14 (+5)  (최대 14 초과 불가)
    """
    sign = "+" if delta >= 0 else ""
    delta_str = f"{sign}{delta}"

    before_str = "?" if before is None else str(before)

    lines = [stat_label]
    if dice_detail:
        lines.append(f"{dice_detail} → {before_str} → {after}")
    else:
        lines.append(f"{before_str} → {after} ({delta_str})")

    if clamped:
        if upper_bound is not None:
            lines[-1] += f"  (최대 {upper_bound} 초과 불가)"
        else:
            lines[-1] += "  (0 미만 불가)"

    return "\n".join(lines)
