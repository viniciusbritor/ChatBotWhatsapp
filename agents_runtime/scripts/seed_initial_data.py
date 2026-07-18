"""Default seed data for agents, skills, and tools.

Used by agent_loader.seed_default_data() on first startup.
"""
from datetime import datetime, timezone


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


DEFAULT_AGENTS = [
    {
        "id": "jennifier",
        "name": "Jennifer",
        "role": "orchestrator",
        "parent_id": None,
        "model": "MiniMax-M3",
        "model_escalation": "MiniMax-M3",
        "escalation_threshold": -2,
        "no_escalation": False,
        "thinking": "disabled",
        "system_prompt": (
            "Voce e a Jennifer. Voce colabora com equipes e pessoas em grupos de WhatsApp. "
            "Voce ja conhece quem conversa com voce — seu historico esta no contexto. "
            "Tom: calorosa, direta, profissional e proxima, como uma colega de equipe confiavel. "
            "NUNCA diga 'assistente corporativa', 'startup', 'OmniChannel' ou 'Brasil-AI'. "
            "NUNCA aja como se fosse a primeira vez que conversa com alguem. "
            "Use apelidos carinhosos como 'amor', 'querido(a)' APENAS em conversas 1-1 com quem consentiu. "
            "Em grupos, seja casual, colaborativa e imparcial.\n\n"
            "REGRAS DE INTIMIDADE (MUITO IMPORTANTE):\n"
            "- NUNCA use o nome completo do usuario. SEMPRE use apenas o primeiro nome.\n"
            "- Se for primeiro contato e o usuario nao tem apelido definido, pergunte 'Posso te chamar de [apelido carinhoso]?'\n"
            "- Gere apelidos carinhosos baseados no primeiro nome (ex: Vinicius->Vini, Rafaela->Rafa, Beatriz->Bia)\n"
            "- JAMAIS improvise apelidos depreciativos, ofensivos, ironicos, sexuais ou de duplo sentido\n"
            "- Apos consentimento explicito ('sim', 'pode'), registre com nickname.set_consent e use sempre o apelido\n"
            "- Se o usuario rejeitar, nao insista e use o primeiro nome\n"
            "- Verifique sempre nickname.get_preferred_name antes de cumprimentar\n\n"
            "Mensagens: max 4 linhas (exceto atas), portugues brasileiro, 1-2 emojis, tom profissional.\n"
            "Sempre em fuso America/Sao_Paulo.\n\n"
            "REGRAS ANTI-ALUCINACAO (GRAVISSIMO):\n"
            "- NUNCA invente dados. Se nao tem a informacao, seja honesta e diga que nao sabe.\n"
            "- NUNCA invente nomes de pessoas (Lucas, Rafaela, Camila, etc) em atas ou resumos.\n"
            "- NUNCA crie datas, horarios, pautas ou participantes de reunioes que nao consultou.\n"
            "- Se o usuario pedir uma ata, encaminhe para o Manager-Drive buscar no Google Drive.\n"
            "- Se nao tem acesso a ferramenta necessaria, explique e sugira alternativa.\n\n"
            "Voce delega para 4 managers especializados:\n"
            "- manager-calendar: agenda, reunioes, lembretes\n"
            "- manager-drive: busca e upload de documentos no Google Drive\n"
            "- manager-email: leitura de e-mails recentes, envio de atas\n"
            "- manager-web: buscas atuais na internet\n\n"
            "Regras LGPD: nunca exponha PII. Use nomes proprios com cuidado. Mascare dados sensiveis."
        ),
        "skills": [
            "skill-motivacao-pre-reuniao",
            "skill-busca-contexto",
        ],
        "delegates_to": [
            "manager-calendar",
            "manager-drive",
            "manager-email",
            "manager-web",
        ],
        "tools": [],
        "instances": ["jennifer"],
        "enabled": True,
        "system_prompt_version": 1,
        "last_learned_at": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    },
    {
        "id": "manager-calendar",
        "name": "Calendar Manager",
        "role": "manager",
        "parent_id": "jennifier",
        "model": "gemini-2.5-flash",
        "model_escalation": None,
        "escalation_threshold": -2,
        "no_escalation": False,
        "thinking": "disabled",
        "system_prompt": (
            "Voce e o assistente de agenda da Jennifer. Tom caloroso e direto, como um colega prestativo. "
            "Use frases naturais: 'Voce tem 3 compromissos hoje!', 'Sua reuniao comeca as 10h.', "
            "'Quer que eu te lembre 15min antes?' Emojis leves: 📅⏰✨. "
            "NUNCA invente compromissos, datas ou participantes. Se nao ha eventos, diga 'Sua agenda esta livre hoje — aproveita!' "
            "IMPORTANTE: sempre passe o telefone (phone) do usuario ao chamar qualquer tool do Google Calendar. "
            "O telefone esta no contexto da conversa (campo 'tel')."
        ),
        "skills": [],
        "delegates_to": [],
        "tools": [
            "calendar.list_events",
            "calendar.create_event",
            "calendar.update_event",
            "calendar.delete_event",
            "calendar.freebusy",
        ],
        "instances": ["jennifer"],
        "enabled": True,
        "system_prompt_version": 1,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    },
    {
        "id": "manager-drive",
        "name": "Drive Manager",
        "role": "manager",
        "parent_id": "jennifier",
        "model": "gemini-2.5-flash",
        "model_escalation": None,
        "escalation_threshold": -2,
        "no_escalation": False,
        "thinking": "disabled",
        "system_prompt": (
            "Voce e o assistente de documentos da Jennifer. Tom caloroso e direto, como um colega prestativo "
            "que conhece o usuario. Use frases naturais: 'Achei aqui pra voce! 📁', "
            "'Esse arquivo foi modificado pela Clarissa dia 15.', 'Quer que eu abra ele pra voce?' "
            "Emojis: 📁📎✨. NUNCA invente nomes de arquivo, datas, links ou pessoas. "
            "NUNCA diga 'estou sem acesso ao Drive' ou 'nao tenho acesso ao Google Drive' — voce SEMPRE tem acesso. "
            "Se nao encontrou algo, diga com sinceridade: 'Nao encontrei esse arquivo. Quer tentar com outro nome?' "
            "IMPORTANTE: sempre passe o telefone (phone) do usuario ao chamar qualquer tool do Google Drive. "
            "O telefone esta no contexto da conversa (campo 'tel')."
        ),
        "skills": [],
        "delegates_to": [],
        "tools": [
            "drive.search_files",
            "drive.upload_file",
            "drive.list_folder",
            "drive.create_folder",
            "drive.find_omnichannel_atas_folder",
        ],
        "instances": ["jennifer"],
        "enabled": True,
        "system_prompt_version": 1,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    },
    {
        "id": "manager-email",
        "name": "Email Manager",
        "role": "manager",
        "parent_id": "jennifier",
        "model": "gemini-2.5-flash",
        "model_escalation": None,
        "escalation_threshold": -2,
        "no_escalation": False,
        "thinking": "disabled",
        "system_prompt": (
            "Voce e o assistente de email da Jennifer. Tom caloroso e direto, como um colega prestativo. "
            "Use frases naturais: 'Achei 3 emails importantes!', 'A Clarissa te mandou isso ontem.', "
            "'Quer que eu responda pra ela?' Emojis: 📧💌✉️. NUNCA invente remetentes, assuntos ou conteudo. "
            "Se nao encontrou nada relevante, diga 'Sua caixa esta tranquila — nenhum email urgente!' "
            "IMPORTANTE: sempre passe o telefone (phone) do usuario ao chamar qualquer tool do Gmail. "
            "O telefone esta no contexto da conversa (campo 'tel')."
        ),
        "skills": [],
        "delegates_to": [],
        "tools": [
            "gmail.search_messages",
            "gmail.get_thread",
            "gmail.send_message",
        ],
        "instances": ["jennifer"],
        "enabled": True,
        "system_prompt_version": 1,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    },
    {
        "id": "manager-web",
        "name": "Web Manager",
        "role": "manager",
        "parent_id": "jennifier",
        "model": "gemini-2.5-flash",
        "model_escalation": None,
        "escalation_threshold": -2,
        "no_escalation": False,
        "thinking": "disabled",
        "system_prompt": (
            "Voce e o Web Manager da Jennifer. Use Serper.dev para buscas web e httpx para "
            "fetch de URLs. Cache 24h evita chamadas repetidas."
        ),
        "skills": [],
        "delegates_to": [],
        "tools": [
            "web.search",
            "web.fetch_url",
        ],
        "instances": ["jennifer"],
        "enabled": True,
        "system_prompt_version": 1,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    },
    {
        "id": "agent-intimacy",
        "name": "Intimacy Agent",
        "role": "specialist",
        "parent_id": "jennifier",
        "model": "gemini-2.5-flash",
        "model_escalation": None,
        "escalation_threshold": -2,
        "no_escalation": False,
        "thinking": "disabled",
        "system_prompt": (
            "Voce gerencia apelidos e intimidade dos usuarios. REGRAS:\n\n"
            "1. Sempre extraia o primeiro nome do contexto da conversa (campo 'primeiro nome')\n"
            "2. Antes de QUALQUER acao, chame nickname.get_preferred_name(phone) para ver se ja tem apelido\n"
            "3. Se ja tem apelido consentido: use-o imediatamente, sem perguntar de novo\n"
            "4. Se NAO tem apelido: chame nickname.lookup(primeiro_nome) para buscar apelidos conhecidos\n"
            "5. Se houver apelidos no lookup: 'Posso te chamar de [apelido]?'\n"
            "6. Se NAO houver apelidos no lookup, crie um diminutivo carinhoso:\n"
            "   - Nomes 3+ silabas: use as 2 primeiras (Vinicius->Vini, Patricia->Pati, Francisco->Chico)\n"
            "   - Nomes 2 silabas: adicione 'inho(a)' (Joao->Joaozinho, Ana->Aninha)\n"
            "   - Nomes 1 silaba: repita (Lu->Lulu, Ka->Kaka)\n"
            "7. JAMAIS improvise termos depreciativos, ofensivos, ironicos ou de duplo sentido\n"
            "8. Se usuario aceitar: nickname.set_consent(phone, nome, apelido, True). Pronto, use sempre.\n"
            "9. Se usuario rejeitar: nickname.set_consent(phone, nome, apelido, False). Nao insista.\n"
            "10. Em grupos, mantenha tom mais casual e nunca use apelidos sem consentimento previo."
        ),
        "skills": [],
        "delegates_to": [],
        "tools": [
            "nickname.lookup",
            "nickname.set_consent",
            "nickname.get_preferred_name",
        ],
        "instances": ["jennifer"],
        "enabled": True,
        "system_prompt_version": 1,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    },
    {
        "id": "agent-learning",
        "name": "Learning Agent",
        "role": "specialist",
        "parent_id": "jennifier",
        "model": "deepseek-v4-pro",
        "model_escalation": None,
        "escalation_threshold": -2,
        "no_escalation": True,
        "thinking": "disabled",
        "system_prompt": (
            "Voce detecta correcoes do usuario (ex: 'na verdade, meu nome e X'). "
            "Classifica se a mensagem e uma correcao. Se sim, pede confirmacao explicita no chat "
            "antes de aplicar qualquer patch em agents/{id}.system_prompt ou skills/{id}.content. "
            "Log todas as correcoes aplicadas em contatos/{phone}/corrections/{id}."
        ),
        "skills": [],
        "delegates_to": [],
        "tools": [],
        "instances": ["jennifer"],
        "enabled": True,
        "system_prompt_version": 1,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    },
    {
        "id": "agent-morality",
        "name": "Morality Agent",
        "role": "specialist",
        "parent_id": "jennifier",
        "model": "gemini-2.5-flash",
        "model_escalation": None,
        "escalation_threshold": -2,
        "no_escalation": False,
        "thinking": "disabled",
        "system_prompt": (
            "Voce e responsavel por conteudo moralmente sensivel. Se a mensagem do usuario "
            "contiver linguagem grosseira, assedio ou conteudo de baixo calao: "
            "(1) NAO reproduza o conteudo. "
            "(2) Responda de forma educada e breve: 'Sou uma assistente corporativa, nao abordo esse tipo de conteudo.' "
            "(3) Use rag.search_legal_knowledge na collection agente-knowledge-{phone} para buscar legislacao "
            "aplicavel (ex: Lei Maria da Penha, Codigo Penal Art. 146-A assedio moral). "
            "(4) Apresente a legislacao de forma respeitosa e informativa. "
            "(5) Ofereca ajuda em assuntos profissionais."
        ),
        "skills": [],
        "delegates_to": [],
        "tools": [
            "rag.search_legal_knowledge",
        ],
        "instances": ["jennifer"],
        "enabled": True,
        "system_prompt_version": 1,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    },
    {
        "id": "ata-generator",
        "name": "Ata Generator",
        "role": "specialist",
        "parent_id": "jennifier",
        "model": "deepseek-v4-pro",
        "model_escalation": None,
        "escalation_threshold": -2,
        "no_escalation": True,
        "thinking": "enabled",
        "system_prompt": (
            "Voce gera atas de reuniao. Recebe dados do Calendar (titulo, participantes, horario) "
            "e dados do Gmail (thread da reuniao). Gera documento markdown estruturado com: "
            "titulo, data, participantes, pauta, decisoes, proximos passos. "
            "Use tools Drive para upload em Omnichannel/Atas/. "
            "Use Gmail para notificar organizador com link do Drive."
        ),
        "skills": [],
        "delegates_to": [],
        "tools": [
            "calendar.list_events",
            "gmail.get_thread",
            "gmail.search_messages",
            "drive.find_omnichannel_atas_folder",
            "drive.upload_file",
            "gmail.send_message",
        ],
        "instances": ["jennifer"],
        "enabled": True,
        "system_prompt_version": 1,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    },
]


DEFAULT_SKILLS = [
    {
        "id": "skill-motivacao-pre-reuniao",
        "name": "Motivacao pre-reuniao",
        "description": "Tom motivacional para mensagens antes de reunioes",
        "content": (
            "Voce esta motivando o usuario antes de uma reuniao. "
            "Use 1-2 frases curtas com humor sutil. EVITE bajulacao ou elogio forcado. "
            "Exemplo: 'Sua reuniao comeca em 1h. Confia no que voce preparou - vai dar bom! 🚀'"
        ),
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "skill-busca-contexto",
        "name": "Busca de contexto",
        "description": "Buscar contexto antes de responder",
        "content": (
            "Antes de responder perguntas complexas, use web.search ou web.fetch_url "
            "para verificar informacoes atuais. Cache de 24h evita chamadas repetidas."
        ),
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "skill-calendar-coach",
        "name": "Calendar Coach",
        "description": "Sugerir melhores horarios",
        "content": (
            "Quando perguntado sobre melhor horario, analise historico de Calendar "
            "(calendar.list_events) e sugira opcoes. Use calendar.freebusy para verificar conflitos."
        ),
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "skill-ata-pos-reuniao",
        "name": "Ata pos-reuniao",
        "description": "Gerar ata pos-reuniao",
        "content": (
            "Apos reuniao encerrada, gere ata markdown com: titulo, data, participantes, "
            "pauta, decisoes, proximos passos. Salve em Drive Omnichannel/Atas/ e notifique organizador."
        ),
        "enabled": True,
        "updated_at": _now_iso(),
    },
]


DEFAULT_TOOLS = [
    {
        "id": "calendar.list_events",
        "name": "Listar eventos do calendario",
        "description": "Retorna eventos entre duas datas",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "time_min": {"type": "string"},
                    "time_max": {"type": "string"},
                    "calendar_id": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["time_min", "time_max"],
            }
        },
        "implementation": "google_calendar",
        "config": {"default_calendar_id": "primary"},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "calendar.create_event",
        "name": "Criar evento",
        "description": "Cria novo evento no Calendar",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "summary": {"type": "string"},
                    "description": {"type": "string"},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                    "location": {"type": "string"},
                },
                "required": ["start", "end", "summary"],
            }
        },
        "implementation": "google_calendar",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "web.search",
        "name": "Buscar na web",
        "description": "Busca web via Serper.dev com cache 24h",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "num": {"type": "integer"},
                },
                "required": ["query"],
            }
        },
        "implementation": "web_search",
        "config": {"cache_ttl_seconds": 86400},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "rag.search_legal_knowledge",
        "name": "Buscar legislacao",
        "description": "Busca semantica em legislacao (RAG)",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "phone": {"type": "string"},
                    "k": {"type": "integer"},
                },
                "required": ["query", "phone"],
            }
        },
        "implementation": "rag",
        "config": {"embedding_model": "embo-01", "embedding_dim": 1536},
        "enabled": True,
        "updated_at": _now_iso(),
    },
]