#!/usr/bin/env python3
"""Fixture guard-chain member.  argv[1] picks the behaviour; stdin is the raw hook payload.

allow | deny <reason> | garbage | unknown | exit1 | sleep | deny_if <needle> | record <file> (append stdin, allow)
"""
import json
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
    with open(sys.argv[2], "a", encoding="utf-8") as handle:
        handle.write(data + "\n")
