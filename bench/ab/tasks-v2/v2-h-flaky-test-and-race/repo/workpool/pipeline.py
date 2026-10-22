"""Multi-stage pipelines: each stage is a WorkerPool feeding the next one."""
import threading

from .pool import WorkerPool


class Stage:
    def __init__(self, name, fn, workers=2, retry=None):
        self.name = name
        self.fn = fn
        self.workers = workers
        self.retry = retry


class Pipeline:
    """Run items through ``stages`` in order and collect the final outputs.

    A stage function returns the value passed to the next stage, or ``None``
    to drop the item (a filter).
    """

    def __init__(self, stages):
        if not stages:
            raise ValueError("a pipeline needs at least one stage")
        self.outputs = []
        self._out_lock = threading.Lock()
        self._pools = []
        downstream = self._collect
        for stage in reversed(stages):
            pool = WorkerPool(self._forwarder(stage.fn, downstream),
                              workers=stage.workers, retry=stage.retry, name=stage.name)
            self._pools.insert(0, pool)
            downstream = pool.submit
        self._names = [s.name for s in stages]

    @staticmethod
    def _forwarder(fn, downstream):
        def handler(item):
            result = fn(item)
            if result is not None:
                downstream(result)
        return handler

    def _collect(self, item):
        with self._out_lock:
            self.outputs.append(item)

    def feed(self, items):
        for item in items:
            self._pools[0].submit(item)

    def close(self):
        """Drain stage by stage, upstream first, so nothing is in flight."""
        for pool in self._pools:
            pool.shutdown(wait=True)
        return self.outputs

    def stats(self):
        return {name: pool.stats() for name, pool in zip(self._names, self._pools)}

    def errors(self):
        return {name: list(pool.errors) for name, pool in zip(self._names, self._pools)}
