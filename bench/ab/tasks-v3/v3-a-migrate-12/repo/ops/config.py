"""Static configuration shared by the operational modules."""

DEFAULTS = {
    "billing": {"limit": 500_000, "currency": "USD"},
    "inventory": {"low_water": 5, "warehouse": "main"},
    "mailer": {"max_attempts": 3, "sender": "ops@example.invalid"},
    "scheduler": {"tick_seconds": 30},
    "cache": {"capacity": 128, "verbose": False},
    "backup": {"min_interval": 86400, "keep": 7},
    "syncer": {"max_push": 100},
}


def get(section, key, overrides=None):
    """Look up ``key`` in ``section``; overrides win over defaults."""
    if overrides and key in overrides.get(section, {}):
        return overrides[section][key]
    return DEFAULTS[section][key]


def sections():
    return sorted(DEFAULTS)


def validate(overrides):
    """Return a list of problems with an overrides mapping (empty if fine)."""
    problems = []
    for section, values in overrides.items():
        if section not in DEFAULTS:
            problems.append("unknown section %s" % section)
            continue
        for key in values:
            if key not in DEFAULTS[section]:
                problems.append("unknown key %s.%s" % (section, key))
    return problems
