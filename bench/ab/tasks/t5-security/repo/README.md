# filesrv

Small helpers that serve static files for the docs preview server.

```python
from filesrv import serve_file

resp = serve_file("/srv/site", "/docs/guide/intro.txt")
resp.status, resp.content_type, resp.body
```

Request paths may carry a query string and percent-encoded characters.
Directory requests are answered with their `index.html` when one exists.

Run the tests with `python3 -m unittest discover -s tests -t .`.
