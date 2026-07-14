# Checklist Final de Deploy — Jennifer + omnichannel-agentes

**Data:** 2026-07-13
**Status Jennifer:** ✅ Connected (Evolution Manager confirmou)
**Domínio Evolution:** `https://evolution.coherenceai.com.br` → IP `34.95.181.124`
**Chatbot WhatsApp number (instance):** `+5511917389901`
**Master/Personal phone (allowlist proatividade):** `+5511966830020`

### Distinção crítica
- `+5511966830020` = **seu número pessoal** (Vinicius) → usado no `PROACTIVE_OWNER_PHONES` (allowlist)
- `+5511917389901` = **número do chatbot Jennifer** (instance WhatsApp) → apenas identificador da instância
- Proatividade SÓ com: seu número pessoal (DM) + membros de grupos fechados onde Jennifer está
- Resposta reativa: QUALQUER pessoa que mandar mensagem (DM ou grupo)

---

## ✅ Pré-Deploy (FEITO)

- [x] Código completo: 166 testes passando (152 agents_runtime + 14 whatsapp)
- [x] Evolution migrado para IP novo + domínio configurado
- [x] Master phone corrigido em 34 refs (14 arquivos)
- [x] Docs atualizadas (PLAN, HARNESS, GUARDRAILS, DIARIO_BORDO, ARQUITETURA)
- [x] Código frontend Portal (10 telas React)
- [x] Backend proxy Portal (12 endpoints)
- [x] Cloud Build YAMLs criados
- [x] Scripts de secrets + deploy criados

---

## ⏸ Deploy (PENDENTE — Requer você)

### 1. Cloud Build Triggers (manual no console)
Para cada repo, criar trigger:
- **Event:** Push to branch
- **Branch:** `^test$`
- **Build config:** `cloudbuild.yaml` (já existe em cada repo)

### 2. Upload de Secrets (1x)
```bash
cd agents_runtime
export DEEPSEEK_API_KEY="sk-..."
export NVIDIA_API_KEY="nvapi-..."
export MINIMAX_API_KEY="eyJ..."
export MINIMAX_GROUP_ID="..."
export SERPER_API_KEY="..."
export GOOGLE_OAUTH_TOKEN="$(cat token.json)"
export AGENTS_RUNTIME_SA_TOKEN="$(openssl rand -hex 32)"

chmod +x scripts/upload_all_secrets.sh
./scripts/upload_all_secrets.sh
```

### 3. git init + push (cada repo)
```bash
# Em cada repo:
git init
git checkout -b test
git remote add origin <YOUR_REPO_URL>
git add -A
git commit -m "feat: phase complete + Evolution IP 34.95.181.124"
git push origin test --set-upstream
# Cloud Build dispara automaticamente
```

### 4. Cloud Scheduler (após Cloud Run estar up)
Ver `agents_runtime/scripts/deploy_cloud_run.md` para comandos completos.

### 5. Registrar módulo no Portal (1x)
```bash
TOKEN=$(gcloud auth print-identity-token)
curl -X POST https://coherence-portal-test/api/admin/modules/omnichannel-agentes \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"Agentes Omnichannel","url":"https://agents-runtime-test-XXX.run.app","icon":"Bot"}'

curl -X POST https://coherence-portal-test/api/admin/permissions \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"target_email":"SEU_EMAIL","module_id":"omnichannel-agentes","role":"super-admin"}'
```

### 6. SSL no novo servidor Evolution (manual via SSH)
```bash
# No servidor 34.95.181.124
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d evolution.coherenceai.com.br
```

### 7. Atualizar webhook Evolution
No Manager (https://evolution.coherenceai.com.br/manager após SSL):
- Settings → Webhook → Update URL:
  ```
  https://whatsapp-agente-test-XXX.run.app/webhook
  ```
- Events: `MESSAGES_UPSERT`, `CONNECTION_UPDATE`

### 8. Validação fim-a-fim (após tudo)
```bash
# 1. Evolution up + SSL
curl https://evolution.coherenceai.com.br/health
curl -X GET "https://evolution.coherenceai.com.br/instance/connectionState/main" \
  -H "apikey: jennifer_secret_2025"
# Deve retornar "state": "open"

# 2. agents_runtime up
curl https://agents-runtime-test-XXX.run.app/healthz \
  -H "Authorization: Bearer $SA_TOKEN"

# 3. whatsapp-agente up
curl https://whatsapp-agente-test-XXX.run.app/healthz

# 4. Teste end-to-end via WhatsApp
# Enviar "Oi" do seu número pessoal (+5511966830020) PARA o chatbot (+5511917389901)
# Jennifer deve responder via orchestrator + LLM cascade

# 5. Card aparece no Portal Dashboard
# Logar no Portal → Dashboard → verificar card "Agentes Omnichannel"
```

---

## 📊 Resumo de Custos (Operacional Mensal)

Com todas otimizações (Tier 1 + Tier 2 + whatsapp min=0):

| Componente | Custo/mês |
|---|---|
| agents-runtime-test (2Gi, min=0, ping) | $5 |
| whatsapp-agente-test (1Gi, min=0, ping) | $3 |
| coherence-portal-test (já existe) | $5 |
| ata-worker (Job, 10min) | $1 |
| proactive-worker (Job, 15min) | $0.80 |
| lgpd-cleanup (Job, diário 3h) | $0.10 |
| LLM DeepSeek cascata | $0.20 |
| LLM proativo | $0.30 |
| Serper (com cache 24h) | $0.50 |
| Áudio Whisper | $0.005 |
| Scheduler + Firestore + Outros | $0.55 |
| **TOTAL** | **~$16.45/mês (~R$ 87)** |

---

## 🎯 Após Deploy — O que Jennifer vai fazer

Quando você mandar "Oi" para `+5511917389901`:

1. Evolution recebe mensagem → envia webhook para whatsapp-agente
2. whatsapp-agente aplica anti-ban (jitter 3-8s, rate-limit)
3. whatsapp-agente chama agents_runtime via Bearer SA token
4. agents_runtime detecta intent (clean → orchestrator)
5. orchestrator (jennifier) consulta agent_loader (Firestore cache)
6. LLM cascade: DeepSeek V4 Flash → escalação → Pro → fallback NVIDIA → MiniMax
7. tools: calendar.list_events (se relevante), web.search (se relevante)
8. resposta volta com delay_ms (typing effect)
9. whatsapp-agente envia via Evolution
10. histórico salvo em `contatos/+5511917389901/historico/{msg_id}`
11. audit log em `audit/` com SHA-256 do conteúdo

Comandos proativos (você pode usar):
- "Jennifer, silêncio" → proatividade off
- "Jennifer, modo zen" → 50% menos proativo
- "Jennifer, retomar" → volta ao normal

Cards no Portal (após deploy + permissão):
- 🤖 Agentes Omnichannel → `/admin/agents/review` (lista agentes)
- ➕ Criar Agente → form
- 🧪 Playground → testar mensagem
- 📊 Proatividade → dashboard de logs
- 💰 Custos → métricas DeepSeek

---

## 📞 Próximo Passo Imediato

**Se você tem credenciais GCP ativas:**
```bash
# 1. git init + push (cada repo)
# 2. ./scripts/upload_all_secrets.sh
# 3. Configurar Cloud Build triggers
# 4. Registrar módulo no Portal
# 5. Testar end-to-end
```

**Se NÃO tem credenciais GCP ativas:**
Posso ajudar a:
- Preparar docker-compose.yml para rodar agents_runtime local
- Criar script de deploy manual via gcloud CLI
- Documentar troubleshooting

Aguardo seu próximo comando.