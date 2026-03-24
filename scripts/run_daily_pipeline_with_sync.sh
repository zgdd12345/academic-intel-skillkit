#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OBSIDIAN_REPO_DEFAULT="/Volumes/My Shared Files/ObsidianLib/Document_News"
CONDA_BIN_DEFAULT="${HOME}/miniconda3/condabin/conda"
CONDA_ENV_DEFAULT="crawer"
AUTO_COMMIT_PREFIX_DEFAULT="chore(research): sync daily brief"

OBSIDIAN_REPO="${OBSIDIAN_REPO:-$OBSIDIAN_REPO_DEFAULT}"
CONDA_BIN="${CONDA_BIN:-$CONDA_BIN_DEFAULT}"
CONDA_ENV="${CONDA_ENV:-$CONDA_ENV_DEFAULT}"
AUTO_COMMIT_PREFIX="${AUTO_COMMIT_PREFIX:-$AUTO_COMMIT_PREFIX_DEFAULT}"

log() {
  printf '[daily-sync] %s\n' "$*"
}

fail() {
  printf '[daily-sync] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

ensure_clean_pull_or_abort() {
  local repo="$1"
  if ! git -C "$repo" diff --quiet || ! git -C "$repo" diff --cached --quiet; then
    fail "repo has uncommitted changes, aborting pull: $repo"
  fi
  git -C "$repo" pull --rebase --autostash
}

commit_and_push_if_needed() {
  local repo="$1"
  local stamp
  stamp="$(date '+%Y-%m-%d %H:%M:%S %z')"

  if git -C "$repo" diff --quiet && git -C "$repo" diff --cached --quiet && [ -z "$(git -C "$repo" ls-files --others --exclude-standard)" ]; then
    log "no changes to commit in $repo"
    return 0
  fi

  git -C "$repo" status --short
  git -C "$repo" add -A

  if git -C "$repo" diff --cached --quiet; then
    log "nothing staged after add in $repo"
    return 0
  fi

  git -C "$repo" commit -m "$AUTO_COMMIT_PREFIX ($stamp)"
  git -C "$repo" push
}

main() {
  require_cmd git
  require_cmd "$CONDA_BIN"

  [ -d "$REPO_DIR/.git" ] || fail "project repo is not a git repo: $REPO_DIR"
  [ -d "$OBSIDIAN_REPO/.git" ] || fail "obsidian repo is not a git repo: $OBSIDIAN_REPO"

  log "project repo: $REPO_DIR"
  log "obsidian repo: $OBSIDIAN_REPO"
  log "syncing obsidian repo before pipeline"
  ensure_clean_pull_or_abort "$OBSIDIAN_REPO"

  log "running daily pipeline"
  cd "$REPO_DIR"
  "$CONDA_BIN" run -n "$CONDA_ENV" --no-capture-output python scripts/run_daily_pipeline.py "$@"

  log "syncing obsidian repo after pipeline"
  commit_and_push_if_needed "$OBSIDIAN_REPO"
  log "done"
}

main "$@"
