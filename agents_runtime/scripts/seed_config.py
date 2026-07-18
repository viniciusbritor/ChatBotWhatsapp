"""Seed config/, new agents, and new skills into Firestore (upsert mode)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["GCP_PROJECT"] = "coherence-ominichannel-fs"

from google.cloud import firestore
db = firestore.Client(project="coherence-ominichannel-fs")
datetime_module = __import__("datetime")
BRT = datetime_module.timezone(datetime_module.timedelta(hours=-3))
now = datetime_module.datetime.now(BRT).isoformat()

# === CONFIG/ROUTING ===
routing_rules = [
    {"agent_id": "agent-morality", "priority": 1, "enabled": True, "keywords": ["puta", "merda", "caralho", "fdp", "porra", "buceta", "viado", "bicha", "desgraça", "foder", "fode", "piranha", "vagabunda", "puto", "bosta", "porcaria", "desgraçado", "assedio", "abuso", "estupro", "violencia", "agressao", "ameaça", "ameaca", "chantagem"]},
    {"agent_id": "agent-learning", "priority": 2, "enabled": True, "keywords": ["na verdade", "não é assim", "nao e assim", "errado", "errada"]},
    {"agent_id": "agent-intimacy", "priority": 3, "enabled": True, "keywords": ["me chame de", "pode me chamar de", "meu apelido", "meu nome e", "meu nome é"]},
    {"agent_id": "manager-calendar", "priority": 4, "enabled": True, "keywords": ["agenda", "reuniao", "evento", "compromisso", "lembrete", "calendario", "disponivel", "semana que vem", "proxima semana"]},
    {"agent_id": "manager-drive", "priority": 5, "enabled": True, "keywords": ["drive", "documento", "arquivo", "pasta", "upload", "omnichannel", "baixar", "encontrar arquivo"]},
    {"agent_id": "manager-email", "priority": 6, "enabled": True, "keywords": ["email", "e-mail", "caixa de entrada", "gmail", "ler email", "enviar email", "ultimos emails"]},
    {"agent_id": "manager-web", "priority": 7, "enabled": True, "keywords": ["pesquisar", "buscar na internet", "busque na internet", "procure na web", "pesquise na web", "noticia atual", "noticias atuais"]},
    {"agent_id": "agent-youtube", "priority": 8, "enabled": True, "keywords": ["youtube", "vídeo", "video", "tutorial", "aula"]},
    {"agent_id": "agent-locomocao", "priority": 9, "enabled": True, "keywords": ["uber", "rota", "tempo", "distância", "distancia", "chegar", "trânsito", "transito", "endereço", "endereco", "onde fica", "perto de", "restaurante", "farmácia", "farmacia", "posto"]},
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
    "owner_phones": ["+5511966830020"],
    "updated_at": now,
}, merge=True)
print("config/proactivity seeded")

# === NOVOS AGENTES ===
new_agents = [
    {"id": "agent-proatividade", "name": "Proatividade", "role": "specialist", "parent_id": "jennifier",
     "model": "deepseek-v4-flash", "thinking": "disabled", "enabled": True,
     "skills": ["skill-proatividade"], "tools": ["calendar.list_events"],
     "system_prompt": "Voce antecipa necessidades dos usuarios. Com base no calendario e contexto, sugira lembretes, follow-ups e dicas uteis. Seja proativa mas nao invasiva. Respeite os limites de frequencia configurados.",
     "instances": ["jennifer"], "system_prompt_version": 1, "updated_at": now},
    {"id": "agent-privacy-guard", "name": "Privacy Guard", "role": "specialist", "parent_id": "jennifier",
     "model": "deepseek-v4-flash", "thinking": "disabled", "enabled": True,
     "skills": ["skill-privacy-group"], "tools": [],
     "system_prompt": "Voce gerencia privacidade em grupos. Quando alguem pede dados pessoais no grupo, confirme com o usuario pelo NOME (nao email) se ele quer compartilhar no grupo ou receber no privado. Aguarde a resposta antes de prosseguir.",
     "instances": ["jennifer"], "system_prompt_version": 1, "updated_at": now},
    {"id": "agent-locomocao", "name": "Locomoção", "role": "specialist", "parent_id": "jennifier",
     "model": "deepseek-v4-flash", "thinking": "disabled", "enabled": True,
     "skills": ["skill-locomocao"], "tools": ["locomotion.calc_route", "locomotion.geocode", "locomotion.search_places"],
     "system_prompt": "Voce calcula rotas, estima precos de Uber/99 e busca lugares proximos. SEMPRE confirme o endereco com o usuario antes de calcular. Precisa de origem e destino para calcular rota.",
     "instances": ["jennifer"], "system_prompt_version": 1, "updated_at": now},
    {"id": "agent-youtube", "name": "YouTube", "role": "specialist", "parent_id": "jennifier",
     "model": "deepseek-v4-flash", "thinking": "disabled", "enabled": True,
     "skills": [], "tools": ["youtube.search_videos"],
     "system_prompt": "Voce busca videos no YouTube e retorna titulo, canal e link. Maximo 3 resultados por busca.",
     "instances": ["jennifer"], "system_prompt_version": 1, "updated_at": now},
    {"id": "agent-rag", "name": "Conhecimento", "role": "specialist", "parent_id": "jennifier",
     "model": "deepseek-v4-flash", "thinking": "disabled", "enabled": True,
     "skills": [], "tools": ["rag.search_knowledge"],
     "system_prompt": "Voce busca informacoes na base de conhecimento compartilhada (leis, editais, livros). Use search_knowledge para consultas semanticas. Responda sempre em portugues brasileiro.",
     "instances": ["jennifer"], "system_prompt_version": 1, "updated_at": now},
    {"id": "group-resolver", "name": "Group Resolver", "role": "specialist", "parent_id": "manager-drive",
     "model": "deepseek-v4-flash", "thinking": "disabled", "enabled": True,
     "skills": [], "tools": ["group.get_info", "drive.search_files"],
     "system_prompt": "Voce resolve qual grupo/pasta do Drive corresponde a um grupo do WhatsApp. Dado um group_jid, busque no Firestore qual pasta usar.",
     "instances": ["jennifer"], "system_prompt_version": 1, "updated_at": now},
]

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

print("\n✅ Fase 0 concluida!")
