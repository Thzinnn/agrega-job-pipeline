#!/usr/bin/env python3
"""
Validador de saída do job-formatter.
Carrega schema-output.json e valida o JSON produzido pelo modelo.
Uso: python validate_output.py < arquivo_json_saida
Retorna: exit 0 se válido, exit 1 + erro no stderr se inválido.
"""

import sys
import json
from pathlib import Path
try:
    import jsonschema
except ImportError:
    print("ERRO: jsonschema não instalado. pip install jsonschema", file=sys.stderr)
    sys.exit(1)

SCHEMA_PATH = Path(__file__).parent.parent / "references" / "schema-output.json"

def main():
    if not SCHEMA_PATH.exists():
        print(f"ERRO: Schema não encontrado em {SCHEMA_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"ERRO: JSON inválido na entrada: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        jsonschema.validate(instance=data, schema=schema)
        # Sucesso silencioso (stdout limpo para o worker capturar)
        sys.exit(0)
    except jsonschema.ValidationError as e:
        print(f"VALIDATION_ERROR: {e.message}", file=sys.stderr)
        print(f"  Caminho: {' -> '.join(str(p) for p in e.path)}", file=sys.stderr)
        print(f"  Valor recebido: {e.instance}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
