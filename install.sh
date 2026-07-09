#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${HOMEAPP_REPO_URL:-https://github.com/benjaminingreens/home.git}"
TARGET_DIR="${HOMEAPP_INSTALL_DIR:-$HOME/apps/homeapp}"

for cmd in git python3; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: $cmd is required but not found." >&2
        exit 1
    fi
done

if [ -d "$TARGET_DIR/.git" ]; then
    echo "Existing install found at $TARGET_DIR, pulling latest..."
    git -C "$TARGET_DIR" pull --recurse-submodules
else
    echo "Cloning homeapp into $TARGET_DIR"
    git clone --recurse-submodules "$REPO_URL" "$TARGET_DIR"
fi

cd "$TARGET_DIR"
exec ./install
