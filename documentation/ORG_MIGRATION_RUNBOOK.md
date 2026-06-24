# Organization Migration Runbook

This runbook migrates project ownership and hosting to the TaxonBodyMassML GitHub organization.

## Scope

1. Move repositories and governance to the TaxonBodyMassML organization.
2. Publish organization-owned website at [https://taxonbodymassml.github.io/](https://taxonbodymassml.github.io/).
3. Keep collaborator website unchanged.

## Non-Impact Policy

1. Do not edit or reconfigure collaborator assets:
   - [https://praterh.github.io/HaileysTaxonBodyMassML/](https://praterh.github.io/HaileysTaxonBodyMassML/)
   - Any collaborator-owned repository/settings behind that URL
2. Use collaborator site and repository content only as a source to copy from.
3. Perform all cutover work in organization-owned repositories.

## Target Repositories

1. Canonical code repository (after transfer):
   - [https://github.com/TaxonBodyMassML/TaxonBodyMassML](https://github.com/TaxonBodyMassML/TaxonBodyMassML)
2. Organization Pages repository:
   - [https://github.com/TaxonBodyMassML/taxonbodymassml.github.io](https://github.com/TaxonBodyMassML/taxonbodymassml.github.io)

## Implementation Steps

1. Transfer ownership of TaxonBodyMassML repository to the TaxonBodyMassML organization.
2. Create repository named taxonbodymassml.github.io in the organization.
3. Build export bundle from this repository using scripts/export_web_dev_for_org_pages.sh.
4. Copy website assets from the export bundle into the root of taxonbodymassml.github.io.
5. Ensure these files are present in Pages repository root:
   - index.html
   - help_page.html
   - data_visualization.html
   - alg.html
   - citations.html
   - style.css and other referenced CSS files
   - index.js, help.js, tutorial.js, and site_config.js
   - all referenced images and static assets
6. In taxonbodymassml.github.io, set site_config.js API_BASE_URL to the organization-owned backend URL.
7. Enable GitHub Pages in the taxonbodymassml.github.io repository (Deploy from branch: main, root).
8. Validate website and API functions using the verification checklist below.

## Export Command

1. Run from repository root:
   - ./scripts/export_web_dev_for_org_pages.sh
2. Optional custom output directory:
   - ./scripts/export_web_dev_for_org_pages.sh /tmp/taxonbodymassml-pages

## Publish To Org Pages Repository

1. Sync export into local clone of TaxonBodyMassML/taxonbodymassml.github.io:
   - ./scripts/publish_to_org_pages_repo.sh /path/to/taxonbodymassml.github.io
2. Optional backend override during sync:
   - ./scripts/publish_to_org_pages_repo.sh /path/to/taxonbodymassml.github.io <https://your-backend.example.com>

## Verification Checklist

1. [https://taxonbodymassml.github.io/](https://taxonbodymassml.github.io/) loads and renders the homepage.
2. Species lookup calls succeed from homepage.
3. Help page question load and submit endpoints succeed.
4. Static assets (images, CSS, JS) load without 404 errors.
5. Collaborator URL remains unchanged and operational.

## Consolidation Steps

1. Diff TaxonBodyMassML and TaxonBodyMassMLHaileys for unique files.
2. Copy only unique, needed assets into canonical repository with attribution in commit message.
3. Archive secondary repository with README note that canonical location is the org repository.

See documentation/CONSOLIDATION_PARITY_REPORT.md for current parity findings.
