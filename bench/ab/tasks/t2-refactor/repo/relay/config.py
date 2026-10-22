"""Configuration loading for the relay worker."""
import json

DEFAULTS = {
    "max_attempts": 5,
    "backoff_base": 1.0,
    "max_delay": 60.0,
}


def load_config(path=None, overrides=None):
    """Return DEFAULTS merged with a JSON file and explicit overrides."""
    cfg = dict(DEFAULTS)
    if path:
        with open(path) as fh:
            data = json.load(fh)
        unknown = set(data) - set(DEFAULTS)
        if unknown:
            raise KeyError(f"unknown config keys: {sorted(unknown)}")
        cfg.update(data)
    if overrides:
        cfg.update(overrides)
    if cfg["backoff_base"] < 0:
        raise ValueError("backoff_base must be >= 0")
    return cfg
