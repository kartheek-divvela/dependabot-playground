#!/usr/bin/env python3
from __future__ import annotations
import json, re, sys
import xml.etree.ElementTree as ET
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[2]
REQ_RE = re.compile(r"^[A-Za-z0-9._-]+==[^\s]+$")
def tag_name(tag): return tag.rsplit("}", 1)[-1]
def check_pom(path):
    try: root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc: raise ValueError(f"invalid XML: {exc}") from exc
    for dependency in root.iter():
        if tag_name(dependency.tag) == "dependency":
            fields = {tag_name(c.tag): (c.text or "").strip() for c in dependency}
            for field in ("groupId", "artifactId", "version"):
                if not fields.get(field): raise ValueError(f"dependency has empty or missing {field}")
def check_package_json(path):
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc: raise ValueError(f"invalid JSON: {exc}") from exc
    for section in ("dependencies", "devDependencies"):
        values = data.get(section)
        if not isinstance(values, dict): raise ValueError(f"missing or invalid {section}")
        for name, version in values.items():
            if not isinstance(version, str) or not version.strip(): raise ValueError(f"{section} dependency {name!r} has empty version")
def check_requirements(path):
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if line and not line.startswith("#") and not REQ_RE.fullmatch(line): raise ValueError(f"line {number} is not pinned as NAME==VERSION: {line!r}")
def check_yaml(path):
    try:
        with path.open(encoding="utf-8") as handle: list(yaml.safe_load_all(handle))
    except (yaml.YAMLError, OSError) as exc: raise ValueError(f"invalid YAML: {exc}") from exc
def main():
    checks = ([(p, check_pom) for p in sorted(ROOT.rglob("pom.xml"))] + [(ROOT / "module-b/package.json", check_package_json)] + [(p, check_requirements) for p in sorted(ROOT.rglob("requirements*.txt"))] + [(p, check_yaml) for p in sorted((ROOT / ".github").rglob("*.y*ml"))])
    failures = 0
    for path, checker in checks:
        rel = path.relative_to(ROOT)
        try: checker(path)
        except (ValueError, UnicodeError) as exc: failures += 1; print(f"FAIL {rel}: {exc}")
        else: print(f"PASS {rel}")
    print(f"Summary: {len(checks)-failures} passed, {failures} failed, {len(checks)} total")
    return int(bool(failures))
if __name__ == "__main__": sys.exit(main())
