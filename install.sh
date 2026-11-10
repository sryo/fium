#!/usr/bin/env bash
# fium installer — clones fium to ~/Documents/fium, links the skill into
# ~/.claude/skills and the fium CLI onto PATH (/usr/local/bin, else ~/.local/bin).
# Re-runnable: pulls an existing clone, leaves a link that's already right.
# Never replaces a file, a directory or a link to somewhere else; it says what it found.
# Never uses sudo.
#
# Overrides:
#   FIUM_REPO=...      git URL to clone from
#   FIUM_DIR=...       install location (default: ~/Documents/fium)
#   FIUM_BIN_DIR=...   where the fium CLI goes (default: /usr/local/bin)

set -euo pipefail

FIUM_REPO="${FIUM_REPO:-https://github.com/sryo/fium.git}"
FIUM_DIR="${FIUM_DIR:-$HOME/Documents/fium}"
FIUM_BIN_DIR="${FIUM_BIN_DIR:-/usr/local/bin}"
CLAUDE_LINK="$HOME/.claude/skills/fium"

command -v git >/dev/null || { echo "git not found. Run: xcode-select --install (macOS) or install git" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found. Run: xcode-select --install (macOS) or install Python 3" >&2; exit 1; }

# link SRC DEST: make DEST a symlink to SRC unless something else is already there.
link() {
  local src="$1" dest="$2"
  if [[ -L "$dest" ]]; then
    if [[ "$(readlink "$dest")" == "$src" ]]; then
      echo "$dest already links to $src"
    else
      echo "$dest links to $(readlink "$dest"), not $src; leaving it."
    fi
  elif [[ -e "$dest" ]]; then
    echo "$dest exists and isn't a link; leaving it."
  else
    mkdir -p "$(dirname "$dest")"
    ln -sfn "$src" "$dest"
    echo "Linked $dest -> $src"
  fi
}

if [[ ! -e "$FIUM_DIR" && -L "$CLAUDE_LINK" && -f "$CLAUDE_LINK/SKILL.md" ]]; then
  FIUM_DIR="$(readlink "$CLAUDE_LINK")"
  echo "fium already installed at $FIUM_DIR ($CLAUDE_LINK links to it). Leaving it."
elif [[ -f "$FIUM_DIR/SKILL.md" ]]; then
  if [[ -d "$FIUM_DIR/.git" ]]; then
    echo "fium already at $FIUM_DIR — pulling latest..."
    git -C "$FIUM_DIR" pull --ff-only
  else
    echo "fium already at $FIUM_DIR (local, no git repo — skipping pull)..."
  fi
elif [[ -e "$FIUM_DIR" ]]; then
  echo "$FIUM_DIR exists but holds no fium. Move it or set FIUM_DIR." >&2
  exit 1
else
  echo "Cloning fium to $FIUM_DIR..."
  mkdir -p "$(dirname "$FIUM_DIR")"
  git clone --quiet "$FIUM_REPO" "$FIUM_DIR"
fi

link "$FIUM_DIR" "$CLAUDE_LINK"

# The CLI: FIUM_BIN_DIR when it's writable (or already holds the right link),
# else ~/.local/bin.
bin_dir="$FIUM_BIN_DIR"
if [[ ! -L "$bin_dir/fium" || "$(readlink "$bin_dir/fium")" != "$FIUM_DIR/fium" ]]; then
  if [[ ! -d "$bin_dir" || ! -w "$bin_dir" ]]; then
    bin_dir="$HOME/.local/bin"
    echo "$FIUM_BIN_DIR isn't writable; putting the fium CLI in $bin_dir instead."
  fi
fi
link "$FIUM_DIR/fium" "$bin_dir/fium"

echo
echo "fium installed at $FIUM_DIR."
case ":$PATH:" in
  *":$bin_dir:"*) echo "Run: fium check ." ;;
  *) echo "$bin_dir isn't on your PATH. Add it (e.g. to ~/.zshrc):"
     echo "  export PATH=\"$bin_dir:\$PATH\""
     echo "Then run: fium check ." ;;
esac
echo "Restart your agent if it doesn't pick up the skill."
