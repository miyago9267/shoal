# ops

Small operations toolkit: billing, inventory, mail, scheduling, auth, caching,
import/export, sync, backup, notifications and reports.

Every module used to write to the deprecated `ops.legacy.legacy_log(msg, level)`
API. New code uses structured events, `ops.log.event(name, **fields)`. See
`docs/migration.md` for the conventions and the list of modules still on the old
API.

Run the tests with `python3 -m unittest discover -s tests -t .`.
