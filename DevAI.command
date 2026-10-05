#!/bin/zsh
# DevAI launcher (macOS): double-click this file in Finder.
#
# It asks which project to open, then opens DevAI's web interface in your
# browser. The first run sets everything up (a Python environment in .venv
# and, if Node is installed, the web pages); later runs start in seconds.
# To stop DevAI: press Ctrl+C here, or close this window.
#
# From a terminal: ./DevAI.command [project folder]

# The project given as an argument, made absolute before leaving this folder.
PROJECT="${1:+${1:A}}"

# 1. Work from DevAI's own folder: the one this file is in.
cd "${0:A:h}" || exit 1
HERE="$PWD"

# 2. Finder doesn't use your Terminal's PATH: add Homebrew's folders, where
#    python3, node, gh and opencode usually live.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

say() { print -P "\n%B$*%b"; }
fail() {
  print -u2 "\n$*"
  read "?Press Enter to close this window. "
  exit 1
}

# 3. A Python of 3.11 or newer, for the first setup.
find_python() {
  local candidate
  for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" > /dev/null &&
      "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2> /dev/null; then
      print "$candidate"
      return
    fi
  done
}

# 4. DevAI with its AI and web extras, in .venv: installed the first time, and
#    again whenever pyproject.toml changes (after a `git pull`, say).
MARKER=".venv/.devai-installed"
if [[ ! -f $MARKER || pyproject.toml -nt $MARKER ]] ||
  ! .venv/bin/python -c 'import fastapi, uvicorn, pydantic' 2> /dev/null; then
  say "Setting up DevAI (only the first time; it takes a minute)..."
  if [[ ! -x .venv/bin/python ]]; then
    PYTHON="$(find_python)"
    [[ -n $PYTHON ]] || fail "DevAI needs Python 3.11 or newer. It's free: https://www.python.org/downloads/"
    "$PYTHON" -m venv .venv || fail "Couldn't create the Python environment (.venv)."
  fi
  .venv/bin/python -m pip install --quiet --upgrade pip &&
    .venv/bin/python -m pip install --quiet -e ".[ai,web]" ||
    fail "Installing DevAI failed: see the messages above."
  touch "$MARKER"
fi

# 5. The web pages, built with Node: the first time, and again when their
#    source changes. Without Node, DevAI still runs, but only its API answers.
PAGES="web/dist/index.html"
if [[ ! -f $PAGES ]] || [[ -n "$(find web/src web/index.html web/package-lock.json -newer $PAGES 2> /dev/null | head -1)" ]]; then
  if command -v npm > /dev/null; then
    say "Building the web pages..."
    if [[ ! -d web/node_modules || web/package-lock.json -nt web/node_modules ]]; then
      npm --prefix web ci --silent || fail "Installing the pages' tools failed."
    fi
    npm --prefix web run build --silent > /dev/null || fail "Building the pages failed."
  elif [[ ! -f $PAGES ]]; then
    say "Node isn't installed, so the pages can't be built: only the API will answer."
    print "Node is free: https://nodejs.org"
  fi
fi

# 6. Which project: the argument, or a folder chosen in a window. Cancel
#    opens the demo project that comes with DevAI.
if [[ -z $PROJECT ]]; then
  PROJECT="$(osascript - "${HERE:h}" 2> /dev/null <<'APPLESCRIPT'
on run argv
  try
    set start to POSIX file (item 1 of argv)
    return POSIX path of (choose folder with prompt "Which project should DevAI open? (Cancel opens the demo project.)" default location start)
  on error
    return ""
  end try
end run
APPLESCRIPT
)"
fi
[[ -n $PROJECT ]] || PROJECT="$HERE/examples/demo-project"

# 7. A free port, from 8765 on: another DevAI may already be open.
PORT="$(.venv/bin/python -c '
import socket
for port in range(8765, 8785):
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) != 0:
            print(port)
            break
')"
[[ -n $PORT ]] || fail "Ports 8765 to 8784 are all taken: close another DevAI window first."

# 8. A note when no free AI is installed: everything else still works.
if ! command -v opencode > /dev/null && ! command -v ollama > /dev/null; then
  say "Note: the AI buttons need OpenCode (https://opencode.ai) or Ollama (https://ollama.com), both free."
fi

say "Opening DevAI for ${PROJECT%/}"
print "Your browser opens by itself. Keep this window open while you use DevAI;"
print "press Ctrl+C or close the window to stop it."
.venv/bin/devai serve "$PROJECT" --port "$PORT" || fail "DevAI stopped with an error: see above."
