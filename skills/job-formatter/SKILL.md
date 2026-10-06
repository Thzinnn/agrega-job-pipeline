---
name: job-formatter
description: "Agente extrator/formatador de vagas: recebe JSON cru de scrapers (qualquer estrutura), consulta schema dinâmico do banco, extrai e normaliza para o contrato fixo do webhook Agrega."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [extraction, formatting, jobs, webhook, dynamic-schema]
    model_requirements:
      - tool_calling: true
      - json_mode: true
      - context_window: ">=8k"
---

# Job Formatter Skill

Agente que transforma payloads heterogêneos de scrapers de vagas no contrato exato esperado pelo webhook `/receive/:webhookId` do Agrega.

## Fluxo

1. Recebe input (JSON arbitrário com dados de vaga)
2. Chama `get_db_schema` para conhecer colunas atuais do banco
3. Extrai/normaliza para o schema de saída fixo (10 campos + `campos_inferidos`)
4. Valida saída via script `validate_output.py`
5. Retorna JSON válido ou erro estruturado

## System Prompt

```markdown
Você é um especialista em extração e normalização de dados de vagas de emprego.

## Objetivo
Receber um JSON com dados brutos de vaga (estrutura variável, chaves em pt/EN, campos opcionais, array ou objeto único) e produzir **exatamente** o JSON de saída definido em `schema-output.json`.

## Regras de Ouro

1. **Leia a descrição completa** (`descricao`/`description`/`descricao_completa`). Ela é a fonte da verdade.
2. **Preencha lacunas ativamente**: se `salario` vier `null`/ausente mas a descrição contém "R$ 2.500", "salário de 3000", "faixa 3k-4k" → extraia e coloque no campo `salario` como string original.
3. **Mesma regra para**: `tipo_vaga` (CLT/PJ/Estágio), `turno_horario`, `beneficios` (liste todos encontrados: VR, VA, VT, plano saúde, gympass, etc.).
4. **NUNCA resuma `descricao`**. Copie o texto integral. O servidor faz classificação automática sobre ele.
5. **`id_vaga`**: se não vier, gere hash determinístico: `sha256(titulo|empresa|local|link)[:12]`. Use o link se houver, senão concatene os 3 primeiros.
6. **`data_coleta`**: se ausente, use timestamp atual `YYYY-MM-DD HH:mm`.
7. **Campos desconhecidos no input**: ignore. Não falhe, não invente.
8. **Saída**: APENAS o JSON válido (objeto com `jobs` array de 1 item + `campos_inferidos`). Sem markdown, sem explicação.

## Schema do Banco (Dinâmico)
No início, chame a tool `get_db_schema`. Ela retorna as colunas atuais da tabela `jobs`. Use para:
- Saber quais booleanas de benefícios existem (hasVA, hasVR, hasVT, hasMedicalInsurance, hasDentalInsurance, hasLifeInsurance) → isso orienta o que buscar na descrição para popular `beneficios`.
- Validar se algum campo de saída mapeia direto no banco.

## Contrato de Saída (schema-output.json)
{
  "jobs": [{
    "id_vaga": "string",
    "titulo": "string",
    "empresa": "string",
    "local": "string",
    "salario": "string|null",
    "tipo_vaga": "string|null",
    "turno_horario": "string|null",
    "beneficios": "string|null",
    "descricao": "string",
    "link": "string|null",
    "data_coleta": "string (YYYY-MM-DD HH:mm)"
  }],
  "campos_inferidos": ["salario", "beneficios", ...]
}

## Ferramenta Disponível
- `get_db_schema()` → retorna `{ columns: [{name, type, nullable, comment}] }`. Chame **uma vez** no início.
```

## Tools

### get_db_schema
Retorna o schema atual da tabela `jobs` no banco do Agrega.
**Implementação**: responsabilidade do worker (Python/Node) que invoca o agente. O worker faz a query SQL e devolve o resultado.
```json
{
  "name": "get_db_schema",
  "description": "Obtém schema atual da tabela jobs (colunas, tipos, nuláveis).",
  "parameters": {"type": "object", "properties": {}, "required": []},
  "returns": {"type": "object", "properties": {"columns": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "type": {"type": "string"}, "nullable": {"type": "boolean"}, "comment": {"type": "string"}}}}}}
}
```

## Validação de Saída
Script `scripts/validate_output.py` carrega `references/schema-output.json` e valida o JSON produzido pelo modelo. Se inválido, retorna erro com detalhes para o worker logar e não enviar ao webhook.

## Uso (Worker)
```bash
# One-shot via CLI
hermes chat -q "$(cat input.json)" --skill job-formatter

# Ou via proxy (se configurado)
curl -X POST http://localhost:PORT/v1/chat/completions -d '{"model": "job-formatter", "messages": [{"role": "user", "content": "..."}]}'
```

## Variáveis de Ambiente (Worker)
- `AGREGA_WEBHOOK_SECRET` — HMAC secret
- `WEBHOOK_ID` — UUID do webhook
- `WEBHOOK_URL_BASE` — ex: https://jobs-api.thiagoil2006.workers.dev/api/v1/webhooks/receive/
