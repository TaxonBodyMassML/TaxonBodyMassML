# Organization Cutover Commands

Date: 2026-06-24

This command guide assumes:

1. TaxonBodyMassML repository is transferred to the TaxonBodyMassML organization.
2. Repository TaxonBodyMassML/taxonbodymassml.github.io exists.
3. Collaborator-owned site remains unchanged.

## 1. Clone the organization Pages repository

1. From any local directory:
   - git clone [https://github.com/TaxonBodyMassML/taxonbodymassml.github.io.git](https://github.com/TaxonBodyMassML/taxonbodymassml.github.io.git)

## 2. Sync static site from canonical repository

1. From canonical repository root:
   - cd /Users/novakm/Git/TaxonBodyMassML
2. Publish to local Pages clone:
   - ./scripts/publish_to_org_pages_repo.sh ../taxonbodymassml.github.io
3. Optional API base override during sync:
   - ./scripts/publish_to_org_pages_repo.sh ../taxonbodymassml.github.io <https://your-backend.example.com>

## 3. Commit and push Pages update

1. Enter Pages repository:
   - cd ../taxonbodymassml.github.io
2. Review changes:
   - git status --short
3. Commit and push:
   - git add -A
   - git commit -m "chore(pages): sync website from canonical repo export"
   - git push

## 4. Enable GitHub Pages (one-time)

1. Open repository settings for TaxonBodyMassML/taxonbodymassml.github.io.
2. Under Pages:
   - Source: Deploy from a branch
   - Branch: main
   - Folder: /(root)

## 5. Verify production site

1. Open [https://taxonbodymassml.github.io/](https://taxonbodymassml.github.io/).
2. Test species lookup from home page.
3. Test help page question loading and submission.
4. Confirm collaborator site still unchanged at:
   - [https://praterh.github.io/HaileysTaxonBodyMassML/](https://praterh.github.io/HaileysTaxonBodyMassML/)
