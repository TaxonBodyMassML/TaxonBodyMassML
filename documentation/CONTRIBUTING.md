## Contributing Guide

How to set up, code, test, review, and release so contributions meet our Definition of Done.

## Code of Conduct

All project interactions should allign with the guidelines described in the Oregon State Univesiry Code of Student Conduct: https://studentlife.oregonstate.edu/sites/studentlife.oregonstate.edu/files/student-conduct-community-standards/Code/code_of_conduct_comp.pdf

## Getting Started

List prerequisites, setup steps, environment variables/secrets handling, and how to run the app locally.

In order to use our application, there are no prerequisite installations or set-up steps. The organization-owned site target is: [https://taxonbodymassml.github.io/](https://taxonbodymassml.github.io/)

Migration boundary: the collaborator-owned site at [https://praterh.github.io/HaileysTaxonBodyMassML/](https://praterh.github.io/HaileysTaxonBodyMassML/) is treated as read-only source content and must not be modified during migration.

## Branching & Workflow

Describe the workflow (e.g., trunk-based or GitFlow), default branch, branch naming, and when to rebase vs. merge.

We employ a GitFlow branching workflow, with each feature being given its own independent branch. For example, the web-dev branch is the only branch to which code for the UI implementation is pushed. Rebasing is often considered good for independent feature branches, but merging is required in any pull request to the main branch; we will adhere to this common practice. 

## Issues & Planning

Explain how to file issues, required templates/labels, estimation, and triage/assignment practices. (Work in progress)

We will use GitHub Issues

## Commit Messages

We will use Conventional Commits, which follow the template: type(scope): description

Examples:
- docs(contributing): completed the commit messages section in contributing.md
- feat(data): log transformed the species mass data
- feat(ui): included histograms on data visualization tab

Reference issues by including either "Fixes #xyz" or "Refs #xyz" at the end of a commit.

## Code Style, Linting & Formatting

Name the formatter/linter, config file locations, and the exact commands to check/fix locally. (Work in progress)

## Testing

Define required test types, how to run tests, expected coverage thresholds, and when new/updated tests are mandatory.

Unit Tests: HTTP GET returns status 200 OK, model returns correct structure response upon query
Performance Test: 1 query takes less than 1 minute
Security Scan: API type-checking verification, no .env files are included in the commit/PR

These tests run automatically upon any commit or Pull Request.  Any time an independent feature is added to the main branch, a corresponding unit test should be added to the testing framework. 

## Pull Requests & Reviews

Outline PR requirements (template, checklist, size limits), reviewer expectations, approval rules, and required status checks.

The PR template and checklist can be found in .github/PULL_REQUEST_TEMPLATE.md

## CI/CD

Link to pipeline definitions, list mandatory jobs, how to view logs/re-run jobs, and what must pass before merge/release.

Located in ./github/workflows and triggers after every push or PR to the main branch

## Security & Secrets

State how to report vulnerabilities, prohibited patterns (hard-coded secrets), dependency update policy, and scanning tools.  (Work in progress)

## Documentation Expectations

Specify what must be updated (README, docs/, API refs, CHANGELOG) and docstring/comment standards.  (Work in progress)

## Release Process

Describe versioning scheme, tagging, changelog generation, packaging/publishing steps, and rollback process.  (Work in progress)
 
Each version will be automatically named with an iterating version number after the decimal point.  All pre-release versions will be formatted as 0.X.  All release versions will be formatted as 1.X.  

## Support & Contact

Provide maintainer contact channel, expected response windows, and where to ask questions. (Work in progress)

The best contact channel will be Mark Novak: mark.novak@oregonstate.edu

