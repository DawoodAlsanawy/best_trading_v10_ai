#!/usr/bin/env python3
"""
kill_switch.py — Trigger the bot's kill switch.

Usage:
    export KILL_SWITCH_SECRET="my-secret"
    python3 kill_switch.py --reason "manual test"
    python3 kill_switch.py --reason "fixing bug" --file kill_switch.json
"""
import argparse, hashlib, hmac, json, os, sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reason", required=True)
    p.add_argument("--file", default="kill_switch.json")
    p.add_argument("--secret", default=os.environ.get("KILL_SWITCH_SECRET", ""))
    args = p.parse_args()

    if not args.secret:
        print("ERROR: KILL_SWITCH_SECRET env var not set")
        sys.exit(1)

    token = hmac.new(args.secret.encode(), args.reason.encode(),
                     hashlib.sha256).hexdigest()
    data = {
        "state": "TRIGGERED",
        "reason": args.reason,
        "token": token,
        "issued_at": __import__("time").time(),
    }
    with open(args.file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"✓ Kill switch triggered: {args.file}")
    print(f"  reason: {args.reason}")
    print(f"  token : {token[:16]}...")


if __name__ == "__main__":
    main()
