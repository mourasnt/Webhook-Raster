#!/usr/bin/env python3
"""
Script de sanitização de logs existentes (execução manual, one-time).

Lê cada arquivo de log, aplica criptografia LGPD nos campos sensíveis
e reescreve o arquivo com dados protegidos.

Uso:
    set ENCRYPTION_KEY=sua_chave_aqui
    python sanitize_existing_logs.py

⚠️  Este script MODIFICA os arquivos de log em disco.
    Os dados pessoais originais serão criptografados.
    Podem ser recuperados com decrypt_logs.py + ENCRYPTION_KEY.
"""

import json
import os
import sys
from pathlib import Path

# Ajustar path para imports do projeto
sys.path.insert(0, str(Path(__file__).parent))

from lgpd import sanitize_payload
from utils import LOG_FILES


def sanitize_log_file(log_file: Path) -> tuple[int, int]:
    """
    Criptografa campos sensíveis em todas as entradas de um arquivo de log.

    Returns:
        (total_entries, sanitized_entries)
    """
    if not log_file.exists():
        return 0, 0

    entries: list[str] = []
    total = 0
    sanitized = 0

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            total += 1
            try:
                entry = json.loads(line)

                if "payload" in entry and isinstance(entry["payload"], dict):
                    entry["payload"] = sanitize_payload(entry["payload"])
                    sanitized += 1

                entries.append(json.dumps(entry, ensure_ascii=False))

            except json.JSONDecodeError:
                # Manter linha original se não for JSON válido
                entries.append(line)

    # Reescrever arquivo
    with open(log_file, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry + "\n")

    return total, sanitized


def main():
    # Verificar ENCRYPTION_KEY
    if not os.environ.get("ENCRYPTION_KEY"):
        print("ERRO: Variável ENCRYPTION_KEY não definida.")
        print()
        print("Gere uma chave com:")
        print('  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"')
        print()
        print("Depois defina:")
        print("  set ENCRYPTION_KEY=sua_chave_aqui")
        sys.exit(1)

    print("=" * 60)
    print("  Criptografia de Logs Existentes — LGPD")
    print("=" * 60)
    print()

    for webhook_type, log_file in LOG_FILES.items():
        if not log_file.exists():
            print(f"  [{webhook_type}] Arquivo não encontrado, pulando.")
            continue

        total, sanitized = sanitize_log_file(log_file)
        print(f"  [{webhook_type}] {total} entradas lidas, {sanitized} criptografadas")
        print(f"    → {log_file}")

    print()
    print("Criptografia concluída.")
    print("Campos protegidos: identification, password, base64, placa")
    print()
    print("Para descriptografar, use:")
    print("  python decrypt_logs.py PESQUISACONCULTA")


if __name__ == "__main__":
    main()
