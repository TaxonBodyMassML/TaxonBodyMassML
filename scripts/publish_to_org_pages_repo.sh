#!/usr/bin/env bash
set -euo pipefail

# Syncs a static site bundle from web_dev into a local clone of
# TaxonBodyMassML/taxonbodymassml.github.io.
#
# Usage:
#   ./scripts/publish_to_org_pages_repo.sh /path/to/taxonbodymassml.github.io [api_base_url]

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 /path/to/taxonbodymassml.github.io [api_base_url]" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAGES_REPO_PATH="$(cd "$1" && pwd)"
API_BASE_URL="${2:-}"
EXPORT_DIR="${ROOT_DIR}/build/org-pages-site"

if [[ ! -d "${PAGES_REPO_PATH}/.git" ]]; then
  echo "Target path is not a git repository: ${PAGES_REPO_PATH}" >&2
  exit 1
fi

if [[ "$(basename "${PAGES_REPO_PATH}")" != "taxonbodymassml.github.io" ]]; then
  echo "Warning: target repository directory name is not taxonbodymassml.github.io" >&2
fi

"${ROOT_DIR}/scripts/export_web_dev_for_org_pages.sh" "${EXPORT_DIR}"

if [[ -n "${API_BASE_URL}" ]]; then
  sed -E -i.bak "s#API_BASE_URL: \"[^\"]+\"#API_BASE_URL: \"${API_BASE_URL}\"#" "${EXPORT_DIR}/site_config.js"
  rm -f "${EXPORT_DIR}/site_config.js.bak"
fi

rsync -a --delete --exclude '.git/' "${EXPORT_DIR}/" "${PAGES_REPO_PATH}/"

echo "Sync complete."
echo "Source export: ${EXPORT_DIR}"
echo "Target repo: ${PAGES_REPO_PATH}"
echo ""
echo "Next commands:"
echo "  cd ${PAGES_REPO_PATH}"
echo "  git status --short"
echo "  git add -A"
echo "  git commit -m 'chore(pages): sync website from canonical repo export'"
echo "  git push"
