In the `relay` package, please rename the `compute_backoff` function to `retry_delay`, and rename
the `backoff_base` config key to `retry_base_delay`. Update every caller, the config defaults and
validation, the README, and the tests so everything uses the new names. Behavior must stay exactly
the same. Don't keep the old names around as aliases; config files using `backoff_base` should now be
rejected like any other unknown key.
