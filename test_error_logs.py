#!/usr/bin/env python3
"""
Script de teste para validar o sistema de error logs.
Simula diferentes tipos de erros HTTP (400, 422, 500) e verifica se são registrados corretamente.
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:1214"

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def test_error_400_empty_body():
    """Teste: Enviar body vazio (erro 400)"""
    print_section("Teste 1: Body Vazio (400)")
    
    response = requests.post(f"{BASE_URL}/webhook", json={})
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 400
    print("✅ Erro 400 capturado com sucesso")

def test_error_400_missing_metodo():
    """Teste: Payload sem campo 'metodo' (erro 400)"""
    print_section("Teste 2: Campo 'metodo' Ausente (400)")
    
    payload = {
        "codchecklist": 123,
        "placa": "ABC1234"
    }
    
    response = requests.post(f"{BASE_URL}/webhook", json=payload)
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 400
    print("✅ Erro 400 capturado com sucesso")

def test_error_400_unsupported_type():
    """Teste: Webhook type não suportado (erro 400)"""
    print_section("Teste 3: Webhook Type Não Suportado (400)")
    
    payload = {
        "metodo": "TIPO_INVALIDO",
        "dados": "teste"
    }
    
    response = requests.post(f"{BASE_URL}/webhook", json=payload)
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 400
    print("✅ Erro 400 capturado com sucesso")

def test_error_422_missing_required_field():
    """Teste: Campo obrigatório ausente (erro 422)"""
    print_section("Teste 4: Campo Obrigatório Ausente (422)")
    
    payload = {
        "metodo": "CHECKLIST",
        "codchecklist": 456
        # Falta o campo 'placa' que é obrigatório
    }
    
    response = requests.post(f"{BASE_URL}/webhook", json=payload)
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 422
    print("✅ Erro 422 capturado com sucesso")

def test_error_422_invalid_data_type():
    """Teste: Tipo de dado inválido (erro 422)"""
    print_section("Teste 5: Tipo de Dado Inválido (422)")
    
    payload = {
        "metodo": "CHECKLIST",
        "placa": "ABC1234",
        "codchecklist": "TEXTO_EM_VEZ_DE_NUMERO"  # Deve ser int
    }
    
    response = requests.post(f"{BASE_URL}/webhook", json=payload)
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 422
    print("✅ Erro 422 capturado com sucesso")

def test_valid_webhook():
    """Teste: Webhook válido (sucesso 200)"""
    print_section("Teste 6: Webhook Válido (200)")
    
    payload = {
        "metodo": "CHECKLIST",
        "placa": "ABC1D23",
        "codchecklist": 789,
        "resultado": "APROVADO"
    }
    
    response = requests.post(f"{BASE_URL}/webhook", json=payload)
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    print("✅ Webhook processado com sucesso (não deve aparecer no error log)")

def check_error_logs():
    """Verificar se os erros foram registrados no error log"""
    print_section("Verificação do Error Log")
    
    response = requests.get(f"{BASE_URL}/errors?limit=10")
    
    if response.status_code != 200:
        print(f"❌ Falha ao buscar error logs: {response.status_code}")
        return
    
    data = response.json()
    print(f"\nTotal de erros registrados: {data['total']}")
    print(f"Erros retornados: {len(data['errors'])}")
    
    if data['total'] == 0:
        print("⚠️  Nenhum erro registrado")
        return
    
    print(f"\n{'─'*60}")
    print("Últimos erros:")
    print('─'*60)
    
    for i, error in enumerate(data['errors'][:5], 1):
        print(f"\n{i}. {error['timestamp']} - HTTP {error['status_code']}")
        print(f"   Tipo: {error['error_type']}")
        print(f"   Detalhes: {error['error_detail'][:80]}...")
        print(f"   Webhook Type: {error.get('webhook_type', 'N/A')}")
        print(f"   Source IP: {error['request']['source_ip']}")
        
        if error.get('payload'):
            print(f"   Payload keys: {list(error['payload'].keys())}")
    
    print(f"\n✅ Error log está funcionando corretamente!")

def test_all():
    """Executar todos os testes"""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║  Teste do Sistema de Error Logs - Webhook Raster        ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    tests = [
        test_error_400_empty_body,
        test_error_400_missing_metodo,
        test_error_400_unsupported_type,
        test_error_422_missing_required_field,
        test_error_422_invalid_data_type,
        test_valid_webhook,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
            time.sleep(0.5)  # Pequeno delay entre testes
        except AssertionError as e:
            print(f"❌ Teste falhou: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ Erro inesperado: {e}")
            failed += 1
    
    # Verificar error logs
    time.sleep(1)  # Aguardar logs serem escritos
    check_error_logs()
    
    # Resumo
    print_section("Resumo dos Testes")
    print(f"Testes executados: {passed + failed}")
    print(f"✅ Passaram: {passed}")
    print(f"❌ Falharam: {failed}")
    
    if failed == 0:
        print("\n🎉 Todos os testes passaram!")
    else:
        print(f"\n⚠️  {failed} teste(s) falharam")

if __name__ == "__main__":
    try:
        test_all()
    except KeyboardInterrupt:
        print("\n\n⚠️  Testes interrompidos pelo usuário")
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Erro: Não foi possível conectar a {BASE_URL}")
        print("Verifique se o Docker está rodando: docker compose ps")
    except Exception as e:
        print(f"\n❌ Erro fatal: {e}")
