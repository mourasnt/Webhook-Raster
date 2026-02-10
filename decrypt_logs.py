#!/usr/bin/env python3
"""
Utilitário para descriptografar logs protegidos pela LGPD.

Lê arquivos de log com campos criptografados (prefixo 'ENC::')
e exibe ou exporta os dados originais usando a ENCRYPTION_KEY.

Uso:
    # Descriptografar e exibir no terminal
    python decrypt_logs.py PESQUISACONCULTA

    # Descriptografar e salvar em arquivo
    python decrypt_logs.py PESQUISACONCULTA --output decrypted_pesquisa.json

    # Descriptografar todos os tipos
    python decrypt_logs.py --all

    # Descriptografar um log entry específico por event_id
    python decrypt_logs.py PESQUISACONCULTA --event-id abc123...

Variáveis de ambiente necessárias:
    ENCRYPTION_KEY — mesma chave usada pela aplicação para criptografar

⚠️  Os dados descriptografados contêm informações pessoais protegidas pela LGPD.
    Trate com o devido cuidado e não exponha em ambientes inseguros.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Ajustar path para imports do projeto
sys.path.insert(0, str(Path(__file__).parent))

from lgpd import desanitize_payload
from utils import LOG_FILES


def decrypt_log_file(
    log_file: Path,
    event_id_filter: str | None = None,
) -> list[dict]:
    """
    Descriptografa todas as entradas de um arquivo de log.

    Args:
        log_file: Caminho do arquivo de log
        event_id_filter: Se fornecido, retorna apenas entries com este event_id

    Returns:
        Lista de dicts com dados descriptografados
    """
    if not log_file.exists():
        return []

    results = []

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)

                # Filtrar por event_id se fornecido
                if event_id_filter and entry.get("event_id") != event_id_filter:
                    continue

                # Descriptografar payload
                if "payload" in entry and isinstance(entry["payload"], dict):
                    entry["payload"] = desanitize_payload(entry["payload"])

                results.append(entry)

            except json.JSONDecodeError:
                continue

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Descriptografar logs protegidos pela LGPD"
    )
    parser.add_argument(
        "webhook_type",
        nargs="?",
        choices=["CHECKLIST", "RESULTADOCHECKLIST", "PESQUISACONCULTA"],
        help="Tipo de webhook para descriptografar",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Descriptografar todos os tipos de webhook",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Arquivo de saída (JSON). Se omitido, exibe no terminal.",
    )
    parser.add_argument(
        "--event-id",
        type=str,
        help="Filtrar por event_id específico",
    )

    args = parser.parse_args()

    if not args.webhook_type and not args.all:
        parser.error("Informe o webhook_type ou use --all")

    # Verificar ENCRYPTION_KEY
    if not os.environ.get("ENCRYPTION_KEY"):
        print("ERRO: Variável ENCRYPTION_KEY não definida.")
        print("Defina com: set ENCRYPTION_KEY=sua_chave_aqui")
        sys.exit(1)

    types_to_process = (
        list(LOG_FILES.keys()) if args.all
        else [args.webhook_type]
    )

    all_results: dict[str, list] = {}

    print("=" * 60)
    print("  Descriptografia de Logs — LGPD")
    print("=" * 60)
    print()

    for wtype in types_to_process:
        log_file = LOG_FILES.get(wtype)
        if not log_file:
            continue

        entries = decrypt_log_file(log_file, args.event_id)
        all_results[wtype] = entries
        print(f"  [{wtype}] {len(entries)} entradas descriptografadas")

    print()

    if args.output:
        # Salvar em arquivo
        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"Dados salvos em: {output_path}")
        print("⚠️  ATENÇÃO: Este arquivo contém dados pessoais (LGPD).")
        print("   Exclua após o uso e não compartilhe.")
    else:
        # Exibir no terminal
        for wtype, entries in all_results.items():
            if not entries:
                continue
            print(f"\n{'─' * 60}")
            print(f"  {wtype}")
            print(f"{'─' * 60}")
            for entry in entries:
                print(json.dumps(entry, ensure_ascii=False, indent=2))
                print()


if __name__ == "__main__":
    main()
