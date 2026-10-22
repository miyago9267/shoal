"""Read-only consistency checks across the operational data structures."""


def check_accounts(accounts):
    """Return problems found in billing accounts (list of strings)."""
    problems = []
    seen = set()
    for acct in accounts:
        ident = acct.get("id")
        if not ident:
            problems.append("account without id")
            continue
        if ident in seen:
            problems.append("duplicate account %s" % ident)
        seen.add(ident)
        if acct["balance"] < 0:
            problems.append("negative balance on %s" % ident)
        if acct["balance"] > acct["limit"]:
            problems.append("%s is over its limit" % ident)
    return problems


def check_stock(stock):
    problems = []
    for sku, qty in sorted(stock.items()):
        if not isinstance(qty, int):
            problems.append("%s: quantity is not an int" % sku)
        elif qty < 0:
            problems.append("%s: negative quantity" % sku)
    return problems


def check_jobs(jobs):
    """Detect unknown dependencies and dependency cycles."""
    names = {j["name"] for j in jobs}
    problems = []
    graph = {}
    for job in jobs:
        deps = list(job.get("after", ()))
        graph[job["name"]] = deps
        for dep in deps:
            if dep not in names:
                problems.append("%s depends on unknown job %s" % (job["name"], dep))
    state = {}

    def visit(node, trail):
        if state.get(node) == "done":
            return
        if state.get(node) == "open":
            problems.append("cycle: " + " -> ".join(trail + [node]))
            return
        state[node] = "open"
        for dep in graph.get(node, ()):
            if dep in graph:
                visit(dep, trail + [node])
        state[node] = "done"

    for name in sorted(graph):
        visit(name, [])
    return problems


def check_cache(cache):
    problems = []
    if len(cache) > cache.capacity:
        problems.append("cache over capacity")
    if cache.hits < 0 or cache.misses < 0:
        problems.append("negative counters")
    return problems


def report(*sections):
    """Join the non-empty problem lists into one printable text block."""
    lines = []
    for title, problems in sections:
        if problems:
            lines.append(title)
            lines.extend("  - " + p for p in problems)
    return "\n".join(lines)
