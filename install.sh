#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$HOME/.claude/wg"
COMMANDS_DIR="$HOME/.claude/commands"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== claude-wg installer ==="
echo

# ── Create directories ────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR/channels"
mkdir -p "$COMMANDS_DIR"

# ── Python venv + dependencies ────────────────────────────────────────────────
echo "Setting up Python environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -q -r "$REPO_DIR/daemon/requirements.txt"
echo "  ✓ Dependencies installed"

# ── Copy daemon files ─────────────────────────────────────────────────────────
cp "$REPO_DIR/daemon/daemon.py" "$INSTALL_DIR/"
cp "$REPO_DIR/daemon/cli.py"    "$INSTALL_DIR/"
cp "$REPO_DIR/daemon/state.py"  "$INSTALL_DIR/"
echo "  ✓ Daemon files copied to $INSTALL_DIR"

# ── Copy skills (custom slash commands) ──────────────────────────────────────
for skill in wg wg-plan wg-sync wg-approve wg-status wg-list wg-join wg-close; do
  cp "$REPO_DIR/skills/${skill}.md" "$COMMANDS_DIR/"
done
echo "  ✓ Skills copied to $COMMANDS_DIR"

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_FILE="$INSTALL_DIR/config.json"

if [ -f "$CONFIG_FILE" ]; then
  echo
  echo "Config already exists at $CONFIG_FILE"
  read -rp "Overwrite? [y/N] " overwrite
  [[ "$overwrite" =~ ^[Yy]$ ]] || { echo "Keeping existing config."; CONFIG_SKIP=1; }
fi

if [ -z "${CONFIG_SKIP:-}" ]; then
  echo
  echo "Enter your Slack credentials:"
  read -rp "  Bot token    (xoxb-...): " BOT_TOKEN
  read -rp "  App token    (xapp-...): " APP_TOKEN
  read -rp "  Your Slack user ID (U...): " USER_ID

  cat > "$CONFIG_FILE" <<JSON
{
  "slack_bot_token": "$BOT_TOKEN",
  "slack_app_token": "$APP_TOKEN",
  "my_slack_user_id": "$USER_ID",
  "state_dir": "$INSTALL_DIR",
  "notify_macos": true
}
JSON
  chmod 600 "$CONFIG_FILE"
  echo "  ✓ Config written (chmod 600)"
fi

# ── launchd service ───────────────────────────────────────────────────────────
PLIST_SRC="$REPO_DIR/launchd/com.claude.wg.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.claude.wg.plist"
PYTHON_BIN="$INSTALL_DIR/venv/bin/python"

sed \
  -e "s|REPLACE_USER|$(whoami)|g" \
  -e "s|/usr/bin/python3|$PYTHON_BIN|g" \
  -e "s|/Users/REPLACE_USER/.claude/wg/daemon.py|$INSTALL_DIR/daemon.py|g" \
  "$PLIST_SRC" > "$PLIST_DST"

# Unload if already loaded (ignore errors)
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo "  ✓ launchd service registered and started"

# ── Verify ────────────────────────────────────────────────────────────────────
echo
echo "=== Installation complete ==="
echo
echo "Daemon status:"
launchctl list | grep claude.wg || echo "  (not found — check $INSTALL_DIR/daemon.err)"
echo
echo "Logs:  tail -f $INSTALL_DIR/daemon.log"
echo "Skill test: open Claude Code and type /wg"
echo
echo "Share ONBOARDING.md with your collaborators."
