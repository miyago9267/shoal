"""Load settings from defaults, a JSON file and the environment.

Precedence (lowest to highest): built-in defaults, config file, environment.
"""
import copy
import json
import os

from .defaults import DEFAULTS

CONFIG_ENV = "APP_CONFIG"
LOG_LEVELS = ("debug", "info", "warning", "error")


class ConfigError(ValueError):
    """Raised for unreadable config files or invalid override values."""


def _parse_bool(raw):
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off", ""):
        return False
    raise ConfigError(f"not a boolean: {raw!r}")


def _parse_port(raw):
    try:
        port = int(raw)
    except ValueError:
        raise ConfigError(f"not a port number: {raw!r}") from None
    if not 0 < port < 65536:
        raise ConfigError(f"port out of range: {port}")
    return port


def _parse_log_level(raw):
    level = raw.strip().lower()
    if level not in LOG_LEVELS:
        raise ConfigError(f"unknown log level: {raw!r}")
    return level


# Environment variable -> (key path in the config dict, parser)
ENV_OVERRIDES = {
    "APP_HOST": (("server", "host"), str),
    "APP_PORT": (("server", "port"), _parse_port),
    "APP_LOG_LEVEL": (("log_level",), _parse_log_level),
    "APP_DEBUG": (("debug",), _parse_bool),
}


def _merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def _set_path(config, path, value):
    node = config
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def _read_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError("config file must contain a JSON object")
    return data


def load_config(path=None, environ=None):
    """Return the merged configuration dict."""
    environ = os.environ if environ is None else environ
    config = copy.deepcopy(DEFAULTS)
    path = path or environ.get(CONFIG_ENV)
    if path:
        _merge(config, _read_file(path))
    for name, (key_path, parser) in ENV_OVERRIDES.items():
        raw = environ.get(name)
        if raw is not None:
            _set_path(config, key_path, parser(raw))
    return config
