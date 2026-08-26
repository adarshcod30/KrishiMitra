#!/usr/bin/env bash
# =============================================================================
# Assemble a Hugging Face Space working tree from this repository.
#
#   ./spaces/api/sync.sh <path-to-space-clone> [--with-artifacts] [--dry-run]
#
# Why a script instead of "just push the repo": a Docker Space builds from the
# ROOT of the Space repo and the Dockerfile must literally be named `Dockerfile`
# there. This repo keeps it at spaces/api/Dockerfile and holds a Next.js app,
# a satellite module and 200 MB of node_modules that the API image must not
# see. This script lays out exactly what the Space needs, and nothing else:
#
#   <space>/Dockerfile         <- spaces/api/Dockerfile
#   <space>/README.md          <- spaces/api/README.md   (HF YAML front-matter)
#   <space>/.gitattributes     <- spaces/api/space.gitattributes  (git-lfs)
#   <space>/.dockerignore      <- spaces/api/space.dockerignore
#   <space>/ml-service/        <- pyproject.toml, README.md, src/, data/, scripts/
#   <space>/ml-service/artifacts/*.joblib|*.json   (only with --with-artifacts)
#
# It NEVER pushes. It stages and commits (unless --dry-run), then prints the
# exact `git push` command for you to run — pushing publishes, and that is your
# call, not a script's.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HERE="${REPO_ROOT}/spaces/api"

WITH_ARTIFACTS=0
DRY_RUN=0
TARGET=""

usage() {
  sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --with-artifacts) WITH_ARTIFACTS=1 ;;
    --dry-run)        DRY_RUN=1 ;;
    -h|--help)        usage 0 ;;
    -*)               echo "unknown flag: $1" >&2; usage 1 ;;
    *)
      if [ -n "${TARGET}" ]; then echo "one target only (got '${TARGET}' and '$1')" >&2; exit 1; fi
      TARGET="$1"
      ;;
  esac
  shift
done

if [ -z "${TARGET}" ]; then
  echo "error: no target given." >&2
  echo >&2
  echo "Clone your Space first, then point this at it:" >&2
  echo "  git clone https://huggingface.co/spaces/<user>/<space> ../krishimitra-space" >&2
  echo "  ./spaces/api/sync.sh ../krishimitra-space" >&2
  exit 1
fi

mkdir -p "${TARGET}"
TARGET="$(cd "${TARGET}" && pwd)"

if [ "${TARGET}" = "${REPO_ROOT}" ]; then
  echo "error: refusing to sync the repository onto itself." >&2
  exit 1
fi

echo "source : ${REPO_ROOT}"
echo "target : ${TARGET}"
echo "mode   : $([ "${DRY_RUN}" = 1 ] && echo 'DRY RUN' || echo 'WRITE')  artifacts: $([ "${WITH_ARTIFACTS}" = 1 ] && echo yes || echo no)"
echo

RSYNC_FLAGS=(-a --delete)
[ "${DRY_RUN}" = 1 ] && RSYNC_FLAGS+=(--dry-run)

copy_file() {  # copy_file <src> <dst-relative>
  local src="$1" dst="${TARGET}/$2"
  if [ "${DRY_RUN}" = 1 ]; then
    echo "  would write  $2"
    return
  fi
  mkdir -p "$(dirname "${dst}")"
  cp "${src}" "${dst}"
  echo "  wrote        $2"
}

# --- 1. Space-root files ----------------------------------------------------
copy_file "${HERE}/Dockerfile"            "Dockerfile"
copy_file "${HERE}/README.md"             "README.md"
copy_file "${HERE}/space.gitattributes"   ".gitattributes"
copy_file "${HERE}/space.dockerignore"    ".dockerignore"

# --- 2. The service itself --------------------------------------------------
# --delete keeps the Space tree an exact mirror: a file deleted here disappears
# there too, instead of lingering in the image forever.
echo "  syncing      ml-service/{pyproject.toml,README.md,src,data,scripts}"
mkdir -p "${TARGET}/ml-service"
if [ "${DRY_RUN}" = 0 ]; then
  cp "${REPO_ROOT}/ml-service/pyproject.toml" "${TARGET}/ml-service/pyproject.toml"
  cp "${REPO_ROOT}/ml-service/README.md"      "${TARGET}/ml-service/README.md"
fi
for dir in src data scripts; do
  rsync "${RSYNC_FLAGS[@]}" \
    --exclude '__pycache__/' --exclude '*.py[cod]' \
    --exclude '.pytest_cache/' --exclude '.ruff_cache/' --exclude '*.egg-info/' \
    --exclude '.DS_Store' \
    "${REPO_ROOT}/ml-service/${dir}/" "${TARGET}/ml-service/${dir}/"
done

# --- 3. Model artifacts (optional, git-lfs) ---------------------------------
# .db is excluded on purpose: agrotech.db holds farmer PII and must never be
# published to a Space repo.
mkdir -p "${TARGET}/ml-service/artifacts"
if [ "${WITH_ARTIFACTS}" = 1 ]; then
  shopt -s nullglob
  found=0
  for f in "${REPO_ROOT}"/ml-service/artifacts/*.joblib "${REPO_ROOT}"/ml-service/artifacts/*.json; do
    found=1
    if [ "${DRY_RUN}" = 1 ]; then
      echo "  would copy   ml-service/artifacts/$(basename "$f")  ($(du -h "$f" | cut -f1))"
    else
      cp "$f" "${TARGET}/ml-service/artifacts/"
      echo "  copied       ml-service/artifacts/$(basename "$f")  ($(du -h "$f" | cut -f1))"
    fi
  done
  shopt -u nullglob
  if [ "${found}" = 0 ]; then
    echo "  WARNING: --with-artifacts given but ml-service/artifacts/ holds no models."
    echo "           Train them first:  npm run train:ml"
  fi
else
  echo "  skipping     ml-service/artifacts/*  (pass --with-artifacts to bake models in)"
fi
[ "${DRY_RUN}" = 0 ] && touch "${TARGET}/ml-service/artifacts/.gitkeep"

echo

if [ "${DRY_RUN}" = 1 ]; then
  echo "dry run complete — nothing was written."
  exit 0
fi

# --- 4. Commit (never push) -------------------------------------------------
if [ ! -d "${TARGET}/.git" ]; then
  cat <<EOF
Tree assembled, but ${TARGET} is not a git repository.

  cd "${TARGET}"
  git init && git lfs install
  git remote add origin https://huggingface.co/spaces/<user>/<space>
  git add -A && git commit -m "Deploy KrishiMitra API"
  git push origin main
EOF
  exit 0
fi

cd "${TARGET}"
if ! git lfs env >/dev/null 2>&1; then
  if [ "${WITH_ARTIFACTS}" = 1 ]; then
    # Hard stop rather than a warning: without the lfs filter, `git add` commits
    # a 116 MB blob as an ordinary object. The Hub then rejects the push, and
    # undoing it means rewriting history. Refusing now costs one command.
    echo "ERROR: git-lfs is not installed, and --with-artifacts wants to commit" >&2
    echo "       ~170 MB of models. Without git-lfs they would go into history as" >&2
    echo "       plain blobs, the Hub would reject the push, and cleaning that up" >&2
    echo "       means rewriting history." >&2
    echo >&2
    echo "       brew install git-lfs   # or: apt install git-lfs" >&2
    echo "       git lfs install" >&2
    echo >&2
    echo "The files are already copied into ${TARGET}; re-run this script after" >&2
    echo "installing git-lfs and it will pick up from here." >&2
    exit 1
  fi
  echo "WARNING: git-lfs is not installed. Install it before syncing models"
  echo "         (brew install git-lfs && git lfs install)."
fi
git add -A
if git diff --cached --quiet; then
  echo "no changes — the Space is already up to date."
  exit 0
fi
git status --short
git commit -q -m "Sync KrishiMitra API from source repo"
echo
echo "Committed. Push when you are ready — this publishes the Space:"
echo "  cd \"${TARGET}\" && git push origin main"
echo
echo "Then set the Space secrets (Settings -> Variables and secrets):"
echo "  AGROTECH_DATABASE_URL, AGROTECH_JWT_SECRET, AGROTECH_ENVIRONMENT=production"
echo "See spaces/api/DEPLOY.md for the full list."
