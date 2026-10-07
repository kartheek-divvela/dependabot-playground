#!/usr/bin/env python3
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

TITLE_RE = re.compile(r"bump\s+(?P<dep>\S+)\s+from\s+(?P<old>\S+)\s+to\s+(?P<new>\S+)", re.I)

def api(method, path, token, body=None):
    req = urllib.request.Request("https://api.github.com" + path, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.data = data
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode()
        try: payload = json.loads(raw)
        except ValueError: payload = raw
        return error.code, payload

def classify(title, include_majors):
    match = TITLE_RE.search(title)
    if not match: return None, None, None, "unparseable"
    dep, old, new = match.group("dep"), match.group("old"), match.group("new")
    om, nm = re.match(r"^(\d+)", old), re.match(r"^(\d+)", new)
    if not om or not nm: return dep, old, new, "unparseable"
    if om.group(1) != nm.group(1):
        return dep, old, new, "major-included" if include_majors else "major"
    return dep, old, new, "eligible"

def main():
    token, repo = os.environ.get("GH_TOKEN"), os.environ.get("REPO")
    if not token or not repo:
        print("GH_TOKEN and REPO are required", file=sys.stderr); return 1
    dry = os.environ.get("DRY_RUN", "false").lower() == "true"
    include = os.environ.get("INCLUDE_MAJORS", "false").lower() == "true"
    entries, page = [], 1
    while True:
        status, payload = api("GET", f"/repos/{repo}/issues?state=open&labels=dependabot&per_page=100&page={page}", token)
        if not 200 <= status < 300:
            print(f"Cannot list labelled issues (HTTP {status}): {payload}", file=sys.stderr); return 1
        if not isinstance(payload, list):
            print("Cannot list labelled issues: unexpected response", file=sys.stderr); return 1
        entries.extend(payload)
        if len(payload) < 100: break
        page += 1
    labelled_prs = [e for e in entries if "pull_request" in e]
    selected = []
    for e in labelled_prs:
        if e.get("user", {}).get("login") != "dependabot[bot]":
            print(f"LOUD: SKIP #{e.get('number')} (not-dependabot-authored)", file=sys.stderr)
        else: selected.append(e)
    print(f"Label selection: {len(labelled_prs)} labelled PRs, {len(selected)} Dependabot-authored PRs")
    rows = []
    for e in selected:
        n = e["number"]
        status, detail = api("GET", f"/repos/{repo}/pulls/{n}", token)
        if not 200 <= status < 300:
            rows.append(("FAIL", n, "?", "?", "?", f"pull-request HTTP {status}: {detail}")); continue
        dep, old, new, reason = classify(detail.get("title", ""), include)
        d, o, ne = dep or "?", old or "?", new or "?"
        if reason == "unparseable": rows.append(("SKIP", n, d, o, ne, reason)); continue
        if reason == "major": rows.append(("SKIP", n, d, o, ne, "major-excluded")); continue
        state = detail.get("mergeable_state")
        for attempt in range(3):
            if detail.get("mergeable") is not None and state not in (None, "unknown"): break
            if attempt == 2: break
            time.sleep(2)
            status, detail = api("GET", f"/repos/{repo}/pulls/{n}", token)
            if not 200 <= status < 300:
                rows.append(("FAIL", n, d, o, ne, f"pull-request HTTP {status}: {detail}")); break
            state = detail.get("mergeable_state")
        else: state = "unknown"
        if not 200 <= status < 300: continue
        if detail.get("mergeable") is None or state in (None, "unknown"):
            rows.append(("SKIP", n, d, o, ne, "mergeability-unknown")); continue
        if state == "dirty": rows.append(("SKIP", n, d, o, ne, "conflict")); continue
        sha = detail.get("head", {}).get("sha")
        status, checks = api("GET", f"/repos/{repo}/commits/{sha}/check-runs?per_page=100", token)
        if not 200 <= status < 300:
            rows.append(("FAIL", n, d, o, ne, f"check-runs HTTP {status}: {checks}")); continue
        check = next((c for c in checks.get("check_runs", []) if c.get("name") == "validate-manifests"), None)
        if not check or check.get("status") != "completed": rows.append(("SKIP", n, d, o, ne, "checks-pending")); continue
        if check.get("conclusion") != "success": rows.append(("SKIP", n, d, o, ne, "checks-failed")); continue
        if dry: rows.append(("WOULD-MERGE", n, d, o, ne, "eligible" if reason == "eligible" else reason)); continue
        status, result = api("PUT", f"/repos/{repo}/pulls/{n}/merge", token, {"merge_method": "merge", "sha": sha})
        rows.append(("MERGE" if 200 <= status < 300 else "FAIL", n, d, o, ne, "merged" if 200 <= status < 300 else f"merge HTTP {status}: {result}"))
    mode = "DRY RUN" if dry else "LIVE"
    print(f"MODE: {mode} (no merges performed)" if dry else "MODE: LIVE")
    for a,n,d,o,ne,r in rows: print(f"{a}  #{n}  {d} {o} -> {ne}  ({r})")
    counts = {k: sum(a == k for a,*_ in rows) for k in ("MERGE", "WOULD-MERGE", "SKIP", "FAIL")}
    print(f"Summary ({mode}): {counts['WOULD-MERGE'] if dry else counts['MERGE']} {'would merge' if dry else 'merged'}, {counts['SKIP']} skipped, {counts['FAIL']} failed")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("## Dependabot auto-merge sweep\n\n| Action | PR | Dependency | Old | New | Reason |\n|---|---:|---|---|---|---|\n")
            for a,n,d,o,ne,r in rows: out.write(f"| {a} | #{n} | {d} | {o} | {ne} | {r} |\n")
    return 0

if __name__ == "__main__": sys.exit(main())
