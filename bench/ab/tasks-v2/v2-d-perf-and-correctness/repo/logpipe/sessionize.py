"""Stage 3: group each user's requests into sessions."""

SESSION_GAP = 30 * 60


def sessionize(events, gap=SESSION_GAP):
    """Set ``event.session``; returns the events sorted by time.

    A user's request joins their latest session when it comes no more than
    ``gap`` seconds after that session's previous request.
    """
    ordered = sorted(events, key=lambda e: (e.ts, e.request_id))
    sessions = []  # [user_id, last_ts, session_id]
    for event in ordered:
        latest = None
        for session in sessions:
            if session[0] == event.user_id:
                latest = session
        if latest is not None and event.ts - latest[1] <= gap:
            latest[1] = event.ts
            event.session = latest[2]
        else:
            sid = len(sessions)
            sessions.append([event.user_id, event.ts, sid])
            event.session = sid
    return ordered
