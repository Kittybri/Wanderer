# Preservation contract

Root/nested AGENTS.md and CODEOWNERS provide durable instructions and review routing.
The runtime test is independent of the manifest writer: it imports the actual bot,
walks prefix aliases and slash subcommands, checks dynamic modules/cogs, captures
real help output, and verifies each PRESENT feature's runtime wiring/privacy stages.
Negative regression tests must demonstrate every failure category.

## Intentional changes
Do not regenerate expectations to hide a regression. First get explicit user
authorization for the named removal/rename. Add a record to
preservation/intentional_changes.json with authorization, removed_surfaces, reason,
replacement/migration, privacy_impact, and validation. Update historical audit
disposition and manifests together. Review must verify the authorization; a JSON
record cannot authenticate the human by itself. tools/check_preservation_diff.py
checks manifest shrinkage against the PR base in CI.

The current command manifest is finalized only after historical comparison. Every
legacy discrepancy is retained in preservation/historical_audit.json; unresolved
features are NOT represented as PRESENT. Source hashes identify snapshots.
Runtime command counts are not equivalent to full behavior validation.

## GitHub recommendations (not enabled automatically)
Require pull requests, successful preservation/full-suite checks, Code Owner review,
dismissal of stale approvals, and no force pushes on release/default branches.
Protect manifests, these tests, and workflow changes from unreviewed bypass.
CODEOWNERS alone does not prevent edits, and local AGENTS.md is not a security
boundary. Branch policies remain unchanged to avoid blocking the existing stack.

## Validation
Run .venv/bin/python -m pytest before deployment; run at least
tests/test_preservation.py and tests/test_tarot_restoration.py before commits.
Use synthetic isolated stores and no external provider calls in tests.
Do not deploy while a supported feature manifest or registration assertion fails.
