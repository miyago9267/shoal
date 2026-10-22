"""Built-in defaults. Every key here may be overridden by the config file."""

DEFAULTS = {
    "server": {"host": "127.0.0.1", "port": 8080},
    "database": {"url": "sqlite:///app.db", "pool_size": 5},
    "log_level": "info",
    "debug": False,
}
