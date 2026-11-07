"""AC-11: which 025 Angular keys does a service really use, and are they in its profile?

Usage (from the repo root): python specs/026-service-scanner/ac11/keys025.py <service> <profile.json>
Run the scan with --max-locations 100000 first so no location is truncated.
"""

import json
import re
import subprocess
import sys
import glob
import collections

root, prof_path = sys.argv[1], sys.argv[2]
prof = json.load(open(prof_path))
have = set()
for sec in (
    "symbols",
    "members",
    "side_effect_imports",
    "templates",
    "dependencies",
    "config",
):
    have |= {e["key"] for e in prof[sec]}
keys = set()
for p in glob.glob("runs/canonical/angular-*-canonical.jsonl"):
    for line in open(p):
        k = json.loads(line).get("canonical", {}).get("key", "")
        if k.startswith(("npm:", "syntax:angular-template", "cfg:")):
            keys.add(k)
files = subprocess.run(
    ["git", "ls-files"], cwd=root, capture_output=True, text=True
).stdout.split()
ts = {
    f: open(f"{root}/{f}", encoding="utf-8", errors="replace").read()
    for f in files
    if f.endswith(".ts")
}
html = {
    f: open(f"{root}/{f}", encoding="utf-8", errors="replace").read()
    for f in files
    if f.endswith(".html")
}
pkg = json.load(open(f"{root}/package.json"))
deps = {
    n
    for s in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    )
    for n in pkg.get(s, {})
}
imp_re = re.compile(r"import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*'([^']+)'", re.S)
imports = collections.defaultdict(set)  # (pkg, sym) -> files
for f, t in ts.items():
    for names, spec in imp_re.findall(t):
        for n in names.split(","):
            n = n.strip().replace("type ", "").split(" as ")[0].strip()
            if n:
                imports[(spec, n)].add(f)


def load_jsonc(path):
    t = open(path).read()
    t = re.sub(r"//[^\n]*|/\*.*?\*/", "", t, flags=re.S)
    t = re.sub(r",\s*([}\]])", r"\1", t)
    return json.loads(t)


cfgs = {}
for name in ("angular.json", "tsconfig.json", "package.json"):
    try:
        cfgs[name] = load_jsonc(f"{root}/{name}")
    except Exception:
        pass


def json_has(data, parts):
    if not parts:
        return True
    head, rest = parts[0], parts[1:]
    if head == "*" and isinstance(data, dict):
        return any(json_has(v, rest) for v in data.values())
    if isinstance(data, dict) and head in data:
        return json_has(data[head], rest)
    if isinstance(data, list) and head.isdigit() and int(head) < len(data):
        return json_has(data[int(head)], rest)
    return False


alltpl = "\n".join(html.values()) + "\n".join(ts.values())


def used(k):
    if k.startswith("npm:"):
        body = k[4:]
        if "#" not in body:
            return body in deps
        p, sym = body.split("#", 1)
        if "." in sym:
            s, m = sym.split(".", 1)
            fs = imports.get((p, s), set())
            return any(
                re.search(rf"\b{re.escape(s)}\??\.{re.escape(m)}\b", ts[f])
                or (
                    re.search(rf"@{re.escape(s)}\(", ts[f])
                    and re.search(rf"\b{re.escape(m)}\s*:", ts[f])
                )
                for f in fs
            )
        return (p, sym) in imports
    if k.startswith("syntax:angular-template#"):
        tok = k.split("#", 1)[1]
        if tok.startswith("pipe:"):
            return bool(re.search(rf"\|\s*{re.escape(tok[5:])}\b", alltpl))
        if tok.startswith("@"):
            return bool(re.search(rf"{re.escape(tok)}\s*[({{]", alltpl))
        if tok.startswith("*"):
            return bool(re.search(rf"{re.escape(tok)}=", alltpl))
        return bool(
            re.search(
                rf"\{{\{{[^}}]*\b{re.escape(tok)}\b[^}}]*\}}\}}",
                "\n".join(html.values()),
            )
        )
    if k.startswith("cfg:"):
        file, _, dotted = k[4:].partition("#")
        if not dotted or file not in cfgs:
            return False
        return json_has(cfgs[file], dotted.split("."))
    return False


used_keys = sorted(k for k in keys if used(k))
missing = [k for k in used_keys if k not in have]
print(
    f"025 Angular keys: {len(keys)}; used by the service: {len(used_keys)}; in profile: {len(used_keys) - len(missing)}"
)
for k in missing:
    print("  MISSING", k)
