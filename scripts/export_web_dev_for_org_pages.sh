#!/usr/bin/env bash
set -euo pipefail

# Builds a Pages-ready static site directory from web_dev content.
# This is copy-only and does not modify collaborator-owned repositories.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${ROOT_DIR}/web_dev"
OUTPUT_DIR="${1:-${ROOT_DIR}/build/org-pages-site}"

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "Source directory not found: ${SOURCE_DIR}" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"

# Copy static site assets to output while excluding backend/runtime files.
rsync -a --delete \
  --delete-excluded \
  --exclude '.DS_Store' \
  --exclude 'node_modules' \
  --exclude '.env' \
  --exclude '.stylelintrc.json' \
  --exclude 'Procfile' \
  --exclude 'requirements.txt' \
  --exclude 'prototype_lookup.py' \
  --exclude 'more_questions_db.py' \
  --exclude 'routes/' \
  --exclude 'package.json' \
  --exclude 'package-lock.json' \
  "${SOURCE_DIR}/" "${OUTPUT_DIR}/"

echo "Export complete."
echo "Source: ${SOURCE_DIR}"
echo "Output: ${OUTPUT_DIR}"
echo "Next step: push ${OUTPUT_DIR} contents to TaxonBodyMassML/taxonbodymassml.github.io root branch."
