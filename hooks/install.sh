#!/bin/bash
# Installs the repo's git hooks into .git/hooks.
cd "$(git rev-parse --show-toplevel)"
cp hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
