# Preservation tests
Inherit root AGENTS.md. Expected surfaces must come from the reviewed historical
audit plus verified runtime behavior, never a blind snapshot of a broken bot.
Keep negative tests proving removals of aliases, slash entries, module/group
loading, help entries and feature wiring are caught. Do not weaken assertions,
skip tests, or mark a missing implementation present to get a green suite.
