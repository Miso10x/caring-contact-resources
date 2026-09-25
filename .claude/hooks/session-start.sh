#!/bin/bash
# Runs at the start of every Claude session in this repo.
#
# Why this exists. A Claude Code cloud session starts with the repo it is
# attached to and nothing else. Michael's working rules, his memory of every
# trap already hit, the Disco deployment recipe and all credentials live in the
# private repo Miso10x/miso-env — none of which a fresh session can see. So it
# rebuilds decisions that were settled months ago, and asks Michael for keys he
# has already stored. That happened for a full day while building the
# experiment tracker before anyone noticed the cause.
#
# This cannot fetch miso-env itself: a plain `git clone` of a private repo fails
# in a cloud session ("could not read Username"), which is what SETUP.md
# documents. Only the session's own GitHub tooling can attach it. So this does
# the one useful thing available — it makes the first thing any session reads be
# where to look.
#
# It holds NO rules of its own, only the location. A copy of the rules here
# would drift from the master the moment that one is edited, which is the same
# reason CLAUDE.md is never committed into a project repo.
#
# Installed by miso-env/bootstrap.sh. Identical in every repo; edit the copy in
# miso-env/hooks/ and re-run bootstrap.sh, never the copy in a project.
set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}"

# Dependencies, so tests and linters work without a first-run stumble.
if [ -f pyproject.toml ] && command -v uv >/dev/null 2>&1; then
  uv sync --quiet >/dev/null 2>&1 || true
elif [ -f package.json ] && command -v npm >/dev/null 2>&1; then
  npm install --silent >/dev/null 2>&1 || true
fi

# A repo that keeps its git hooks in hooks/ gets them installed.
if [ -f hooks/install.sh ] && [ -d .git ]; then
  bash hooks/install.sh >/dev/null 2>&1 || true
fi

cat <<'NOTICE'
=== Before anything else, in this and every one of Michael's repos ===

MICHAEL IS NON-TECHNICAL. Anything he has to do himself gets numbered,
click-by-click, plain-English steps. Never ask him to run a command you can run
yourself. Never ask him for a credential before checking whether he has already
given it to you — he almost always has.

HIS INSTRUCTIONS ARE NOT IN THIS REPO. They are in the private repo
Miso10x/miso-env. Attach it with the session's GitHub tooling (a plain
`git clone` will fail on a private repo), clone it, and run its bootstrap.sh.
That gives you:

  home/CLAUDE.md  how to deploy via Disco, the testing rules, the rule that
                  internal tools get a password on every backend route
  memory/         one file per project and per trap already paid for. Read
                  memory/MEMORY.md first — it is an index.
  CREDENTIALS-HANDOFF.md   every credential, by location, with the traps
                  (two different HubSpot tokens, two Anthropic keys, a service
                  account that cannot send mail). Never paste one into chat.
  dotfiles/       Disco and git config, so you can deploy without asking him
  envs/, creds/   the values themselves

DO THAT FIRST. Skipping it is how a project ends up rebuilding decisions that
were already made, and asking Michael for things he handed over months ago.

If the work touches 10x Management as a company, also read 10x-brain: sync it,
read INDEX.md, and check CONFLICTS.md against your task BEFORE you build, not
after.
NOTICE
