"""Sweep open Dependabot pull requests and merge safe patch/minor updates."""
import json
import os
import re
import sys
import urllib.request

TITLE_RE = re.compile(r"bump\s+(?P<dep>\S+)\s+from\s+(?P<old>\S+)\s+to\s+(?P<new>\S+)", re.I)


def classify(title):
    match = TITLE_RE.search(title)
    if not match:
        return None, None, None, "unparseable"
    dep, old, new = match.group("dep"), match.group("old"), match.group("new")
    old_major = re.match(r"^(\d+)", old)
    new_major = re.match(r"^(\d+)", new)
    if not old_major or not new_major:
        return dep, old, new, "unparseable"
    reason = "eligible" if old_major.group(1) == new_major.group(1) else "major"
    return dep, old, new, reason


def api(method, path, token, body=None):
    url = "https://api.github.com" + path
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("Authorization", "Bearer " + token)
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw
        return error.code, payload


def main():
    token, repo = os.environ.get("GH_TOKEN"), os.environ.get("REPO")
    if not token or not repo:
        print("GH_TOKEN and REPO are required", file=sys.stderr)
        return 1
    prs = []
    page = 1
    while True:
        status, payload = api("GET", "/repos/%s/pulls?state=open&per_page=100&page=%d" % (repo, page), token)
        if status < 200 or status >= 300:
            print("Cannot list pull requests (HTTP %d): %s" % (status, payload), file=sys.stderr)
            return 1
        if not isinstance(payload, list):
            print("Cannot list pull requests: unexpected response", file=sys.stderr)
            return 1
        prs.extend(pr for pr in payload if pr.get("user", {}).get("login") == "dependabot[bot]")
        if len(payload) < 100:
            break
        page += 1

    rows = []
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    for pr in prs:
        number, title = pr["number"], pr.get("title", "")
        dep, old, new, classification = classify(title)
        dep_display, old_display, new_display = dep or "?", old or "?", new or "?"
        if classification != "eligible":
            reason = {"major": "skip-major", "unparseable": "unparseable"}[classification]
            rows.append(("SKIP", number, dep_display, old_display, new_display, reason))
            continue
        status, detail = api("GET", "/repos/%s/pulls/%d" % (repo, number), token)
        if status < 200 or status >= 300:
            rows.append(("FAIL", number, dep_display, old, new, "pull-request HTTP %d: %s" % (status, detail)))
            continue
        if detail.get("mergeable_state") == "dirty":
            rows.append(("SKIP", number, dep, old, new, "conflict"))
            continue
        sha = detail.get("head", {}).get("sha")
        status, checks = api("GET", "/repos/%s/commits/%s/check-runs?per_page=100" % (repo, sha), token)
        if status < 200 or status >= 300:
            rows.append(("FAIL", number, dep, old, new, "check-runs HTTP %d: %s" % (status, checks)))
            continue
        check = next((c for c in checks.get("check_runs", []) if c.get("name") == "validate-manifests"), None)
        if not check or check.get("status") != "completed":
            rows.append(("SKIP", number, dep, old, new, "checks-pending"))
            continue
        if check.get("conclusion") != "success":
            rows.append(("SKIP", number, dep, old, new, "checks-failed"))
            continue
        if dry_run:
            rows.append(("MERGE", number, dep, old, new, "would-merge"))
            continue
        status, result = api("PUT", "/repos/%s/pulls/%d/merge" % (repo, number), token, {"merge_method": "merge"})
        if status < 200 or status >= 300:
            rows.append(("FAIL", number, dep, old, new, "merge HTTP %d: %s" % (status, result)))
        else:
            rows.append(("MERGE", number, dep, old, new, "merged"))

    for action, number, dep, old, new, reason in rows:
        print("%s  #%d  %s %s -> %s  (%s)" % (action, number, dep, old, new, reason))
    counts = {key: sum(1 for row in rows if row[0] == key) for key in ("MERGE", "SKIP", "FAIL")}
    print("Summary: %d merged, %d skipped, %d failed" % (counts["MERGE"], counts["SKIP"], counts["FAIL"]))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write("## Dependabot auto-merge sweep\n\n| Action | PR | Dependency | Old | New | Reason |\n|---|---:|---|---|---|---|\n")
            for action, number, dep, old, new, reason in rows:
                output.write("| %s | #%d | %s | %s | %s | %s |\n" % (action, number, dep, old, new, reason))
            output.write("\n**Summary:** %d merged, %d skipped, %d failed\n" % (counts["MERGE"], counts["SKIP"], counts["FAIL"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
