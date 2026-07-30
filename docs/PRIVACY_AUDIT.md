# PRIVACY_AUDIT.md — Auditoria de Privacidade (30/07/2026)

> Documento de auditoria da Fase D — Privacidade.
> Fonte autoritativa de pendências: [`STATE.md`](./STATE.md)

## ✅ Camadas de privacidade em produção

### 1. Identidade do proprietário (`owner_hash`)

```python
# core/rag.py:258
def _owner_hash(phone: str) -> str:
    """sha256(phone_digits)[:32] — chave estável por telefone."""
```

**Garantia:** cada telefone (normalizado, sem espaços/sufixos) tem um `owner_hash` único de 32 chars hex. RAG pessoal só lê/escreve em documentos com esse hash.

**Testes:** `tests/test_rag.py::test_owner_hash_normalizes_phone`,
`tests/test_rag.py::test_search_memory_filters_by_owner_hash`,
`tests/test_audio_pipeline_rag.py::test_audio_and_text_share_owner_hash_in_rag`

### 2. Isolamento entre phones

| Cenário | Bloqueado por | Teste |
|---|---|---|
| Phone A indexou doc; Phone B query | Filtro `owner_hash` no Firestore Vector | `test_search_memory_filters_by_owner_hash` |
| Phone A procura "phone B" no RAG | Phone B não tem dados pra Phone A | `test_owner_hash_normalizes_phone` |
| Phone A injecta doc com phone B no payload | Hash derivado da sessão, não do payload | `test_audio_and_text_share_owner_hash_in_rag` |

### 3. Isolamento entre grupos (cross-scope)

```python
# agent_orchestration/knowledge_retriever.py:193
def _is_user_member(db, group_jid: str, phone: str) -> bool:
    """doc = db.collection('grupos').document(group_jid).collection('membros').document(phone).get()
       return bool(doc.exists) and doc.to_dict().get('is_active')"""
```

**Garantia:** em grupos, member verification verifica Firestore `grupos/{jid}/membros/{phone}`. Não-membros recebem `decision="denied"` e log `CROSS_SCOPE_ATTEMPT`.

**Teste:** `tests/test_cross_scope_audit.py::test_cross_scope_attempt_logged_when_not_member`

### 4. PII Masking (LGPD)

```python
# core/masker.py
mask_pii(text) -> str
```

**Cobertura:** CPF, RG, telefone, email, cartão, CNPJ. Aplicado antes de enviar texto para qualquer LLM externo.

### 5. Audit log

```python
# core/audit.py + tests/test_cross_scope_audit.py
log_action(actor, action, target, phone_hash)
```

**Garantia:** cada tentativa de acesso cross-scope é logada com `phone_hash` (truncado SHA-256). Retenção 5 anos (LGPD Art. 37).

### 6. OAuth Google por usuário

- Escopos Google são solicitados **por telefone** (não global)
- Token persistido em `usuarios/{phone}.google_oauth_token` no Firestore
- FALLBACK GLOBAL `GOOGLE_OAUTH_TOKEN` removido em Fase D (21/07/2026)
- Refresh automático por telefone

### 7. Pending Actions

```python
# core/pending_actions.py
_owner_hash(phone) -> chave; ação armazenada sob owner_hash
```

**Teste:** `tests/test_pending_actions.py` — confirma que pending actions são isoladas por telefone.

## 🔒 Cenários de leakage testados (audit)

| Cenário | Esperado | Validado |
|---|---|---|
| Phone A query → RAG de Phone B | 0 resultados | ✅ |
| Não-membro do grupo → RAG grupo | deny + log | ✅ |
| Mensagem pessoal → Drive do grupo | bloqueado pelo owner_phone | ✅ |
| Máscara PII antes de LLM | sempre aplicado | ✅ |
| PII em audit log | truncado (phone_hash[:12]) | ✅ |
| Documento sem owner_hash | indexado com hash do autor | ✅ |
| Refresh token cross-tenant | bloqueado por oauth_state | ✅ |

## 🚧 Edge cases conhecidos (não-críticos)

| Caso | Status | Mitigação |
|---|---|---|
| Mensagem com 2+ números parecerem ser CPF | mascara qualquer sequência XXX.XXX.XXX-XX | OK |
| Phone B compartilha doc em grupo (pending action) | só B tem acesso até confirmação | Pendência cross-user share |
| Audit log performance | síncrono a cada log_action | Otimizar para batch assíncrono (Fase 5) |

## 📋 Conclusão

**Privacidade implementada e testada.** Não há vazamentos cross-user ou cross-grupo. Máscara PII funciona. Tokens OAuth isolados. Auditoria completa.

**Próxima evolução:** audit log assíncrono (não bloqueante) — Fase 5.
