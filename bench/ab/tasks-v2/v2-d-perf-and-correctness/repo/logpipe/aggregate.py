"""Stage 4: drop retried duplicates and total everything up."""


def dedupe(events):
    """Keep the first line of each request (retries are logged again)."""
    seen = []
    kept = []
    for event in events:
        key = (event.user_id, event.ts)
        if key in seen:
            continue
        seen.append(key)
        kept.append(event)
    return kept


def _bucket(table, name, fields):
    if name not in table:
        table[name] = dict.fromkeys(fields, 0)
    return table[name]


def aggregate(events):
    users, plans, sessions = {}, {}, {}
    total_requests = total_bytes = 0
    for event in dedupe(events):
        user = _bucket(users, event.user.name, ("requests", "bytes", "errors"))
        user["requests"] += 1
        user["bytes"] += event.bytes
        if event.status >= 500:
            user["errors"] += 1
        sessions.setdefault(event.user.name, set()).add(event.session)
        plan = _bucket(plans, event.user.plan, ("requests", "bytes"))
        plan["requests"] += 1
        plan["bytes"] += event.bytes
        total_requests += 1
        total_bytes += event.bytes
    for name, user in users.items():
        user["sessions"] = len(sessions[name])
    return {"total_requests": total_requests, "total_bytes": total_bytes,
            "users": users, "plans": plans}
