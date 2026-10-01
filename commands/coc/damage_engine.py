"""
CoC 무기 피해 계산

- `roll_damage(formula, rng=None)` — 복합식(`"1d4"`, `"1d4+2"`, `"3d10+1d5"`)을 굴려
  합계·최대값·출력용 식/굴림을 담은 `DamageRoll` 반환.
- `resolve_weapon_damage(weapon_roll, db_roll, db_mode, result, penetrates, counter)`
  — 판정 등급·관통·피해보너스·반격 규칙을 적용한 최종 피해와 출력 블록. 피해 규칙의 유일한 구현.

복합식 문법:
- 항: `ndm` | 정수. 항 사이를 `+` 또는 `-` 로 잇는다. 예: `3d10+1d5-2`, `-1d4`
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .check_engine import CheckResult

_TOKEN_DICE = re.compile(r'^(\d+)[dD](\d+)$')
_TOKEN_INT = re.compile(r'^(\d+)$')

# 허용 범위
MIN_DICE_COUNT = 1
MAX_DICE_COUNT = 30
MIN_DICE_SIDES = 2
MAX_DICE_SIDES = 1000


@dataclass(frozen=True)
class DamageRoll:
    """복합 다이스식 한 번 굴림 결과."""

    formula: str        # 원본 문자열
    total: int          # 실제 굴림 합
    max_value: int      # 이론상 최대값
    detail: str         # "1d4(3)=3+2" 형태의 설명
    expression: str = ""
    shown: str = ""
    has_dice: bool = False


def _split_terms(formula: str) -> List[Tuple[int, str]]:
    """
    복합식을 부호 있는 항 리스트로 분해.

    `"3d10+1d5-2"` → `[(+1, '3d10'), (+1, '1d5'), (-1, '2')]`, `"-1d6"` → `[(-1, '1d6')]`
    """
    s = (formula or "").strip().replace(" ", "")
    if not s:
        raise ValueError("빈 피해식")
    sign = -1 if s[0] == '-' else 1
    if s[0] in ('+', '-'):
        s = s[1:]

    tokens: List[Tuple[int, str]] = []
    current = ""
    for ch in s:
        if ch in ('+', '-'):
            if not current:
                raise ValueError(f"피해식 문법 오류: '{formula}'")
            tokens.append((sign, current))
            sign = 1 if ch == '+' else -1
            current = ""
        else:
            current += ch
    if not current:
        raise ValueError(f"피해식 문법 오류: '{formula}'")
    tokens.append((sign, current))
    return tokens


@dataclass(frozen=True)
class _TokenRoll:
    """항 하나 굴림: 값·최소/최대값·설명·출력용 식·출력용 굴림."""

    total: int
    min_value: int
    max_value: int
    detail: str
    expression: str
    shown: str
    has_dice: bool


def _roll_dice_token(n: int, m: int, rng: random.Random) -> _TokenRoll:
    """`ndm` 항 굴림."""
    if not (MIN_DICE_COUNT <= n <= MAX_DICE_COUNT):
        raise ValueError(f"다이스 개수 범위 초과: {n} (허용 {MIN_DICE_COUNT}~{MAX_DICE_COUNT})")
    if not (MIN_DICE_SIDES <= m <= MAX_DICE_SIDES):
        raise ValueError(f"다이스 면수 범위 초과: {m} (허용 {MIN_DICE_SIDES}~{MAX_DICE_SIDES})")
    rolls = [rng.randint(1, m) for _ in range(n)]
    total = sum(rolls)
    return _TokenRoll(
        total=total,
        min_value=n,
        max_value=n * m,
        detail=f"{n}d{m}({'+'.join(str(x) for x in rolls)})={total}",
        expression=f"{n}D{m}",
        shown=f"{total}[{','.join(str(x) for x in rolls)}]",
        has_dice=True,
    )


def _roll_token(token: str, rng: random.Random) -> _TokenRoll:
    """단일 항(`ndm` / 정수) 굴림."""
    dice_m = _TOKEN_DICE.match(token)
    if dice_m:
        return _roll_dice_token(int(dice_m.group(1)), int(dice_m.group(2)), rng)
    if _TOKEN_INT.match(token):
        v = int(token)
        return _TokenRoll(v, v, v, str(v), str(v), str(v), False)
    raise ValueError(f"피해식 항 해석 불가: '{token}'")


def roll_damage(formula: str, rng: Optional[random.Random] = None) -> DamageRoll:
    """
    복합 다이스식 굴림.

    Args:
        formula: `"1d4"`, `"1d4+2"`, `"3d10+1d5"`, `"0"` 등
        rng: 테스트용 시드 가능 RNG

    Raises:
        ValueError: 문법 오류·다이스 범위 초과.
    """
    cleaned = (formula or "").strip()
    if not cleaned:
        return DamageRoll(formula="", total=0, max_value=0, detail="0", expression="0", shown="0")
    if _TOKEN_INT.match(cleaned):
        v = int(cleaned)
        return DamageRoll(formula=cleaned, total=v, max_value=v, detail=str(v), expression=str(v), shown=str(v))
    return _roll_terms(cleaned, rng or random)


def _roll_terms(cleaned: str, rng: random.Random) -> DamageRoll:
    """`+`/`-` 로 이은 항들을 굴려 합친다. 음수 항의 최대 기여는 -(최소값)."""
    total = 0
    max_total = 0
    pieces: List[str] = []
    expression = ""
    shown = ""
    has_dice = False
    for sign, token in _split_terms(cleaned):
        rolled = _roll_token(token, rng)
        total += sign * rolled.total
        max_total += rolled.max_value if sign > 0 else -rolled.min_value
        prefix = "-" if sign < 0 else ("" if not pieces else "+")
        pieces.append(prefix + rolled.detail)
        expression += prefix + rolled.expression
        shown += prefix + rolled.shown
        has_dice = has_dice or rolled.has_dice

    return DamageRoll(
        formula=cleaned,
        total=total,
        max_value=max_total,
        detail=" ".join(pieces).strip().lstrip("+"),
        expression=expression,
        shown=shown,
        has_dice=has_dice,
    )


# ======================================================================
# 출력용 피해 블록
# ======================================================================

@dataclass(frozen=True)
class WeaponDamage:
    """무기 판정 성공 시 피해.

    `expression`/`shown` 이 비어 있으면 다이스 블록 없이 `➤ 피해 N` 만 출력한다
    (비관통 극단적 성공·대성공처럼 최대 피해로 고정되거나 주사위가 없는 경우).
    """

    total: int
    base: int
    bonus: int
    expression: str = ""
    shown: str = ""


@dataclass(frozen=True)
class _BonusPart:
    value: int
    expression: str = ""
    shown: str = ""
    has_dice: bool = False


def _join_term(text: str) -> str:
    """뒤에 이어 붙일 항: 음수는 그대로(`-1`), 나머지는 `+` 접두."""
    return text if text.startswith("-") else f"+{text}"


def _concat(weapon_text: str, bonus_text: str) -> str:
    """무기 항 + 피해보너스 항. 무기 피해식이 비어(`0`) 있으면 피해보너스만 (`0+2D6` → `2D6`)."""
    if weapon_text == "0" and bonus_text:
        return bonus_text.removeprefix("+")
    return weapon_text + bonus_text


def _bonus_part(db_roll: Optional[DamageRoll], db_mode: str, use_max: bool) -> _BonusPart:
    """피해보너스 항. `use_max` 면 최대값 (극단적 성공·대성공)."""
    mode = (db_mode or "0").strip()
    if db_roll is None or mode not in ("db", "1/2 db") or db_roll.expression in ("", "0"):
        return _BonusPart(0)
    full = db_roll.max_value if use_max else db_roll.total
    if mode == "db":
        return _BonusPart(full, _join_term(db_roll.expression), _join_term(db_roll.shown), db_roll.has_dice)
    return _BonusPart(
        full // 2,
        f"+1/2({db_roll.expression})",
        f"+1/2({db_roll.shown})",
        db_roll.has_dice,
    )


def resolve_weapon_damage(
    weapon_roll: DamageRoll,
    db_roll: Optional[DamageRoll],
    db_mode: str,
    result: CheckResult,
    penetrates: bool,
    counter: bool = False,
) -> Optional[WeaponDamage]:
    """판정 등급별 피해 + 출력 블록. 실패·대실패는 None.

    - 보통/어려운 성공, 또는 반격(`counter`): 무기식 + 피해보너스를 그대로 굴림 → `1D3+2D6`
    - 극단적 성공·대성공 + 관통: (무기 최대 + 피해보너스 최대) 상수 + 무기식 굴림 → `20+1D8`
    - 극단적 성공·대성공 + 비관통: 무기 최대 + 피해보너스 최대, 다이스 블록 없음
    합계가 음수(음수 피해보너스)면 0.
    """
    if not result.is_success:
        return None
    max_damage = result.is_max_damage and not counter
    bonus = _bonus_part(db_roll, db_mode, use_max=max_damage)
    if not max_damage:
        base = weapon_roll.total
        show = weapon_roll.has_dice or bonus.has_dice
        expression = _concat(weapon_roll.expression, bonus.expression) if show else ""
        shown = _concat(weapon_roll.shown, bonus.shown) if show else ""
    elif penetrates:
        base = weapon_roll.total + weapon_roll.max_value
        const = weapon_roll.max_value + bonus.value
        show = weapon_roll.has_dice
        expression = f"{const}{_join_term(weapon_roll.expression)}" if show else ""
        shown = f"{const}{_join_term(weapon_roll.shown)}" if show else ""
    else:
        base, expression, shown = weapon_roll.max_value, "", ""
    total = max(0, base + bonus.value)
    return WeaponDamage(total=total, base=base, bonus=bonus.value, expression=expression, shown=shown)
