"""Outside watcher: run it from somewhere that is NOT one of the apps (a cron, a GitHub Action, any other computer).

    python tools/outside_watch.py targets.json

Reads each app's health page and checks its real freshness, not just "the site answers". Prints one line per
app and exits 1 if anything is wrong, so whatever runs it can tell a person (a failed run is the alert).
No secrets and no third-party packages. See tools/outside_watch.example.json for the targets format.
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


def fetch(url, timeout=20):
    """(http status, body text); a network failure is status 0."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "irr-outside-watch"}), timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001  DNS, timeout, TLS: all mean "cannot reach it"
        return 0, str(e)


def _dig(data, path):
    for part in path.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def _age_seconds(value, now):
    try:
        return (now - datetime.fromisoformat(str(value).replace("Z", "+00:00"))).total_seconds()
    except ValueError:
        return None


def check_target(target, get=fetch, now=None):
    """Problems for one app (empty list = fine). Checks: {field, max} number, {field, max_age_s} timestamp, {field, equals}."""
    now = now or datetime.now(timezone.utc)
    status, text = get(target["url"])
    if status != 200:
        return [f"health page answered {status or 'nothing'}"]
    try:
        data = json.loads(text)
    except ValueError:
        return ["health page is not JSON"]
    problems = []
    if isinstance(data, dict) and (data.get("ok") is False or data.get("status") in ("down", "error")):
        problems.append("app says it is not healthy")
    for c in target.get("checks", []):
        value = _dig(data, c["field"])
        if value is None:
            problems.append(f"{c['field']} is missing")
        elif "equals" in c and value != c["equals"]:
            problems.append(f"{c['field']} is {value}, expected {c['equals']}")
        elif "max" in c and not (isinstance(value, (int, float)) and value <= c["max"]):
            problems.append(f"{c['field']} is {value}, more than {c['max']}")
        elif "max_age_s" in c:
            age = _age_seconds(value, now)
            if age is None or age > c["max_age_s"]:
                problems.append(f"{c['field']} is {'unreadable' if age is None else f'{int(age // 60)} minutes old'}")
    return problems


def main(path, get=fetch):
    bad = 0
    for t in json.load(open(path)):
        problems = check_target(t, get)
        bad += bool(problems)
        print(f"{'PROBLEM' if problems else 'OK'}  {t['name']}" + (": " + "; ".join(problems) if problems else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: outside_watch.py targets.json")
    sys.exit(main(sys.argv[1]))
