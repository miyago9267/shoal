`app/core.py` has grown into a ~550-line god module that mixes settings, errors, money helpers,
validation, models, pricing/discounts, inventory, the order service, reports and serialisation.
Please split it into a package `app/core/` made of at least four cohesive modules. No single
module should define more than half of the names in `__all__`, and the definitions should live in
the submodules (`app/core/__init__.py` only re-exports them).

This is a pure refactor: behaviour must not change, and every name currently in
`app.core.__all__` must still work as `from app.core import X` (and via `from app.core import *`).
Other modules (`app/api.py`, `app/catalog.py`, `app/cli.py`) must keep working unchanged, and each
new submodule must be importable on its own, so watch out for circular imports between the
pieces.
