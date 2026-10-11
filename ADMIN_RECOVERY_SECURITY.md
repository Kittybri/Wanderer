# Admin and history recovery permission review

The old `!rebuildmemory`, `!rebuildrank`, `!rebuildstats` and
`!rebuildrelationship` commands replay historical chat into state.
Guild administrator/manage-messages permission alone did not provide the
consent of users whose memories could be recreated after deletion.
For this scoped safety patch, only the explicitly configured `OWNER_ID`
may use these commands; no owner configured means no access.

`!bothealth` and `!backupmemory` previously had `if OWNER_ID and`
checks and therefore did not fail closed when the owner ID was unset.
These commands now deny access without a positive owner identity.

**Important remaining limitation:** Owner-only access does not make
cross-user history replay privacy safe. A future design should add a
user-scoped consent ledger, deletion tombstones and a reviewed preview
or replacement for all-user history reconstruction. Do not run history
rebuilds over users who have requested deletion. Do not enable them
as part of routine maintenance.

Command names/aliases, normal memory, Google, Tarot and voice are unchanged.
