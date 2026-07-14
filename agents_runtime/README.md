# 🟢 Jennifer — Modulo `omnichannel-agentes` no Coherence Portal

**Status:** ✅ Pronto para deploy | **166 testes passando** | **~170 arquivos**

Plataforma multi-agente WhatsApp com Jennifer como assistente corporativa.

---

## 📁 Estrutura dos Repos

| Repo | Localização | Foco |
|---|---|---|
| `Coherence_Portal` | `C:\Users\vinic\workspace_antigravity\Coherence_Portal\` | UI gestão (`/admin/agents/*`) + proxy backend |
| `WhatsappAgente` | `C:\Users\vinic\workspace_antigravity\WhatsappAgente\` | Thin proxy Evolution → agents_runtime |
| `ChatBotWhatsapp/agents_runtime` | `C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp\agents_runtime\` | Runtime principal (LLM, tools, RAG, audio) |

---

## 🎯 O Que Jennifer Faz

- ✅ Responde mensagens WhatsApp (texto + áudio com Whisper)
- ✅ Delega para 4 managers (calendar, drive, email, web) + 4 specialists (intimacy, learning, morality, ata-generator)
- ✅ Cascata LLM: DeepSeek V4 Flash → escalação automática → Pro → fallback NVIDIA NIM → MiniMax M3
- ✅ RAG jurídico (MiniMax embo-01 1536d + Firestore Vector)
- ✅ Proatividade calibrada (2/dia, 5 global, 8 camadas anti-spam, 7 comandos)
- ✅ LGPD: masker PII, TTL 90d, opt-out, audit log
- ✅ Memória por contato (subcollection `historico/`)
- ✅ Apelidos com consentimento (built-in + aprendizado)

---

## 🔑 Números Importantes

| Item | Valor |
|---|---|
| **Seu número pessoal (master/owner)** | `+5511966830020` |
| **Número do chatbot Jennifer (instance)** | `+5511917389901` |
| **IP Evolution (antigo)** | `34.39.162.165` |
| **IP Evolution (novo)** | `34.95.181.124` |
| **Domínio Evolution** | `https://evolution.coherenceai.com.br` |
| **GCP project** | `coherence-ominichannel-fs` (Portal + agents_runtime) |
| **GCP project (Evolution)** | `whatsapp-server-fs` |

---

## ⚡ Quick Start (Deploy GCP Test)

**ATENÇÃO:** Não há teste local. Todos os testes rodam no ambiente GCP test (`agents-runtime-test` Cloud Run).

```bash
cd ChatBotWhatsapp/agents_runtime

# 1. Instalar deps (apenas para IDE/linter)
pip install -r requirements.txt

# 2. Deploy direto para GCP test (Cloud Build)
git push origin test
# → Cloud Build dispara automaticamente → deploy em agents-runtime-test

# 3. Smoke test contra URL real do GCP
curl https://agents-runtime-test-XXX-uc.a.run.app/healthz \
  -H "Authorization: Bearer $SA_TOKEN"
```

## 🧪 Como Testar (GCP Test Environment)

1. Push para branch `test` dispara Cloud Build
2. Cloud Build faz deploy em `agents-runtime-test` (Cloud Run)
3. Smoke test contra URL real:
   ```bash
   curl https://agents-runtime-test-XXX-uc.a.run.app/healthz
   ```
4. Teste end-to-end via WhatsApp (Evolution Manager → Jennifer → resposta)

Para logs detalhados, use `gcloud logs read` ou Cloud Console.

---

## 🚀 Deploy Produção (GCP)

### Pré-requisitos
- `gcloud` CLI autenticado
- Repositórios git remotos configurados
- Cloud Build triggers criados para branch `test`

### Passo a passo

```bash
# 1. Upload de secrets
export DEEPSEEK_API_KEY="sk-..."
export NVIDIA_API_KEY="nvapi-..."
export MINIMAX_API_KEY="eyJ..."
export MINIMAX_GROUP_ID="..."
export SERPER_API_KEY="..."
export GOOGLE_OAUTH_TOKEN="$(cat token.json)"

cd ChatBotWhatsapp/agents_runtime
./scripts/upload_all_secrets.sh

# 2. Push código (cada repo)
./scripts/deploy_all.sh
# Cloud Build dispara automaticamente

# 3. Configurar Cloud Scheduler (ver scripts/deploy_cloud_run.md)

# 4. Registrar módulo no Portal
TOKEN=$(gcloud auth print-identity-token)
curl -X POST https://coherence-portal-test/api/admin/modules/omnichannel-agentes \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"Agentes Omnichannel","url":"https://agents-runtime-test-XXX.run.app","icon":"Bot"}'
```

Ver checklist completo: `scripts/DEPLOY_CHECKLIST.md`

---

## 📊 Custos Mensais (~$17/mês = ~R$ 87)

| Componente | Custo |
|---|---|
| agents-runtime-test (2Gi, min=0) | $5 |
| whatsapp-agente-test (1Gi, min=0) | $3 |
| coherence-portal-test (já existe) | $5 |
| ata-worker + proactive-worker + lgpd-cleanup | $2 |
| LLM (DeepSeek cascata) | $0.20 |
| LLM proativo | $0.30 |
| Serper (com cache 24h) | $0.50 |
| Áudio + Scheduler + Firestore | $0.55 |

---

## 🎯 Comandos Proativos (você pode usar)

| Comando | Efeito |
|---|---|
| `Jennifer, silêncio` | Proatividade off |
| `Jennifer, modo zen` | Reduz frequência em 50% |
| `Jennifer, modo turbo` | Aumenta frequência (até 2/dia) |
| `Jennifer, só emergências` | Só situações críticas |
| `Jennifer, retomar` | Volta ao normal |
| `Jennifer, grupo off` | Desativa proatividade em grupo |
| `Jennifer, grupo on` | Reativa proatividade em grupo |

---

## 🧪 Testes (executados no CI/CD do GCP)

```bash
# Os testes rodam automaticamente no Cloud Build durante o deploy
# Configuração em cloudbuild.yaml: "pip install + pytest -q tests/"

# Para rodar localmente (apenas para desenvolvimento):
cd ChatBotWhatsapp/agents_runtime
pytest tests/ -q           # 152 passed, 9 skipped

cd ../../WhatsappAgente
pytest tests/ -q           # 14 passed
# TOTAL: 166 passed
```

---

## 📞 Próximo Passo Imediato

**Se você tem credenciais GCP ativas:**
```bash
# Configure git remotes:
cd ChatBotWhatsapp/agents_runtime && git remote add origin <URL>
cd ../../WhatsappAgente && git remote add origin <URL>
cd ../../Coherence_Portal && git remote add origin <URL>

# Push + deploy:
cd ../ChatBotWhatsapp/agents_runtime
./scripts/deploy_all.sh

# Upload secrets:
./scripts/upload_all_secrets.sh
```

**Se NÃO tem credenciais GCP:**
- Use `./scripts/dev.sh up` para testar local
- Deploy fica para quando você configurar credenciais

---

## 📚 Documentação

- [PLAN_OMNICHANNEL_AGENTES.md](docs/PLAN_OMNICHANNEL_AGENTES.md) — plano completo 16 seções
- [ARQUITETURA.md](docs/ARQUITETURA.md) — diagrama + componentes
- [HARNESS.md](docs/HARNESS.md) — setup + secrets + scheduler
- [GUARDRAILS.md](docs/GUARDRAILS.md) — regras inegociáveis
- [DIARIO_BORDO.md](docs/DIARIO_BORDO.md) — histórico de decisões
- [MODULE_INTEGRATION_AGENTES.md](../Coherence_Portal/docs/MODULE_INTEGRATION_AGENTES.md) — contrato Portal ↔ agents_runtime
- [scripts/DEPLOY_CHECKLIST.md](scripts/DEPLOY_CHECKLIST.md) — checklist final deploy
- [scripts/deploy_cloud_run.md](scripts/deploy_cloud_run.md) — comandos Cloud Scheduler

---

**Implementação:** 13/07/2026 | **Owner:** Vinicius | **Versão:** 1.0.0-test