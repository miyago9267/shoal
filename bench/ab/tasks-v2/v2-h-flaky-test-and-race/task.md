Our CI is flaky on `test_pool`, please fix the root cause, don't just retry. In production we
also see jobs that finish with fewer results than items submitted, both with `map_unordered`
and with pipelines. The README describes the guarantees `WorkerPool` is supposed to give;
make the implementation actually honour them, and keep the public API (`WorkerPool`,
`submit`, `shutdown(wait=..., timeout=...)`, `stats()`, `errors`, `closed`, the context
manager, `RetryPolicy`, `map_unordered`, `Pipeline`) as it is. Adding sleeps or retries to
the tests is not a fix.
