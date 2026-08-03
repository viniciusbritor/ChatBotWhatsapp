"""Comment out dead code using AST — safe, preserves file syntax."""
import ast

DEAD_NAMES = {
    "_detect_intent", "_matches_keyword", "_get_routing_rules",
    "_build_skills_section", "_get_orchestrator", "_select_orchestrator_agent",
    "_agent_has_tool", "_iter_agents", "_resolve_agent_for_intent",
    "_resolve_agents_for_intents", "_is_personal_intent",
    "_execute_single_specialist", "_execute_multi_specialists_parallel",
    "_run_guard_graph", "_intent_to_capability", "_is_read_query",
    "_prefetch_tone_guide", "_run_one", "_run_one_safe",
    "_AGENT_INTENT_FLAGS", "PERSONAL_INTENTS",
    "_FILENAME_EXT", "_has_filename_hint", "_import_rag_helpers",
}

FILE = "orchestrator.py"
with open(FILE, "r", encoding="utf-8", errors="replace") as f:
    source = f.read()

tree = ast.parse(source)
lines = source.split("\n")

ranges_to_comment = []

class DeadFinder(ast.NodeVisitor):
    def visit_FunctionDef(self, node):
        if node.name in DEAD_NAMES:
            ranges_to_comment.append((node.lineno, node.end_lineno))
        self.generic_visit(node)
    def visit_AsyncFunctionDef(self, node):
        if node.name in DEAD_NAMES:
            ranges_to_comment.append((node.lineno, node.end_lineno))
        self.generic_visit(node)
    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in DEAD_NAMES:
                ranges_to_comment.append((node.lineno, node.end_lineno))
        self.generic_visit(node)
    def visit_AnnAssign(self, node):
        if isinstance(node.target, ast.Name) and node.target.id in DEAD_NAMES:
            ranges_to_comment.append((node.lineno, node.end_lineno, True))
        self.generic_visit(node)

DeadFinder().visit(tree)

# Comment out dead lines (preserve file structure)
for start, end, *_ in sorted(ranges_to_comment, reverse=True):
    for i in range(start - 1, end):
        if not lines[i].lstrip().startswith("#"):
            lines[i] = "# " + lines[i]

with open(FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Commented out {len(ranges_to_comment)} dead blocks")
