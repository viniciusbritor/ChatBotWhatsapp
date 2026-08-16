"""Seed config/, new agents, and new skills into Firestore (upsert mode)."""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["GCP_PROJECT"] = "coherence-ominichannel-fs"

from google.cloud import firestore
db = firestore.Client(project="coherence-ominichannel-fs")
from core.timezone import now_brt
now = now_brt().isoformat()

# === CONFIG/ROUTING ===
routing_rules = [
    {"agent_id": "agent-morality", "priority": 1, "enabled": True, "keywords": ["puta", "merda", "caralho", "fdp", "porra", "buceta", "viado", "bicha", "desgraça", "foder", "fode", "piranha", "vagabunda", "puto", "bosta", "porcaria", "desgraçado", "assedio", "abuso", "estupro", "violencia", "agressao", "ameaça", "ameaca", "chantagem"]},
    {"agent_id": "agent-learning", "priority": 2, "enabled": True, "keywords": ["na verdade", "não é assim", "nao e assim", "errado", "errada"]},
    {"agent_id": "agent-intimacy", "priority": 3, "enabled": True, "keywords": ["me chame de", "pode me chamar de", "meu apelido", "meu nome e", "meu nome é"]},
    {"agent_id": "manager-calendar", "priority": 4, "enabled": True, "keywords": ["agenda", "reuniao", "evento", "compromisso", "lembrete", "calendario", "disponivel", "semana que vem", "proxima semana"]},
    {"agent_id": "manager-drive", "priority": 5, "enabled": True, "keywords": ["drive", "documento", "arquivo", "pasta", "upload", "omnichannel", "baixar", "encontrar arquivo"]},
    {"agent_id": "manager-email", "priority": 6, "enabled": True, "keywords": ["email", "e-mail", "caixa de entrada", "gmail", "ler email", "enviar email", "ultimos emails"]},
]
db.collection("config").document("routing").set({"rules": routing_rules, "updated_at": now}, merge=True)
print("config/routing seeded:", len(routing_rules), "rules")

# === CONFIG/PRIVACY ===
db.collection("config").document("privacy").set({
    "group_policy": "ask_confirmation",
    "confirmation_timeout_sec": 60,
    "fallback": "dm",
    "templates": {
        "blocked_group": "Oi {name}! 🔒 Dados pessoais (agenda, email, documentos) não podem ser compartilhados no grupo. Me chama no privado!",
        "confirm_group": "{name}, você quer que eu mostre essa informação aqui no grupo ou prefere que eu te responda no privado? 🔒",
        "shared_in_group": "Pessoal, a {name} pediu pra compartilhar: {data}",
    },
    "updated_at": now,
}, merge=True)
print("config/privacy seeded")

# === CONFIG/PROACTIVITY ===
db.collection("config").document("proactivity").set({
    "max_per_contact_day": 2,
    "max_global_day": 5,
    "quiet_hours_start": 21,
    "quiet_hours_end": 9,
    "min_relevance": 0.75,
    "triggers": ["calendar_1h", "followup_2h", "birthday"],
    "owner_phones": ["+5511967389901"],
    "updated_at": now,
}, merge=True)
print("config/proactivity seeded")

# === NOVOS AGENTES ===
new_agents = []

for agent in new_agents:
    db.collection("agents").document(agent["id"]).set(agent, merge=True)
print(f"Agents seeded: {len(new_agents)}")

# === NOVAS SKILLS ===
new_skills = [
    {"id": "skill-proatividade", "name": "Proatividade", "enabled": True, "content": (
        "# Regras de Proatividade\n\n"
        "## Quando notificar\n"
        "- 1h antes de reuniao: lembrete com titulo, horario, participantes\n"
        "- Follow-up 2h depois: 'Como foi a reuniao? Quer que eu gere uma ata?'\n"
        "- Topicos 2x/semana (terca e sexta): sugestao de tema relevante\n"
        "- Aniversario: mensagem de parabens\n\n"
        "## Limites\n"
        "- Max 2 mensagens proativas/dia por contato\n"
        "- Max 5 mensagens proativas/dia global\n"
        "- Quiet hours: 21h-9h BRT\n"
        "- Cooldown 12h entre mensagens para o mesmo contato\n"
        "- Relevance minima: 0.75\n\n"
        "## Templates PROIBIDOS\n"
        "- 'Oi, tudo bem?' sem contexto\n"
        "- 'Senti sua falta'\n"
        "- Elogios forcados\n"
        "- Memes/piadas aleatorias\n"
        "- 'Bom dia!' sem motivo\n"
    ), "updated_at": now},
    {"id": "skill-privacy-group", "name": "Privacidade em Grupo", "enabled": True, "content": (
        "# Regras de Privacidade em Grupos\n\n"
        "## Politica\n"
        "- Dados pessoais (agenda, email, documentos) NAO sao compartilhados automaticamente em grupos\n"
        "- Sempre pergunte confirmacao pelo NOME da pessoa, nunca pelo email\n"
        "- Timeout: 60 segundos para resposta\n"
        "- Fallback: se nao responder, enviar DM\n\n"
        "## Templates\n"
        "- Confirmacao: '{name}, quer que eu mostre no grupo ou prefere no privado? 🔒'\n"
        "- Compartilhado: 'A {name} pediu pra compartilhar: {data}'\n"
        "- Bloqueado: 'Oi {name}! Dados pessoais no grupo nao rolam. Me chama no privado! 🔒'\n"
    ), "updated_at": now},
    {"id": "skill-locomocao", "name": "Locomoção", "enabled": True, "content": (
        "# Locomoção — Como usar as tools\n\n"
        "## calc_route\n"
        "- Calcular rota entre dois pontos (origem, destino)\n"
        "- Retorna: distancia (km), duracao (min), preco Uber e 99 (estimativa)\n"
        "- SEMPRE confirme o endereco antes de calcular\n"
        "- Se o usuario nao informar origem ou destino, pergunte\n\n"
        "## geocode\n"
        "- Converte endereco em coordenadas ou vice-versa\n"
        "- Use quando o usuario perguntar 'onde fica X?'\n\n"
        "## search_places\n"
        "- Busca lugares proximos (restaurantes, farmacias, postos)\n"
        "- Passe tipo e localizacao\n\n"
        "## Precos (estimativa)\n"
        "- Uber: R$ 5.50 (base) + R$ 2.80/km + R$ 0.35/min\n"
        "- 99: ~85% do valor Uber\n"
        "- Tarifa minima: R$ 8.00\n"
    ), "updated_at": now},
]

for skill in new_skills:
    db.collection("skills").document(skill["id"]).set(skill, merge=True)
print(f"Skills seeded: {len(new_skills)}")

print("\n[OK] Fase 0 concluida")
