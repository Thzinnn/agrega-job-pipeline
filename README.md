# Agrega Job Pipeline - Agent + Worker

## Estrutura
```
agrega-job-pipeline/
├── .env                      # Segredos (NÃO COMMITAR)
├── requirements.txt          # Python deps do worker
├── worker.py                 # Bridge: HTTP -> Hermes -> Webhook Agrega
├── skills/
│   └── job-formatter/        # Skill Hermes (2 instâncias = HA)
│       ├── SKILL.md          # System prompt + tool definitions
│       ├── references/
│       │   ├── schema-output.json      # Contrato de saída (validação obrigatória)
│       │   └── schema-input-hints.json # Dicas de input (flexível)
│       └── scripts/
│           └── validate_output.py      # Validador JSON Schema
└── system-prompt-extrator.md # Documentação do prompt (referência)
```

## Setup

### 1. Hermes + Ollama (gratuito, local)
```bash
# Instala Hermes
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Instala Ollama
winget install Ollama.Ollama  # Windows
# ou: curl -fsSL https://ollama.com/install.sh | sh  # Linux/Mac

# Baixa modelo recomendado (bom em extração, ~8GB RAM)
ollama pull llama3.1:8b
# ou mais pesado: ollama pull qwen2.5:14b

# Configura Hermes para usar Ollama
hermes model
# Selecione: Provider=Ollama, Model=llama3.1:8b
```

### 2. Instala skill
```bash
# O skill já está em skills/job-formatter/
# Hermes carrega automaticamente de ~/.hermes/skills/ ou $HERMES_HOME/skills/
# Se não carregou: hermes skill install file:///C:/Users/Thiago/agrega-job-pipeline/skills/job-formatter
```

### 3. Configura .env
```bash
cp .env.example .env
# Edite com seus valores reais
```

### 4. Instala deps do worker
```bash
pip install -r requirements.txt
```

### 5. Implementa `get_db_schema()` no worker.py
Substitua o stub pela query real no banco do Agrega:
```python
def get_db_schema():
    import psycopg2  # ou seu driver
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'jobs'
        ORDER BY ordinal_position
    """)
    cols = []
    for row in cur.fetchall():
        cols.append({
            "name": row[0],
            "type": row[1],
            "nullable": row[2] == "YES",
            "comment": row[3] or ""
        })
    cur.close()
    conn.close()
    return {"columns": cols}
```

## Rodar (2 instâncias para HA)

Terminal 1:
```bash
WORKER_PORT=8080 python worker.py
```

Terminal 2:
```bash
WORKER_PORT=8081 python worker.py
```

Coloque um load balancer (nginx, traefik, cloud LB) na frente das duas portas.

## Testar

```bash
# Health check
curl http://localhost:8080/health

# Enviar vaga crua (exemplo Indeed)
curl -X POST http://localhost:8080/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "event": "job.upsert",
    "jobs": [{
      "id": "678399f28792a12c",
      "title": "Auxiliar de Compras",
      "company": "Concessionária Tamoios",
      "location": "Caraguatatuba, SP",
      "salary": null,
      "contract_type": "Efetivo CLT",
      "work_schedule": "De segunda à sexta-feira",
      "benefits": "Vale-transporte, Vale-refeição",
      "description": "O que você vai fazer?\\n\\nAtuar com atendimento...\\n\\n• Vale-transporte\\n• Salário R$ 3.000,00 – R$ 3.440,45 por mês",
      "url": "https://br.indeed.com/viewjob?jk=678399f28792a12c",
      "scraped_at": "2026-10-06 07:42"
    }]
  }'
```

## Como funciona a extração inteligente

O agente recebe o input acima (salary=null), lê a `description`, encontra "Salário R$ 3.000,00 – R$ 3.440,45 por mês" e produz:

```json
{
  "jobs": [{
    "id_vaga": "a1b2c3d4e5f6",
    "titulo": "Auxiliar de Compras",
    "empresa": "Concessionária Tamoios",
    "local": "Caraguatatuba, SP",
    "salario": "R$ 3.000,00 – R$ 3.440,45 por mês",
    "tipo_vaga": "Efetivo CLT",
    "turno_horario": "De segunda à sexta-feira",
    "beneficios": "Vale-transporte, Vale-refeição",
    "descricao": "O que você vai fazer?\\n\\nAtuar com atendimento...\\n\\n• Vale-transporte\\n• Salário R$ 3.000,00 – R$ 3.440,45 por mês",
    "link": "https://br.indeed.com/viewjob?jk=678399f28792a12c",
    "data_coleta": "2026-10-06 07:42"
  }],
  "campos_inferidos": ["salario"]
}
```

O worker valida, assina HMAC, envia pro webhook. Se der 400/500, reenvia com novo `X-Agrega-Delivery`.

## Colunas dinâmicas do banco

Toda execução o agente chama `get_db_schema()` (implementado no worker). Se você adicionar coluna `has_gympass` no banco, na próxima vaga o agente já sabe que deve procurar "Gympass" na descrição e incluir no campo `beneficios`.

## Logs de auditoria

`campos_inferidos` no retorno mostra o que o agente preencheu lendo a descrição (não veio no input). Use para monitorar qualidade dos scrapers.