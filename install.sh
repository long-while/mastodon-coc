#!/usr/bin/env bash
# install.sh — Debian 12 (bookworm) x64 용 CoC 마스토돈 봇 설치 스크립트
#
# 사용법:
#   curl -fsSL https://raw.githubusercontent.com/long-while/mastodon-coc/main/install.sh | bash
#
# 동작:
#   1) apt 로 git / python3 / python3-venv / python3-pip / tmux / nano 설치 (비대화형)
#   2) 저장소를 ~/coc 에 클론
#   3) venv 생성 + requirements.txt 설치
#   4) 사용자 입력값 정제(공백/프로토콜/경로/@ 제거) 후 .env 작성
#   5) 마무리 안내 출력 — credentials.json 은 사용자가 nano 로 직접 작성

set -euo pipefail

# apt / debconf 비대화형 설정 — 패키지 설치 중 보라색 debconf 화면(서비스 재시작
# 프롬프트, 설정 파일 충돌 등)이 뜨지 않도록 강제. curl|bash 자동 설치 흐름에선
# 사용자 개입 없이 끝까지 진행되어야 함.
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a              # needrestart: 서비스 자동 재시작
export NEEDRESTART_SUSPEND=1           # needrestart: 인터랙티브 모드 자체 비활성

REPO_URL="https://github.com/long-while/mastodon-coc.git"
INSTALL_DIR="$HOME/coc"
TTY_DEV="/dev/tty"

# apt 공통 옵션 — 설정 파일 충돌 시 새 버전 사용, 비대화형 유지.
APT_OPTS=(
    -y
    -o Dpkg::Options::=--force-confdef
    -o Dpkg::Options::=--force-confnew
)

# ----------------------------------------------------------------------
# 출력 헬퍼
# ----------------------------------------------------------------------
BOLD=$'\033[1m'
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'
RESET=$'\033[0m'

info()  { printf "%s[정보]%s %s\n" "$CYAN" "$RESET" "$*"; }
ok()    { printf "%s[완료]%s %s\n" "$GREEN" "$RESET" "$*"; }
warn()  { printf "%s[경고]%s %s\n" "$YELLOW" "$RESET" "$*"; }
err()   { printf "%s[오류]%s %s\n" "$RED" "$RESET" "$*" >&2; }

# ----------------------------------------------------------------------
# 입력 헬퍼 — curl|bash 환경에서도 사용자 입력을 받도록 /dev/tty 사용
# ----------------------------------------------------------------------
read_line() {
    local prompt="$1"
    local var
    printf "%s%s%s" "$BOLD" "$prompt" "$RESET" >&2
    if [[ -t 0 ]]; then
        IFS= read -r var
    else
        IFS= read -r var < "$TTY_DEV"
    fi
    printf "%s" "$var"
}

# 공백·탭·개행 등 모든 화이트스페이스 제거
sanitize_no_space() {
    local v="${1-}"
    v="${v//[[:space:]]/}"
    printf "%s" "$v"
}

# 도메인만 추출: https://, http:// 제거 + 첫 / 이후 경로 제거 + 공백 제거
sanitize_url() {
    local v
    v="$(sanitize_no_space "${1-}")"
    v="${v#https://}"
    v="${v#http://}"
    v="${v%%/*}"
    printf "%s" "$v"
}

# acct 정제: 공백 제거 + 선두 @ 제거
sanitize_id() {
    local v
    v="$(sanitize_no_space "${1-}")"
    v="${v#@}"
    printf "%s" "$v"
}

# ----------------------------------------------------------------------
# 1. 사전 검증
# ----------------------------------------------------------------------
require_apt() {
    if ! command -v apt-get >/dev/null 2>&1; then
        err "이 스크립트는 Debian/Ubuntu 계열에서만 동작합니다 (apt-get 필요)."
        exit 1
    fi
}

require_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        err "python3 가 설치되지 않았습니다. apt 설치가 정상적으로 끝났는지 확인하세요."
        exit 1
    fi
    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        local v
        v="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo unknown)"
        err "Python 3.10 이상이 필요합니다 (현재: $v)."
        err "Debian 12 (bookworm) 이상 권장."
        exit 1
    fi
}

# ----------------------------------------------------------------------
# 2. 시스템 패키지 설치
# ----------------------------------------------------------------------
install_system_deps() {
    # 모든 필수 도구가 이미 있으면 apt 단계 스킵 — sudo 권한 없는 일반 사용자
    # (coc 등) 가 root 의 사전 설치 후 install.sh 를 돌릴 수 있게 한다.
    if command -v git >/dev/null 2>&1 \
       && command -v python3 >/dev/null 2>&1 \
       && command -v tmux >/dev/null 2>&1 \
       && command -v nano >/dev/null 2>&1 \
       && python3 -c 'import venv, pip' 2>/dev/null; then
        info "필수 시스템 패키지가 이미 설치되어 있어 apt 단계를 건너뜁니다."
        return 0
    fi

    info "시스템 패키지 설치 (sudo 권한 필요, 비대화형 모드)"
    # sudo -E : 위에서 export 한 DEBIAN_FRONTEND/NEEDRESTART_* 를 sudo 환경에 전달.
    sudo -E apt-get update -y
    sudo -E apt-get install "${APT_OPTS[@]}" \
        git \
        python3 \
        python3-venv \
        python3-pip \
        tmux \
        nano \
        ca-certificates
    ok "시스템 패키지 설치 완료"
}

# ----------------------------------------------------------------------
# 3. 저장소 클론 + venv + Python 의존성
# ----------------------------------------------------------------------
clone_repo() {
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        info "기존 설치 발견 — 최신 상태로 업데이트"
        git -C "$INSTALL_DIR" pull --ff-only
    else
        info "저장소 클론 → $INSTALL_DIR"
        git clone --depth=1 "$REPO_URL" "$INSTALL_DIR"
    fi
    ok "저장소 준비 완료"
}

setup_venv() {
    info "가상환경 생성 + Python 의존성 설치"
    cd "$INSTALL_DIR"
    if [[ ! -d venv ]]; then
        python3 -m venv venv
    fi
    ./venv/bin/pip install --upgrade pip --quiet
    ./venv/bin/pip install -r requirements.txt --quiet
    ok "Python 의존성 설치 완료"
}

# ----------------------------------------------------------------------
# 4. 사용자 입력 → .env 작성
# ----------------------------------------------------------------------
prompt_config() {
    echo
    info "봇 설정값 입력 (모든 항목의 공백은 자동 제거됩니다)"
    echo

    local mast_url mast_token max_len admin coc_id rt_id custom_id
    local markdown_input markdown_enabled
    local decoration_input decoration_char decoration_pos decoration_both

    echo "${BOLD}1) 마스토돈 서버 주소${RESET}"
    echo "   - https:// 를 제외하고 example.com 부분만 작성하세요."
    mast_url="$(sanitize_url "$(read_line '   > ')")"
    if [[ -z "$mast_url" ]]; then
        err "서버 주소는 필수입니다."
        exit 1
    fi
    echo "   ↳ ${CYAN}https://${mast_url}${RESET}"
    echo

    echo "${BOLD}2) 마스토돈 액세스 토큰${RESET}"
    mast_token="$(sanitize_no_space "$(read_line '   > ')")"
    if [[ -z "$mast_token" ]]; then
        err "액세스 토큰은 필수입니다."
        exit 1
    fi
    echo

    echo "${BOLD}3) 서버의 글자수 제한${RESET}"
    echo "   - 마스토돈 서버에 들어갔을 때, 툿 작성란에 보이는 수를 적어주세요."
    max_len="$(sanitize_no_space "$(read_line '   > ')")"
    if ! [[ "$max_len" =~ ^[0-9]+$ ]]; then
        warn "숫자가 아닌 값이 입력됨 — 기본값 1000 사용"
        max_len=1000
    fi
    echo

    echo "${BOLD}4) KPC 혹은 GM 계정 아이디${RESET} (@ 없이 작성)"
    echo "   - 입력하신 아이디로 오류 알림이 전송됩니다."
    admin="$(sanitize_id "$(read_line '   > ')")"
    echo

    echo "${BOLD}5) CoC 캐릭터 시트 ID${RESET}"
    coc_id="$(sanitize_no_space "$(read_line '   > ')")"
    if [[ -z "$coc_id" ]]; then
        err "CoC 시트 ID 는 필수입니다."
        exit 1
    fi
    echo

    echo "${BOLD}6) 랜덤표 시트 ID${RESET}"
    rt_id="$(sanitize_no_space "$(read_line '   > ')")"
    if [[ -z "$rt_id" ]]; then
        err "랜덤표 시트 ID 는 필수입니다."
        exit 1
    fi
    echo

    echo "${BOLD}7) 커스텀 시트 ID${RESET}"
    custom_id="$(sanitize_no_space "$(read_line '   > ')")"
    if [[ -z "$custom_id" ]]; then
        err "커스텀 시트 ID 는 필수입니다."
        exit 1
    fi
    echo

    echo "${BOLD}8) 서버가 Markdown 형식(${RESET}*기울임꼴*${BOLD}/${RESET}**볼드체**${BOLD} 등)을 지원하나요?${RESET}"
    echo "   - 한참 인스턴스는 지원하므로 y를 입력해주세요."
    echo "   - 그 외의 서버는 n을 입력해주세요."
    markdown_input="$(sanitize_no_space "$(read_line '   > (y/n) ')")"
    case "${markdown_input,,}" in
        y|yes|true|1)
            markdown_enabled=true
            ;;
        n|no|false|0|"")
            markdown_enabled=false
            ;;
        *)
            warn "y/n 이 아닌 값이 입력됨 — 기본값 false 사용"
            markdown_enabled=false
            ;;
    esac
    echo "   ↳ ${CYAN}MARKDOWN_ENABLED=${markdown_enabled}${RESET}"
    echo

    echo "${BOLD}9) 자동봇 결과 출력 시 붙는 특수문자는 무엇으로 지정할까요?${RESET}"
    echo "   - ✦ 관찰력 ✦ 이렇게 출력됩니다."
    echo "   - 기본 ✦ 을 사용하고 싶으시면 엔터를 눌러주세요."
    echo "   - 다른 특수문자를 사용하고 싶으시면 인터넷에서 원하시는 특수문자를"
    echo "     복사하신 후 입력란에 붙여넣으세요."
    echo "   - 특수문자를 생략하고 싶으시면 ${BOLD}no${RESET} 라고 입력해 주세요."
    decoration_input="$(read_line '   > ')"
    # 양 끝 공백만 제거 (사용자가 붙여넣은 특수문자는 그대로 보존)
    decoration_input="${decoration_input#"${decoration_input%%[![:space:]]*}"}"
    decoration_input="${decoration_input%"${decoration_input##*[![:space:]]}"}"
    case "${decoration_input,,}" in
        no)
            decoration_char=""
            echo "   ↳ ${CYAN}장식 문자 생략${RESET}"
            ;;
        "")
            decoration_char="✦"
            echo "   ↳ ${CYAN}DECORATION_CHAR=✦ (기본값)${RESET}"
            ;;
        *)
            decoration_char="${decoration_input}"
            echo "   ↳ ${CYAN}DECORATION_CHAR=${decoration_char}${RESET}"
            ;;
    esac
    echo

    if [[ -n "$decoration_char" ]]; then
        echo "${BOLD}10) 자동봇 결과 출력 시 특수문자가 판정 기능치의 앞에만 붙을까요, 양 옆에 붙을까요?${RESET}"
        echo "   - ${decoration_char} 관찰력 ${decoration_char} 을 원하시면 ${BOLD}2${RESET} 를 입력하고 엔터"
        echo "   - ${decoration_char} 관찰력 을 원하시면 ${BOLD}1${RESET} 을 입력하고 엔터"
        decoration_pos="$(sanitize_no_space "$(read_line '   > (1/2) ')")"
        case "${decoration_pos}" in
            1)
                decoration_both=false
                ;;
            2|"")
                decoration_both=true
                ;;
            *)
                warn "1/2 가 아닌 값이 입력됨 — 기본값 2 (양옆) 사용"
                decoration_both=true
                ;;
        esac
        echo "   ↳ ${CYAN}DECORATION_BOTH_SIDES=${decoration_both}${RESET}"
        echo
    else
        # 장식 문자 생략 시 위치 옵션은 의미 없음 — 기본값으로 기록만 함.
        decoration_both=true
    fi

    cat > "$INSTALL_DIR/.env" <<EOF
# CoC 봇 설정 (install.sh 로 자동 생성)

MASTODON_API_BASE_URL=https://${mast_url}
MASTODON_ACCESS_TOKEN=${mast_token}
SHEET_ID=${coc_id}
SYSTEM_ADMIN_ID=${admin}
MAX_MESSAGE_LENGTH=${max_len}

RANDOM_TABLE_SHEET_ID=${rt_id}
CUSTOM_COMMAND_SHEET_ID=${custom_id}

MARKDOWN_ENABLED=${markdown_enabled}
DECORATION_CHAR=${decoration_char}
DECORATION_BOTH_SIDES=${decoration_both}

OPERATION_START_DATE=
OPERATION_END_DATE=
EOF
    chmod 600 "$INSTALL_DIR/.env"
    ok ".env 작성 완료 (${INSTALL_DIR}/.env, 권한 600)"
}

# ----------------------------------------------------------------------
# 5. 마무리 안내
# ----------------------------------------------------------------------
print_finish_message() {
    cat <<MSG

${GREEN}${BOLD}=== 설치 마법사 완료 — 다음 두 단계만 더 진행하세요 ===${RESET}

${BOLD}1) Google 서비스 계정 JSON 등록${RESET}
  cd ${INSTALL_DIR}
  nano credentials.json
  → JSON 전체를 붙여넣고 ${BOLD}Ctrl+O${RESET} (저장) → ${BOLD}Enter${RESET} → ${BOLD}Ctrl+X${RESET} (종료)

${BOLD}2) 봇 실행 (tmux 백그라운드 세션)${RESET}
  tmux new -s bot
  source venv/bin/activate
  python main.py

${BOLD}세션 분리:${RESET}     Ctrl+B  →  D
${BOLD}세션 재접속:${RESET}   tmux attach -t bot
${BOLD}봇 종료:${RESET}       세션 안에서 Ctrl+C

${BOLD}설정 파일:${RESET}     ${INSTALL_DIR}/.env
${BOLD}인증 파일:${RESET}     ${INSTALL_DIR}/credentials.json
                  (시트마다 서비스 계정 이메일을 ${BOLD}편집자${RESET}로 공유했는지 확인)

${BOLD}로그:${RESET}          ${INSTALL_DIR}/logs/bot.log

MSG
}

# ----------------------------------------------------------------------
main() {
    require_apt
    install_system_deps
    require_python
    clone_repo
    setup_venv
    prompt_config
    print_finish_message
}

main "$@"
