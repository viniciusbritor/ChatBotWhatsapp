"""Strip leftover lines from main.py after the legacy dashboard block."""
import pathlib

p = pathlib.Path("main.py")
text = p.read_text(encoding="utf-8")
start_marker = '<html lang="pt-BR">'
end_marker = '@app.post("/admin/playground")'

start_idx = text.index(start_marker)
end_idx = text.index(end_marker, start_idx)
new_text = text[:start_idx] + text[end_idx:]
p.write_text(new_text, encoding="utf-8")
print("CLEANED", "new_length", len(new_text))
