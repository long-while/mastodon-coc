"""
.env 파일 관리 헬퍼 (CoC 봇)

CoC 봇 1개를 위한 .env 파일을 대화형으로 생성합니다.
사용자가 실제 편집해야 하는 항목은 MASTODON_API_BASE_URL / MASTODON_ACCESS_TOKEN
/ SHEET_ID 정도. 나머지는 코드 기본값으로 처리되어 prompt 하지 않습니다.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Set, Tuple


@dataclass(frozen=True)
class FieldSpec:
    key: str
    prompt: str
    default: Optional[str] = None
    condition: Optional[Callable[[Dict[str, str]], bool]] = None


@dataclass(frozen=True)
class SectionSpec:
    title: str
    keys: Tuple[str, ...]
    description: Optional[str] = None


# ----------------------------------------------------------------------
# 전역 prompt 대상 (사용자가 실제 편집해야 하는 것만)
# ----------------------------------------------------------------------
GLOBAL_FIELD_SPECS: Dict[str, FieldSpec] = {
    'MASTODON_API_BASE_URL': FieldSpec(
        key='MASTODON_API_BASE_URL',
        prompt='Mastodon 서버 URL',
        default='',
    ),
    'MASTODON_ACCESS_TOKEN': FieldSpec(
        key='MASTODON_ACCESS_TOKEN',
        prompt='Mastodon 액세스 토큰',
        default='',
    ),
    'SHEET_ID': FieldSpec(
        key='SHEET_ID',
        prompt='CoC 캐릭터 시트의 Google Sheets ID',
        default='',
    ),
    'SYSTEM_ADMIN_ID': FieldSpec(
        key='SYSTEM_ADMIN_ID',
        prompt='시스템 관리자 ID (콤마 구분, 선택)',
        default='',
    ),
    'GOOGLE_CREDENTIALS_PATH': FieldSpec(
        key='GOOGLE_CREDENTIALS_PATH',
        prompt='Google 인증 파일 경로',
        default='credentials.json',
    ),
    'RANDOM_TABLE_SHEET_ID': FieldSpec(
        key='RANDOM_TABLE_SHEET_ID',
        prompt='랜덤표 스프레드시트 ID (선택, 비우면 비활성화)',
        default='',
    ),
    'CUSTOM_COMMAND_SHEET_ID': FieldSpec(
        key='CUSTOM_COMMAND_SHEET_ID',
        prompt='커스텀 명령어 스프레드시트 ID (선택, 비우면 비활성화)',
        default='',
    ),
    'OPERATION_START_DATE': FieldSpec(
        key='OPERATION_START_DATE',
        prompt='가동 시작 날짜 KST YYYY-MM-DD (선택, 비우면 무제한)',
        default='',
    ),
    'OPERATION_END_DATE': FieldSpec(
        key='OPERATION_END_DATE',
        prompt='가동 종료 날짜 KST YYYY-MM-DD (선택, 비우면 무제한)',
        default='',
    ),
}

GLOBAL_SECTIONS: Tuple[SectionSpec, ...] = (
    SectionSpec(
        title='필수 항목',
        description='Mastodon 연결 + CoC 시트 설정',
        keys=(
            'MASTODON_API_BASE_URL',
            'MASTODON_ACCESS_TOKEN',
            'SHEET_ID',
            'SYSTEM_ADMIN_ID',
            'GOOGLE_CREDENTIALS_PATH',
        ),
    ),
    SectionSpec(
        title='보조 시트 (선택)',
        description='랜덤표/커스텀 명령어 시트. 비우면 해당 기능 비활성화.',
        keys=('RANDOM_TABLE_SHEET_ID', 'CUSTOM_COMMAND_SHEET_ID'),
    ),
    SectionSpec(
        title='가동 기간 (선택)',
        description='KST 기준. 종료 날짜 00:00 KST 부터 만료 안내 후 침묵. 비우면 무기한.',
        keys=('OPERATION_START_DATE', 'OPERATION_END_DATE'),
    ),
)


class EnvManager:
    """환경 변수 관리 클래스."""

    def __init__(self, env_path: str = '.env'):
        self.env_path = Path(env_path)
        self.config: Dict[str, str] = {}

    def _should_prompt(self, field_spec: FieldSpec) -> bool:
        if field_spec.condition is None:
            return True
        return field_spec.condition(self.config)

    def _prompt_field(self, field_spec: FieldSpec) -> None:
        current = self.get_value(field_spec.key, field_spec.default or '')
        placeholder = current or '입력 필요'
        value = input(f"{field_spec.prompt} [{placeholder}]: ").strip()
        if not value:
            value = current
        if value is None:
            value = ''
        self.set_value(field_spec.key, value)

    def load_existing(self) -> bool:
        if not self.env_path.exists():
            return False
        try:
            with open(self.env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        self.config[key.strip()] = value.strip()
            return True
        except Exception as e:
            print(f"[오류] .env 파일 로드 실패: {e}")
            return False

    def get_value(self, key: str, default: str = '') -> str:
        return self.config.get(key, default)

    def set_value(self, key: str, value: str) -> None:
        self.config[key] = value

    def interactive_setup(self) -> None:
        print("=" * 60)
        print("CoC 봇 환경 설정")
        print("=" * 60)
        print()

        if self.load_existing():
            print("[정보] 기존 .env 파일을 찾았습니다.")
            use_existing = input("기존 설정을 유지하시겠습니까? (Y/n): ").strip().lower()
            if use_existing == 'n':
                self.config = {}

        for section in GLOBAL_SECTIONS:
            print()
            print(f"=== {section.title} ===")
            if section.description:
                print(section.description)
            print()
            for key in section.keys:
                spec = GLOBAL_FIELD_SPECS[key]
                if not self._should_prompt(spec):
                    if spec.default is not None and key not in self.config:
                        self.set_value(key, spec.default)
                    continue
                self._prompt_field(spec)

        print()
        print("=== 설정 완료 ===")
        print()

    def save(self) -> bool:
        try:
            if self.env_path.exists():
                backup_path = Path(f"{self.env_path}.backup")
                with open(self.env_path, 'r', encoding='utf-8') as src:
                    with open(backup_path, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
                print(f"[정보] 기존 파일 백업: {backup_path}")

            with open(self.env_path, 'w', encoding='utf-8') as f:
                f.write("# CoC 봇 설정 (자동 생성)\n\n")

                written: Set[str] = set()
                for section in GLOBAL_SECTIONS:
                    rows = [(k, self.config[k]) for k in section.keys if k in self.config]
                    if not rows:
                        continue
                    f.write(f"# {section.title}\n")
                    for k, v in rows:
                        f.write(f"{k}={v}\n")
                        written.add(k)
                    f.write("\n")

                remaining = [k for k in sorted(self.config) if k not in written]
                if remaining:
                    f.write("# 기타\n")
                    for k in remaining:
                        f.write(f"{k}={self.config[k]}\n")

            print(f"[성공] 설정 파일 저장: {self.env_path}")
            return True
        except Exception as e:
            print(f"[오류] 설정 파일 저장 실패: {e}")
            return False

    def quick_edit(self, key: str, value: str) -> bool:
        self.load_existing()
        self.set_value(key, value)
        return self.save()

    def show_current(self) -> None:
        if not self.load_existing():
            print("[오류] .env 파일을 찾을 수 없습니다.")
            return
        print("현재 설정")
        print("=" * 60)
        for key, value in sorted(self.config.items()):
            display = value[:10] + '…' if 'TOKEN' in key and len(value) > 10 else value
            print(f"{key}={display}")


def main() -> None:
    manager = EnvManager()

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'show':
            manager.show_current()
        elif command == 'edit' and len(sys.argv) >= 4:
            key, value = sys.argv[2], sys.argv[3]
            if manager.quick_edit(key, value):
                print(f"[성공] {key}={value}")
        elif command == 'setup':
            manager.interactive_setup()
            manager.save()
        else:
            print("사용법:")
            print("  python env_manager.py setup         - 대화형 설정")
            print("  python env_manager.py show          - 현재 설정 보기")
            print("  python env_manager.py edit KEY VALUE - 빠른 수정")
    else:
        manager.interactive_setup()
        print()
        if input("설정을 저장하시겠습니까? (Y/n): ").strip().lower() != 'n':
            manager.save()
            print()
            print("[완료] 이제 'python main.py' 로 봇을 실행하세요!")


if __name__ == '__main__':
    main()
