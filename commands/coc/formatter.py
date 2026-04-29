"""
CoC 응답 메시지 포매터

판정 결과(CheckOutcome), 무기 공격 결과, 스탯 변동 결과를 사용자용 한국어
문자열로 변환한다. 마스토돈은 마크다운을 렌더링하지 않으므로 별표 등 장식
기호는 사용하지 않는다.

기본 출력 형식:

    회피
    기준치: 77 / 38 / 15
    굴림: 17
    판정결과: 어려운 성공

무기 판정은 위 블록 뒤에 빈 줄과 `피해: <값>` 을 추가한다. 실패/대실패 시
피해 줄은 생략.
"""

from __future__ import annotations

from typing import Optional

from .check_engine import CheckOutcome
from .damage_engine import DamageRoll


def _modifier_suffix(modifier: int) -> str:
    """보너스/패널티 표시 (0 이면 빈 문자열)."""
    if modifier > 0:
        return f" (보너스 ×{modifier})"
    if modifier < 0:
        return f" (패널티 ×{abs(modifier)})"
    return ""


def _roll_detail(outcome: CheckOutcome) -> str:
    """보너스/패널티가 있으면 십자리 후보까지 노출, 아니면 빈 문자열."""
    if outcome.rolled.modifier == 0:
        return ""
    cands = ", ".join(f"{t:02d}" for t in outcome.rolled.tens_candidates)
    return f" (십자리 후보: {cands} → {outcome.rolled.tens:02d})"


def _format_check_block(
    title: str,
    outcome: CheckOutcome,
) -> str:
    """
    제목 + 기준치/굴림/판정결과 4줄 블록.

    기준치는 성공(큰값) / 어려운 / 극단(작은값) 순서.
    """
    t = outcome.thresholds
    mod_suffix = _modifier_suffix(outcome.rolled.modifier)
    roll_suffix = _roll_detail(outcome)

    return (
        f"{title}{mod_suffix}\n"
        f"기준치: {t.regular} / {t.hard} / {t.extreme}\n"
        f"굴림: {outcome.rolled.d100}{roll_suffix}\n"
        f"판정결과: {outcome.result.label}"
    )


def format_check(outcome: CheckOutcome) -> str:
    """일반 기능/능력치 판정 결과."""
    return _format_check_block(outcome.skill_name, outcome)


def format_weapon_attack(
    weapon_name: str,
    skill_name: str,
    outcome: CheckOutcome,
    damage_roll: DamageRoll,
    base_damage: int,
    base_detail: str,
    bonus_damage: int,
    bonus_detail: str,
    total_damage: int,
    penetrates: bool,
) -> str:
    """
    무기 판정 + 피해 계산 결과.

    `skill_name` / `base_detail` / `bonus_detail` 은 현재 출력에는 포함하지
    않지만 호출측 호환성을 위해 시그니처는 유지.
    """
    _ = (skill_name, base_detail, bonus_detail, damage_roll, base_damage, bonus_damage)  # 미사용

    block = _format_check_block(weapon_name, outcome)

    if outcome.result.is_success:
        return f"{block}\n\n피해: {total_damage}"

    return block


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
