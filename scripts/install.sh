#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/0xp4ck3t/liksyon"
INSTALL_DIR="${HOME}/.local/share/liksyon"
BIN_DIR="${HOME}/.local/bin"
LAUNCHER="${BIN_DIR}/liksyon"

# ── colours ──────────────────────────────────────────────────────────────────
BOLD='\033[1m'
GREEN='\033[1;32m'
BLUE='\033[1;34m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
DIM='\033[2m'
NC='\033[0m'

step()  { echo -e "${BLUE}==>${NC} ${BOLD}$1${NC}"; }
ok()    { echo -e "${GREEN} ✓${NC}  $1"; }
warn()  { echo -e "${YELLOW} !${NC}  $1"; }
die()   { echo -e "${RED} ✗${NC}  $1" >&2; exit 1; }

# ── banner ───────────────────────────────────────────────────────────────────
echo -e "
${BLUE}${BOLD}██╗     ██╗██╗  ██╗███████╗██╗   ██╗ ██████╗ ███╗   ██╗${NC}
${BLUE}${BOLD}██║     ██║██║ ██╔╝██╔════╝╚██╗ ██╔╝██╔═══██╗████╗  ██║${NC}
${BLUE}${BOLD}██║     ██║█████╔╝ ███████╗ ╚████╔╝ ██║   ██║██╔██╗ ██║${NC}
${BLUE}${BOLD}██║     ██║██╔═██╗ ╚════██║  ╚██╔╝  ██║   ██║██║╚██╗██║${NC}
${BLUE}${BOLD}███████╗██║██║  ██╗███████║   ██║   ╚██████╔╝██║ ╚████║${NC}
${BLUE}${BOLD}╚══════╝╚═╝╚═╝  ╚═╝╚══════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═══╝${NC}
${DIM}  AI-powered flashcards from your Udemy courses${NC}
"

# ── check: git ───────────────────────────────────────────────────────────────
step "Checking dependencies..."
command -v git &>/dev/null || die "git is required. Install it and try again."

# ── check: python 3.11+ ──────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        meets=$("$cmd" -c "import sys; print(sys.version_info >= (3,11))" 2>/dev/null || echo "False")
        if [ "$meets" = "True" ]; then
            PYTHON=$(command -v "$cmd")
            break
        fi
    fi
done
[ -n "$PYTHON" ] || die "Python 3.11 or higher is required. Download from https://python.org"
ok "Python: $PYTHON ($("$PYTHON" --version))"

# ── clone or update ──────────────────────────────────────────────────────────
if [ -d "${INSTALL_DIR}/.git" ]; then
    step "Updating liksyon..."
    git -C "$INSTALL_DIR" pull --quiet
    ok "Updated to latest version"
else
    step "Downloading liksyon..."
    rm -rf "$INSTALL_DIR"
    git clone --quiet --depth 1 "$REPO_URL" "$INSTALL_DIR"
    ok "Downloaded to ${INSTALL_DIR}"
fi

# ── virtual environment ──────────────────────────────────────────────────────
step "Creating virtual environment..."
"$PYTHON" -m venv "${INSTALL_DIR}/.venv"
ok "Virtual environment ready"

# ── install package ──────────────────────────────────────────────────────────
step "Installing liksyon..."
"${INSTALL_DIR}/.venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install --quiet "${INSTALL_DIR}"
ok "Package installed"

# ── launcher script ──────────────────────────────────────────────────────────
step "Creating launcher..."
mkdir -p "$BIN_DIR"

cat > "$LAUNCHER" << LAUNCHER_EOF
#!/usr/bin/env bash
exec "${INSTALL_DIR}/.venv/bin/python" -m liksyon.cli "\$@"
LAUNCHER_EOF

chmod +x "$LAUNCHER"
ok "Launcher created at ${LAUNCHER}"

# ── PATH check ───────────────────────────────────────────────────────────────
if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
    echo ""
    warn "${BIN_DIR} is not in your PATH."

    # Detect shell and suggest the right rc file
    SHELL_RC=""
    case "${SHELL}" in
        */zsh)  SHELL_RC="${HOME}/.zshrc" ;;
        */bash) SHELL_RC="${HOME}/.bashrc" ;;
    esac

    if [ -n "$SHELL_RC" ]; then
        echo -e "  Run this to fix it:\n"
        echo -e "  ${BOLD}echo 'export PATH=\"\${HOME}/.local/bin:\${PATH}\"' >> ${SHELL_RC} && source ${SHELL_RC}${NC}\n"
    else
        echo -e "  Add ${BIN_DIR} to your PATH and restart your shell.\n"
    fi
else
    echo ""
    echo -e "${GREEN}${BOLD}  All done! Run: liksyon${NC}"
    echo ""
fi
