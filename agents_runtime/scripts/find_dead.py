import re, subprocess, os

os.chdir(r"C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp\agents_runtime")

with open("orchestrator.py", "r") as f:
    content = f.read()

defs = set()
for m in re.finditer(r"^(async\s+)?def\s+(\w+)\s*\(", content, re.MULTILINE):
    defs.add(m.group(2))

imports = set()
import glob
for fp in glob.glob("**/*.py", recursive=True):
    if fp.startswith("orchestrator.py") or "tests" in fp:
        continue
    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "orchestrator" in line and "import" in line:
                for m in re.finditer(r"import\s+(\w+)", line):
                    imports.add(m.group(1))
                for m in re.finditer(r"from orchestrator import\s+(.*)", line):
                    for n in m.group(1).split(","):
                        imports.add(n.strip().split(" as ")[0].strip())

# Also check internal references within orchestrator.py itself
internal = set()
for m in re.finditer(r"^\s*(_[\w]+)\s*\(|^\s*if\s+(_[\w]+)\(", content, re.MULTILINE):
    internal.add(m.group(1))
for m in re.finditer(r"(?<!def\s)(?<!\.)(_[\w]+)\s*\(|=\s*(_[\w]+)|await\s+(_[\w]+)\(", content):
    for g in m.groups():
        if g and g.startswith("_") and g in defs:
            internal.add(g)

dead = defs - imports - internal
with open("scripts/dead_funcs.txt", "w") as f:
    for d in sorted(dead):
        f.write(d + "\n")
        print(d)
