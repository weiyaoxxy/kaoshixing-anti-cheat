#!/bin/zsh
# Canonical documents-skill renderer, using the installed Codex-managed Python.
# The fontconfig override is scoped to this process; no system config is modified.
set -eu
exec env FONTCONFIG_FILE=/opt/homebrew/etc/fonts/fonts.conf \
  /Users/weiyao/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/weiyao/.codex/plugins/cache/openai-primary-runtime/documents/26.426.12240/skills/documents/render_docx.py \
  "$@"
