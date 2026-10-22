# appcfg

Configuration loader for the order service.

Settings are resolved in this order (later wins):

1. Built-in defaults (`appcfg/defaults.py`)
2. A JSON config file, passed to `load_config(path)` or named by `APP_CONFIG`
3. Environment variable overrides

```python
from appcfg import load_config

config = load_config()
config["server"]["port"]
```

## Environment variables

| Variable        | Config key    | Notes                                   |
|-----------------|---------------|-----------------------------------------|
| `APP_CONFIG`    | -             | Path to the JSON config file            |
| `APP_HOST`      | `server.host` |                                         |
| `APP_PORT`      | `server.port` | Integer, 1-65535                        |
| `APP_LOG_LEVEL` | `log_level`   | One of `debug`, `info`, `warning`, `error` |
| `APP_DEBUG`     | `debug`       | `1/true/yes/on` or `0/false/no/off`     |

Invalid values raise `appcfg.ConfigError` at startup.

Run the tests with `python3 -m unittest discover -s tests -t .`.
