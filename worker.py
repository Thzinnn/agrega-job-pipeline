#!/usr/bin/env python3
"""
Worker bridge: recebe JSON cru (HTTP), chama Hermes job-formatter, valida, envia ao webhook Agrega com HMAC.
Duas instâncias deste worker rodando = HA (load balancer na frente).
"""

import os
import sys
import json
import time
import uuid
import hmac
import hashlib
import subprocess
import requests
from datetime import datetime
from pathlib import Path

# Carrega .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# Database driver
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE", "https://jobs-api.thiagoil2006.workers.dev/api/v1/webhooks/receive/")
WEBHOOK_ID = os.getenv("WEBHOOK_ID", "81fb7623-e731-49ae-8012-be7a467f74a6")
WEBHOOK_SECRET = os.getenv("AGREGA_WEBHOOK_SECRET")
HERMES_CMD = os.getenv("HERMES_CMD", "hermes")  # ou caminho completo

if not WEBHOOK_SECRET:
    print("ERRO: AGREGA_WEBHOOK_SECRET não definido no .env", file=sys.stderr)
    sys.exit(1)

WEBHOOK_URL = f"{WEBHOOK_URL_BASE.rstrip('/')}/{WEBHOOK_ID}"

SKILL_DIR = Path(__file__).parent / "skills" / "job-formatter"
VALIDATE_SCRIPT = SKILL_DIR / "scripts" / "validate_output.py"

def get_db_schema():
    """
    Tool implementation: retorna schema atual da tabela jobs.
    Conecta no PostgreSQL (Neon) e busca information_schema.columns.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL não definido no .env")
    
    if not psycopg2:
        raise RuntimeError("psycopg2 não instalado. pip install psycopg2-binary")
    
    conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'jobs'
                ORDER BY ordinal_position
            """)
            cols = []
            for row in cur.fetchall():
                cols.append({
                    "name": row["column_name"],
                    "type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "comment": row["column_default"] or ""
                })
            return {"columns": cols}
    finally:
        conn.close()

def call_hermes(input_json: dict) -> dict:
    """
    Chama `hermes chat -q` com o skill job-formatter.
    Injeta o schema do banco no system prompt via tool call simulada.
    """
    # Prepara input para o Hermes: adiciona schema do banco no contexto
    db_schema = get_db_schema()
    
    # O Hermes com skill job-formatter espera receber o input bruto
    # O system prompt do skill já instrui o modelo a chamar get_db_schema
    # Mas como estamos no one-shot CLI, vamos injetar o schema no prompt
    
    prompt = f"""INPUT_BRUTO:
{json.dumps(input_json, ensure_ascii=False)}

SCHEMA_BANCO_ATUAL:
{json.dumps(db_schema, ensure_ascii=False)}

Processe conforme instruções do skill job-formatter. Retorne APENAS o JSON de saída válido."""
    
    cmd = [HERMES_CMD, "chat", "-q", prompt, "--skill", "job-formatter"]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Hermes timeout (>5min)")
    
    if result.returncode != 0:
        raise RuntimeError(f"Hermes falhou (exit {result.returncode}): {result.stderr}")
    
    # Extrai JSON da saída (pode vir com texto extra)
    stdout = result.stdout.strip()
    try:
        # Tenta parse direto
        return json.loads(stdout)
    except json.JSONDecodeError:
        # Tenta extrair JSON entre chaves
        import re
        match = re.search(r'\{.*\}', stdout, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise RuntimeError(f"Saída do Hermes não é JSON válido: {stdout[:500]}")

def validate_output(data: dict) -> bool:
    """Chama script de validação."""
    result = subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT)],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=10
    )
    if result.returncode != 0:
        print(f"Validação falhou: {result.stderr}", file=sys.stderr)
        return False
    return True

def sign_payload(raw_body: str, timestamp: str) -> str:
    message = f"{timestamp}.{raw_body}".encode('utf-8')
    return hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        message,
        hashlib.sha256
    ).hexdigest()

def send_to_webhook(jobs_array: list) -> requests.Response:
    payload = {"event": "job.upsert", "jobs": jobs_array}
    raw_body = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
    timestamp = str(int(time.time()))
    delivery_id = str(uuid.uuid4())
    signature = sign_payload(raw_body, timestamp)
    
    headers = {
        "Content-Type": "application/json",
        "X-Agrega-Timestamp": timestamp,
        "X-Agrega-Signature": f"sha256={signature}",
        "X-Agrega-Delivery": delivery_id
    }
    
    resp = requests.post(WEBHOOK_URL, data=raw_body.encode('utf-8'), headers=headers, timeout=30)
    return resp

def process_raw_input(raw_input: dict) -> dict:
    """Pipeline completo: Hermes -> Valida -> Webhook."""
    # 1. Chama Hermes
    formatted = call_hermes(raw_input)
    
    # 2. Valida saída
    if not validate_output(formatted):
        raise ValueError("Saída do agente inválida perante schema-output.json")
    
    # 3. Extrai jobs e campos_inferidos
    jobs = formatted.get("jobs", [])
    campos_inferidos = formatted.get("campos_inferidos", [])
    
    if not jobs:
        raise ValueError("Nenhum job na saída do agente")
    
    # 4. Envia ao webhook com retry (novo delivery_id a cada tentativa)
    max_retries = 3
    for attempt in range(max_retries):
        resp = send_to_webhook(jobs)
        if resp.status_code == 200:
            try:
                resp_json = resp.json()
                if resp_json.get("success") is False and resp_json.get("code") == "IDEMPOTENT_REPLAY":
                    # Replay com mesmo delivery_id - gerar novo e tentar de novo
                    print(f"Idempotent replay detectado, nova tentativa...", file=sys.stderr)
                    continue
            except:
                pass
            return {"success": True, "status_code": resp.status_code, "response": resp.json(), "campos_inferidos": campos_inferidos}
        elif resp.status_code in (400, 500):
            # Erro de negócio - retry com NOVO delivery_id (loop continua)
            print(f"Erro {resp.status_code}, tentativa {attempt+1}/{max_retries}: {resp.text}", file=sys.stderr)
            time.sleep(2 ** attempt)  # backoff
            continue
        else:
            # Outro erro - não retry
            return {"success": False, "status_code": resp.status_code, "error": resp.text}
    
    return {"success": False, "error": f"Falhou após {max_retries} tentativas"}

# === HTTP Server (exemplo com Flask) ===
if __name__ == "__main__":
    from flask import Flask, request, jsonify
    
    app = Flask(__name__)
    
    @app.route("/ingest", methods=["POST"])
    def ingest():
        try:
            raw = request.get_json(force=True)
            result = process_raw_input(raw)
            if result.get("success"):
                return jsonify(result), 200
            else:
                return jsonify(result), 500
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    
    @app.route("/health", methods=["GET"])
    def health():
        # Teste rápido do Hermes
        try:
            test = call_hermes({"jobs": [{"titulo": "teste", "empresa": "teste", "local": "Remoto", "descricao": "teste"}]})
            return jsonify({"status": "ok", "hermes": "responsive"}), 200
        except Exception as e:
            return jsonify({"status": "degraded", "error": str(e)}), 503
    
    port = int(os.getenv("WORKER_PORT", "8080"))
    print(f"Worker iniciando na porta {port}...")
    app.run(host="0.0.0.0", port=port)
