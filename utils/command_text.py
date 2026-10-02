"""
명령어 입력 정규화 · 이름 비교 · 다이스 식 패턴 (라우터·다이스·CoC 폴백 공용)

- `normalize_command_text`: 전각·호환 문자(NFKC), 여러 가지 빼기 기호, `≤ ≥`, 보이지 않는 문자.
  모바일 입력기·자동 변환에서 섞여 들어오는 `［근력＋1］`, `−3` 등을 반각 기호로 맞춘다.
- `name_key`: 시트 이름 비교용 키 — 공백·장식 괄호(《》 등) 제거 + 소문자.
- `DICE_EXPRESSION_RE`: `NdM`, `NdM±K`, `NdM±K<=A` (비교: `<= >= < > = <>`).
"""

from __future__ import annotations

import re
import unicodedata

_SYMBOLS = {
    **dict.fromkeys(map(ord, "−‐‑‒–—﹣"), "-"),
    ord("≤"): "<=",
    ord("≦"): "<=",
    ord("≥"): ">=",
    ord("≧"): ">=",
}
_INVISIBLE_RE = re.compile("[\u200b-\u200d\u2060\ufeff]")
_DECORATION = str.maketrans("", "", "《》〈〉「」『』【】")

DICE_USAGE = "주사위 식 예: [2d6], [1d20+5], [1d100<=50], [2d6+1>=7]"

DICE_EXPRESSION_RE = re.compile(r"^(\d+)[dD](\d+)([+-]\d+)?(?:(<=|>=|<>|<|>|=)(-?\d+))?$")
DICE_LIKE_RE = re.compile(r"^(?:\d+[dD]\d*|[dD]\d+)[^가-힣a-zA-Z]*$")


def normalize_command_text(text: str) -> str:
    """명령어 원문 정규화 (NFKC + 빼기 기호·부등호 통일 + 보이지 않는 문자 제거)."""
    text = unicodedata.normalize("NFKC", text or "")
    return _INVISIBLE_RE.sub("", text).translate(_SYMBOLS)


def name_key(name: str) -> str:
    """시트 이름 비교 키: `근 력` == `근력` == `《근력》`, `근접전 (격투)` == `근접전(격투)`."""
    return "".join(normalize_command_text(name).translate(_DECORATION).split()).lower()


def compact(text: str) -> str:
    """모든 공백 제거."""
    return "".join((text or "").split())


def is_dice_expression(text: str) -> bool:
    """공백을 뺀 `text` 가 다이스 식인지."""
    return bool(DICE_EXPRESSION_RE.match(compact(text)))


def looks_like_dice(text: str) -> bool:
    """`2d6+`, `3d`, `2d6/3` 처럼 다이스를 쓰려다 형식이 틀린 입력인지 (`NdM` 으로 시작하고 글자가 없는 식)."""
    return bool(DICE_LIKE_RE.match(compact(text))) and not is_dice_expression(text)
