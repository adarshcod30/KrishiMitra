#!/usr/bin/env bash
# =============================================================================
# 20 — Create Secret Manager secrets and grant the runtime service accounts
#      access to exactly the ones they need.
#
#   ./deploy/20-secrets.sh                 # prompt for anything missing
#   ./deploy/20-secrets.sh --grant-only    # skip prompts, just (re)apply IAM
#   ./deploy/20-secrets.sh --rotate agrotech-jwt-secret
#
# Secret VALUES are read from the terminal with `read -s` (never echoed, never
# stored in a file, never passed on a command line) or generated locally with
# openssl. They are piped to gcloud on stdin.
#
# Existing secrets are NEVER overwritten silently: a secret that already has a
# version is left alone unless you explicitly ask for --rotate.
#
# Prerequisite: ./deploy/10-provision.sh (which creates the two database
# secrets, because only it ever sees the generated database password).
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

load_env
require_cmd gcloud openssl
require_project

GRANT_ONLY=0
ROTATE_TARGETS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --grant-only) GRANT_ONLY=1; shift ;;
    --rotate)     ROTATE_TARGETS+=("${2:?--rotate needs a secret name}"); shift 2 ;;
    -h|--help)
      sed -n '2,26p' "${BASH_SOURCE[0]}"
      exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

# -----------------------------------------------------------------------------
# The catalogue.
#
#   name | kind | required | description
#
# kind:
#   generate — created locally with openssl; the operator never sees or types it
#   prompt   — read from the terminal, hidden
#   hash     — a password is prompted for, and only its bcrypt/pbkdf2 hash is
#              stored; the plaintext never leaves this process
# -----------------------------------------------------------------------------
SECRET_NAMES=(
  agrotech-jwt-secret
  agrotech-admin-password-hash
  agrotech-sarvam-api-key
  agrotech-brave-search-api-key
  agrotech-myscheme-api-key
  ee-service-account-json
)
SECRET_KINDS=(generate hash prompt prompt prompt prompt)
SECRET_REQUIRED=(yes yes no no no no)
SECRET_DESCRIPTIONS=(
  "HMAC signing key for API access tokens (AGROTECH_JWT_SECRET)"
  "Hash of the admin password (AGROTECH_ADMIN_PASSWORD_HASH)"
  "Sarvam AI translation key (AGROTECH_SARVAM_API_KEY) — Indic translation"
  "Brave Search key (AGROTECH_BRAVE_SEARCH_API_KEY) — news + knowledge search"
  "myScheme.gov.in key (AGROTECH_MYSCHEME_API_KEY) — government scheme lookup"
  "Earth Engine service-account JSON key (EE_SERVICE_ACCOUNT_JSON) — only if EE_USE_KEY=true"
)

# Secrets created by 10-provision.sh; this script only wires up their IAM.
DB_SECRETS=(krishimitra-db-password agrotech-database-url)

print_plan_header "Secret Manager"

cat <<PLAN
This script will, for each secret below:
  * create it if it does not exist (empty secrets are created but left without
    a version — the deploy script will then tell you which ones are unusable)
  * add a version only if the secret has none, or if you passed --rotate
  * grant roles/secretmanager.secretAccessor to the runtime service account
    that reads it, and to nothing else

Secrets
PLAN

for i in "${!SECRET_NAMES[@]}"; do
  req="optional"; [[ "${SECRET_REQUIRED[$i]}" == "yes" ]] && req="REQUIRED"
  printf '  %-32s %-9s %s\n' "${SECRET_NAMES[$i]}" "${req}" "${SECRET_DESCRIPTIONS[$i]}"
done
printf '\n  Already created by 10-provision.sh (IAM only):\n'
for s in "${DB_SECRETS[@]}"; do printf '  %-32s %s\n' "${s}" "database credentials"; done
printf '\n'

confirm "Proceed on ${PROJECT_ID}?" || die "aborted"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
secret_has_version() {
  gc secrets versions list "$1" --filter='state:ENABLED' --limit=1 \
    --format='value(name)' 2>/dev/null | grep -q .
}

ensure_secret_container() {
  local name="$1" description="$2"
  if secret_exists "${name}"; then
    skip "secret ${name} exists"
  else
    gc secrets create "${name}" \
      --replication-policy=automatic \
      --labels=app=krishimitra \
      >/dev/null
    ok "created secret ${name}  (${description})"
  fi
}

is_rotate_target() {
  local name="$1" t
  for t in "${ROTATE_TARGETS[@]:-}"; do
    [[ "${t}" == "${name}" ]] && return 0
  done
  return 1
}

# read_hidden <prompt-text> -> echoes the value on stdout
read_hidden() {
  local prompt="$1" value=""
  [[ -t 0 ]] || die "cannot prompt for '${prompt}' without a TTY. Add the version manually: gcloud secrets versions add <name> --data-file=-"
  read -r -s -p "    ${prompt}: " value </dev/tty
  printf '\n' >&2
  printf '%s' "${value}"
}

add_version() {
  local name="$1"
  # --data-file=- reads stdin, so the value never becomes a process argument.
  gc secrets versions add "${name}" --data-file=- >/dev/null
  ok "added a version to ${name}"
}

# -----------------------------------------------------------------------------
# 1. Create / populate
# -----------------------------------------------------------------------------
banner "Creating secrets"

for i in "${!SECRET_NAMES[@]}"; do
  name="${SECRET_NAMES[$i]}"
  kind="${SECRET_KINDS[$i]}"
  required="${SECRET_REQUIRED[$i]}"
  description="${SECRET_DESCRIPTIONS[$i]}"

  # Skip the Earth Engine key entirely under the recommended (keyless) setup.
  if [[ "${name}" == "ee-service-account-json" && "${EE_USE_KEY}" != "true" ]]; then
    skip "${name} — EE_USE_KEY=false, Earth Engine uses Workload Identity (recommended)"
    continue
  fi

  ensure_secret_container "${name}" "${description}"

  if [[ "${GRANT_ONLY}" == "1" ]]; then
    continue
  fi

  if secret_has_version "${name}" && ! is_rotate_target "${name}"; then
    skip "${name} already has a version (use --rotate ${name} to replace it)"
    continue
  fi

  case "${kind}" in
    generate)
      # 64 hex chars = 256 bits. Generated here so no human ever handles it.
      openssl rand -hex 32 | tr -d '\n' | add_version "${name}"
      ;;

    hash)
      info "${description}"
      if [[ "${required}" != "yes" ]] && ! confirm "    Set ${name} now?"; then
        skip "${name} left without a version"
        continue
      fi
      pw1="$(read_hidden "admin password for '${AGROTECH_ADMIN_USERNAME}'")"
      pw2="$(read_hidden "confirm")"
      [[ -n "${pw1}" ]] || die "empty password"
      [[ "${pw1}" == "${pw2}" ]] || die "passwords did not match"
      [[ ${#pw1} -ge 12 ]] || die "use at least 12 characters for an admin password"

      # Hash locally. The plaintext is passed to python on stdin, not argv, and
      # is discarded when this subshell exits.
      #
      # PBKDF2-HMAC-SHA256, 600k iterations (OWASP 2023 guidance), stored in the
      # portable "pbkdf2_sha256$iterations$salt$hash" form that Django/passlib
      # style verifiers understand. If ml-service standardises on bcrypt
      # instead, replace this block with:
      #   python -c 'import bcrypt,sys; print(bcrypt.hashpw(sys.stdin.buffer.read().strip(), bcrypt.gensalt()).decode())'
      # The python program is single-quoted on purpose: the `$` characters below
      # belong to the Python f-string, not to the shell.
      # shellcheck disable=SC2016
      printf '%s' "${pw1}" | python3 -c '
import base64, hashlib, os, sys

password = sys.stdin.buffer.read()
iterations = 600_000
salt = os.urandom(16)
digest = hashlib.pbkdf2_hmac("sha256", password, salt, iterations)

def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")

sys.stdout.write(f"pbkdf2_sha256${iterations}${b64(salt)}${b64(digest)}")
' | add_version "${name}"
      unset pw1 pw2
      ;;

    prompt)
      info "${description}"
      if [[ "${required}" != "yes" ]] && ! confirm "    Set ${name} now?"; then
        skip "${name} left without a version (the feature degrades gracefully)"
        continue
      fi
      if [[ "${name}" == "ee-service-account-json" ]]; then
        # A JSON key is multi-line; prompting for it character by character is
        # hopeless, so take a path instead.
        [[ -t 0 ]] || die "cannot prompt without a TTY"
        read -r -p "    path to the Earth Engine service-account JSON key: " key_path </dev/tty
        [[ -f "${key_path}" ]] || die "no such file: ${key_path}"
        python3 -c 'import json,sys; k=json.load(open(sys.argv[1])); assert k.get("type")=="service_account", "not a service account key"' "${key_path}" \
          || die "${key_path} is not a valid service-account key"
        gc secrets versions add "${name}" --data-file="${key_path}" >/dev/null
        ok "added a version to ${name} from ${key_path}"
        warn "now delete the local copy:  shred -u '${key_path}'  (or rm on macOS)"
      else
        value="$(read_hidden "value for ${name}")"
        if [[ -z "${value}" ]]; then
          skip "${name} left without a version (empty input)"
        else
          printf '%s' "${value}" | add_version "${name}"
        fi
        unset value
      fi
      ;;
  esac
done

# -----------------------------------------------------------------------------
# 2. Grant access — per secret, per service account. Nothing project-wide.
# -----------------------------------------------------------------------------
banner "Granting access"

info "API service account (${API_SA_EMAIL})"
for s in agrotech-database-url agrotech-jwt-secret agrotech-admin-password-hash \
         agrotech-sarvam-api-key agrotech-brave-search-api-key agrotech-myscheme-api-key; do
  if secret_exists "${s}"; then
    ensure_secret_accessor "${s}" "${API_SA_EMAIL}"
  else
    skip "${s} does not exist — nothing to grant"
  fi
done

# The web tier holds no application secrets: it proxies to the API and its only
# credential is its own Cloud Run identity. Deliberately nothing to grant here.
info "Web service account (${WEB_SA_EMAIL})"
skip "no secrets — the frontend authenticates to the API with its own identity"

info "Satellite service account (${SATELLITE_SA_EMAIL})"
if [[ "${EE_USE_KEY}" == "true" ]] && secret_exists ee-service-account-json; then
  ensure_secret_accessor "ee-service-account-json" "${SATELLITE_SA_EMAIL}"
else
  skip "no Earth Engine key secret — using Workload Identity"
fi

# krishimitra-db-password is intentionally NOT granted to any runtime identity.
# The API consumes the assembled agrotech-database-url instead; the raw password
# exists only so an operator can reconstruct or rotate the URL.
info "Raw database password"
skip "krishimitra-db-password is operator-only; no runtime service account can read it"

# -----------------------------------------------------------------------------
# 3. Report
# -----------------------------------------------------------------------------
banner "Secret status"

printf '  %-32s %-10s %s\n' "SECRET" "VERSIONS" "STATE"
for s in "${DB_SECRETS[@]}" "${SECRET_NAMES[@]}"; do
  if ! secret_exists "${s}"; then
    printf '  %-32s %-10s %s\n' "${s}" "-" "not created"
  elif secret_has_version "${s}"; then
    count="$(gc secrets versions list "${s}" --filter='state:ENABLED' --format='value(name)' | wc -l | tr -d ' ')"
    printf '  %-32s %-10s %s\n' "${s}" "${count}" "ready"
  else
    printf '  %-32s %-10s %s\n' "${s}" "0" "EMPTY — add a version before deploying"
  fi
done

printf '\n'
ok "Done. Next: ./deploy/30-deploy.sh"
