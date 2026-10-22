"""Stage 5: present the aggregate."""
import json


def human_bytes(n):
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def build(summary, skipped):
    return {**summary, "skipped": skipped}


def to_text(report):
    lines = [f"requests: {report['total_requests']}  "
             f"bytes: {human_bytes(report['total_bytes'])}  skipped: {report['skipped']}",
             "", f"{'USER':<16}{'REQ':>8}{'ERR':>6}{'SESS':>6}  BYTES"]
    ranked = sorted(report["users"].items(), key=lambda kv: (-kv[1]["bytes"], kv[0]))
    for name, row in ranked:
        lines.append(f"{name:<16}{row['requests']:>8}{row['errors']:>6}"
                     f"{row['sessions']:>6}  {human_bytes(row['bytes'])}")
    lines += ["", f"{'PLAN':<16}{'REQ':>8}  BYTES"]
    for plan, row in sorted(report["plans"].items()):
        lines.append(f"{plan:<16}{row['requests']:>8}  {human_bytes(row['bytes'])}")
    return "\n".join(lines)


def to_json(report):
    return json.dumps(report, indent=2, sort_keys=True)
