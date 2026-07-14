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

# `git pull --recurse-submodules` fetches submodule commits but does not
# reliably check them out into the submodule's working tree (that depends
# on the submodule.recurse git config, which isn't guaranteed to be set).
# This is the explicit step that actually replaces on-disk submodule code
# (e.g. Ark) to match whatever commit the superproject now points at.
git -C "$TARGET_DIR" submodule update --init --recursive

cd "$TARGET_DIR"
exec ./install
