#!/usr/bin/env bash
# Dev-loop helper for codex-opinion plugin authors.
#
# Symlinks the installed plugin's versioned cache directory to this repo's
# working tree so edits to plugins/codex-opinion/** are live without the
# commit/push/`plugins update`/restart cycle.
#
# Re-run after any `claude plugins update`, version bump in plugin.json, or
# cache wipe — each of these can replace the symlink with a fetched copy.
#
# Restart Claude Code once after running this. SKILL.md in-session caching
# behavior is not documented; if you edit SKILL.md and see stale behavior,
# restart Claude Code.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLUGIN_DIR="$REPO_ROOT/plugins/codex-opinion"
MANIFEST="$PLUGIN_DIR/.claude-plugin/plugin.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "dev-link: manifest not found at $MANIFEST — not a codex-opinion repo?" >&2
    exit 1
fi

VERSION=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$MANIFEST")
if [[ -z "$VERSION" ]]; then
    echo "dev-link: could not read version from $MANIFEST" >&2
    exit 1
fi

CACHE_ROOT="$HOME/.claude/plugins/cache/codex-opinion/codex-opinion"
CACHE_DIR="$CACHE_ROOT/$VERSION"

# Guard: never touch a path outside the expected cache root prefix.
case "$CACHE_DIR" in
    "$HOME/.claude/plugins/cache/codex-opinion/codex-opinion/"*) ;;
    *)
        echo "dev-link: refusing to touch unexpected path $CACHE_DIR" >&2
        exit 1
        ;;
esac

mkdir -p "$CACHE_ROOT"

if [[ -L "$CACHE_DIR" ]]; then
    CURRENT_TARGET="$(readlink "$CACHE_DIR")"
    if [[ "$CURRENT_TARGET" == "$PLUGIN_DIR" ]]; then
        echo "dev-link: already linked: $CACHE_DIR -> $PLUGIN_DIR"
        exit 0
    fi
    echo "dev-link: replacing stale symlink (was -> $CURRENT_TARGET)"
    rm "$CACHE_DIR"
elif [[ -d "$CACHE_DIR" ]]; then
    echo "dev-link: removing existing cache directory at $CACHE_DIR"
    rm -rf "$CACHE_DIR"
fi

ln -s "$PLUGIN_DIR" "$CACHE_DIR"
echo "dev-link: linked $CACHE_DIR -> $PLUGIN_DIR"
echo "dev-link: restart Claude Code once so the session rebinds."
