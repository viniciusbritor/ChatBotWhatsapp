{"
            "responda 'request_oauth' e inclua o link /oauth/google?phone=...\n"
            "3. Se os scopes do token nao cobrirem a capability, responda "
            "'request_oauth' com o link.\n"
            "4. Caso contrario, responda 'allow'.\n"
            "Sempre devolva JSON estruturado, sem texto extra."
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
        "id": "agent-intimacy",
        "name": "Intimacy Agent",
        "role": "specialist",
        "parent_id": "jennifier",
        "model": "deepseek-v4-flash",
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
        "model": "deepseek-v4-flash",
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
        "tools": ["correction.detect", "correction.log", "correction.apply_patch"],
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
        "model": "deepseek-v4-flash",
        "model_escalation": None,
        "escalation_threshold": -2,
        "no_escalation": False,
        "thinking": "disabled",
        "system_prompt": (
            "Voce e responsavel por conteudo moralmente sensivel. Se a mensagem do usuario "
            "contiver linguagem grosseira, assedio ou conteudo de baixo calao: "
            "(1) NAO reproduza o conteudo. "
            "(2) Responda de forma educada e breve: 'Sou uma assistente corporativa, nao abordo esse tipo de conteudo.' "
            "(3) Use rag.search_legal_knowledge na collection knowledge-database (scope private) para buscar legislacao "
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
        "config": {"embedding_model": "text-embedding-3-small", "embedding_dim": 1536},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "locomotion.calc_route",
        "name": "Calcular rota",
        "description": "Calcula rota entre dois enderecos. Retorna distancia, duracao, preco estimado Uber e 99.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "origem": {"type": "string"},
                    "destino": {"type": "string"},
                },
                "required": ["origem", "destino"],
            }
        },
        "implementation": "locomotion",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "locomotion.geocode",
        "name": "Geocodificar endereco",
        "description": "Converte endereco em coordenadas e endereco formatado.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "endereco": {"type": "string"},
                },
                "required": ["endereco"],
            }
        },
        "implementation": "locomotion",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "locomotion.search_places",
        "name": "Buscar lugares proximos",
        "description": "Busca lugares proximos (restaurantes, farmacias, postos) por tipo.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "local": {"type": "string"},
                    "tipo": {"type": "string"},
                },
                "required": ["local"],
            }
        },
        "implementation": "locomotion",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "locomotion.find_place",
        "name": "Buscar estabelecimento por nome",
        "description": "Busca um estabelecimento pelo NOME (ex: 'Emporio Alto Pinheiro'). Retorna nome, endereco, avaliacao e se esta aberto.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "localizacao": {"type": "string"},
                },
                "required": ["query"],
            }
        },
        "implementation": "locomotion",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "weather.current",
        "name": "Clima atual",
        "description": "Condicao atual do tempo de uma cidade: temperatura, sensacao, umidade, vento e condicao.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "cidade": {"type": "string"},
                },
                "required": ["cidade"],
            }
        },
        "implementation": "weather",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "weather.forecast",
        "name": "Previsao do tempo",
        "description": "Previsao do tempo para os proximos dias (1-7) de uma cidade.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "cidade": {"type": "string"},
                    "dias": {"type": "integer"},
                },
                "required": ["cidade"],
            }
        },
        "implementation": "weather",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "youtube.search_videos",
        "name": "Buscar videos no YouTube",
        "description": "Busca videos no YouTube e retorna titulo, canal e link.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
            }
        },
        "implementation": "youtube",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "translate.text",
        "name": "Traduzir texto",
        "description": "Traduz um texto para outro idioma (default pt).",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "target_lang": {"type": "string"},
                    "source_lang": {"type": "string"},
                },
                "required": ["text"],
            }
        },
        "implementation": "translate",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "translate.detect",
        "name": "Detectar idioma",
        "description": "Detecta o idioma de um texto.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            }
        },
        "implementation": "translate",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "vision.ocr",
        "name": "OCR imagem",
        "description": "Extrai texto de uma imagem via OCR.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "image": {"type": "string"},
                },
                "required": ["image"],
            }
        },
        "implementation": "vision",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "vision.detect_labels",
        "name": "Identificar objetos em imagem",
        "description": "Identifica objetos e categorias em uma imagem.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "image": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["image"],
            }
        },
        "implementation": "vision",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "tasks.list",
        "name": "Listar tarefas",
        "description": "Lista as tarefas do usuario no Google Tasks.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["phone"],
            }
        },
        "implementation": "google_tasks",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "tasks.create",
        "name": "Criar tarefa",
        "description": "Cria uma nova tarefa no Google Tasks.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "title": {"type": "string"},
                    "notes": {"type": "string"},
                    "due": {"type": "string"},
                },
                "required": ["phone", "title"],
            }
        },
        "implementation": "google_tasks",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "tasks.update",
        "name": "Atualizar tarefa",
        "description": "Atualiza uma tarefa (marca concluida ou renomeia).",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "task_id": {"type": "string"},
                    "completed": {"type": "boolean"},
                    "title": {"type": "string"},
                },
                "required": ["phone", "task_id"],
            }
        },
        "implementation": "google_tasks",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "people.search",
        "name": "Buscar contatos",
        "description": "Busca contatos do usuario no Google.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "query": {"type": "string"},
                    "page_size": {"type": "integer"},
                },
                "required": ["phone", "query"],
            }
        },
        "implementation": "google_people",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "people.get_profile",
        "name": "Perfil do usuario",
        "description": "Retorna o perfil do proprio usuario autenticado.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                },
                "required": ["phone"],
            }
        },
        "implementation": "google_people",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
                "required": ["phone"],
            }
        },
    },
                "required": ["phone", "media_id"],
            }
        },
    },
    {
        "id": "googlesheets.read_cells",
        "name": "Ler celulas planilha",
        "description": "Le celulas de uma planilha Google Sheets.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range_": {"type": "string"},
                },
                "required": ["spreadsheet_id"],
            }
        },
        "implementation": "googlesheets_composio",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "googlesheets.write_cells",
        "name": "Escrever celulas planilha",
        "description": "Escreve valores em celulas de uma planilha Google Sheets.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range_": {"type": "string"},
                    "values": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                },
                "required": ["spreadsheet_id", "range_", "values"],
            }
        },
        "implementation": "googlesheets_composio",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
    {
        "id": "googlesheets.create_spreadsheet",
        "name": "Criar planilha",
        "description": "Cria uma nova planilha Google Sheets.",
        "function_schema": {
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                },
                "required": ["title"],
            }
        },
        "implementation": "googlesheets_composio",
        "config": {},
        "enabled": True,
        "updated_at": _now_iso(),
    },
]
