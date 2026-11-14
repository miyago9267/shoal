#!/usr/bin/env python3
"""Fixture guard-chain member.  argv[1] picks the behaviour; stdin is the raw hook payload.

allow | deny <reason> | garbage | unknown | exit1 | sleep | deny_if <needle> | record <file> (append stdin, allow)
context <text> (allow + advisory context) | deny_context <reason> <text> | env_context (allow + context
"host=<SHOAL_GUARD_HOST> event=<SHOAL_GUARD_EVENT>") | report (allow, self-reported member and version)
report_num (allow, numeric version) | flood (a deny followed by megabytes of padding on stdout and stderr)
"""
import json
import os
import sys
import time

mode = sys.argv[1] if len(sys.argv) > 1 else "allow"
data = sys.stdin.read()
if mode == "allow":
    print('{"decision":"allow"}')
elif mode == "deny":
    print(json.dumps({"decision": "deny", "reason": sys.argv[2] if len(sys.argv) > 2 else "no"}))
elif mode == "garbage":
    print("not json at all")
elif mode == "unknown":
    print('{"decision":"maybe"}')
elif mode == "exit1":
    print('{"decision":"deny","reason":"ignored because exit code is 1"}')
    sys.exit(1)
elif mode == "sleep":
    time.sleep(10)
elif mode == "deny_if":
    if sys.argv[2] in data:
        print(json.dumps({"decision": "deny", "reason": "saw " + sys.argv[2]}))
elif mode == "record":
    with open(sys.argv[2], "a", encoding="utf-8", newline="") as handle:
        handle.write(data + "\n")
elif mode == "context":
    print(json.dumps({"decision": "allow", "context": sys.argv[2]}))
elif mode == "deny_context":
    print(json.dumps({"decision": "deny", "reason": sys.argv[2], "context": sys.argv[3]}))
elif mode == "env_context":
    print(json.dumps({"decision": "allow", "context": "host=%s event=%s" % (
        os.environ.get("SHOAL_GUARD_HOST"), os.environ.get("SHOAL_GUARD_EVENT"))}))
elif mode == "report":
    print(json.dumps({"decision": "allow", "member": "fx-reporter", "version": "1.2.3", "ignored": {"x": 1}}))
elif mode == "report_num":
    print(json.dumps({"decision": "allow", "member": "fx-num", "version": 1, "extra": [1]}))
elif mode == "flood":
    sys.stderr.write("e" * (8 * 1024 * 1024))
    sys.stdout.write('{"decision":"deny","reason":"flooded"}' + " " * (8 * 1024 * 1024))
