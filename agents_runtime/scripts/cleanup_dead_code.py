"""Remove dead functions from orchestrator.py, keeping everything else intact."""
import re, sys

DEAD = {
    "_detect_intent", "_matches_keyword", "_get_routing_rules",
    "_build_skills_section", "_get_orchestrator", "_select_orchestrator_agent",
    "_agent_has_tool", "_iter_agents", "_resolve_agent_for_intent",
    "_resolve_agents_for_intents", "_is_personal_intent",
    "_execute_single_specialist", "_execute_multi_specialists_parallel",
    "_run_guard_graph", "_intent_to_capability", "_is_read_query",
    "_prefetch_tone_guide",
    # helpers for execute_multi_specialists_parallel
    "_run_one", "_run_one_safe",
    # constants only used by dead functions
    "_AGENT_INTENT_FLAGS", "PERSONAL_INTENTS",
    "_FILENAME_EXT", "_has_filename_hint", "_import_rag_helpers",
}

FILE = "orchestrator.py"
with open(FILE, "r", encoding="utf-8", errors="replace") as f:
    content = f.read()

lines = content.split("\n")
output = []
skipping = False
skip_depth = 0

i = 0
while i < len(lines):
    line = lines[i]
    stripped = line.strip()

    # Detect top-level def/constant (at col 0)
    if not line.startswith(" ") and not line.startswith("\t"):
        m = re.match(r"^(async\s+)?def\s+(\w+)\(", stripped)
        cm = re.match(r"^(\w[\w_]*)\s*[:=]", stripped)

        if m:
            name = m.group(2)
            if name in DEAD:
                skipping = True
                skip_depth = 0
                i += 1
                continue
            else:
                skipping = False

        elif cm and cm.group(1) in DEAD:
            skipping = True
            skip_depth = 0
            i += 1
            continue

        elif stripped == "" or stripped.startswith("#") or stripped.startswith("@"):
            if skipping:
                i += 1
                continue

    if skipping:
        # Track indentation to know when function body ends
        indent = len(line) - len(line.lstrip())
        if indent <= skip_depth and stripped != "":
            skipping = False
            output.append(line)
            i += 1
            continue
        i += 1
        continue

    output.append(line)
    i += 1

with open(FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output))

print(f"Removed {len(DEAD)} dead functions/constants from {FILE}")
