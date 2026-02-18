# Sistema de Log de Erros - Webhook Raster

## Visão Geral

Sistema dedicado para registro de **TODOS os erros HTTP** (400, 422, 500, etc.) com payload completo, stack trace e contexto detalhado.

**Localização:** `logs/errors.json` (JSON Lines format)

## Estrutura do Error Log

Cada erro é salvo como uma linha JSON com a seguinte estrutura:

```json
{
  "timestamp": "2026-02-18 14:35:22",
  "status_code": 422,
  "error_type": "CLIENT_ERROR",
  "error_detail": "Dados inválidos: campo 'placa' obrigatório",
  "webhook_type": "CHECKLIST",
  "event_id": "a1b2c3d4e5f6...",
  "request": {
    "method": "POST",
    "url": "http://localhost:8000/webhook",
    "source_ip": "192.168.1.100"
  },
  "payload": {
    "metodo": "CHECKLIST",
    "codchecklist": 123
  },
  "traceback": null
}
```

### Campos do Error Log

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `timestamp` | string | Data/hora do erro (YYYY-MM-DD HH:MM:SS) |
| `status_code` | int | Código HTTP (400, 422, 500, etc.) |
| `error_type` | string | `CLIENT_ERROR` (4xx) ou `SERVER_ERROR` (5xx) |
| `error_detail` | string | Mensagem de erro detalhada |
| `webhook_type` | string | Tipo do webhook se identificado (CHECKLIST, etc.) |
| `event_id` | string | SHA256 do body para rastreabilidade |
| `request.method` | string | Método HTTP (POST, GET, etc.) |
| `request.url` | string | URL completa da requisição |
| `request.source_ip` | string | IP de origem |
| `payload` | object | **Payload completo** recebido (sanitizado LGPD) |
| `traceback` | string | Stack trace completo (apenas para erros 500) |

## Tipos de Erros Capturados

### ✅ Erros 400 (Bad Request)
- Body vazio
- Campo `metodo` ou `method` ausente
- Webhook type não suportado
- Timestamp inválido

### ✅ Erros 422 (Unprocessable Entity)
- Validação Pydantic falhou
- Campos obrigatórios ausentes
- Tipos de dados incorretos
- Valores fora do formato esperado

### ✅ Erros 500 (Internal Server Error)
- Exceções não tratadas
- Erros de banco de dados
- Falhas no Google Drive upload
- Erros de criptografia

### ✅ Erros 409 (Conflict)
- Requisição duplicada (idempotência)

### ✅ Erros 429 (Rate Limit)
- Limite de requisições excedido

## Como Visualizar os Erros

### 1. Via API Endpoint

**Endpoint:** `GET /errors`

**Parâmetros:**
- `limit` (opcional): Número máximo de erros a retornar (padrão: 50, máx: 200)

**Exemplo:**
```bash
# Últimos 50 erros
curl http://localhost:8000/errors

# Últimos 100 erros
curl http://localhost:8000/errors?limit=100

# Todos os erros (até 200)
curl http://localhost:8000/errors?limit=200
```

**Resposta:**
```json
{
  "total": 15,
  "limit": 50,
  "errors": [
    {
      "timestamp": "2026-02-18 15:30:45",
      "status_code": 422,
      "error_detail": "Dados inválidos: campo 'placa' obrigatório",
      "payload": {...}
    }
  ]
}
```

### 2. Via Arquivo Direto

**Localização:** `logs/errors.json`

```bash
# Ver últimos 10 erros
tail -n 10 logs/errors.json | jq

# Filtrar erros 500
cat logs/errors.json | jq 'select(.status_code == 500)'

# Contar erros por tipo
cat logs/errors.json | jq -r '.status_code' | sort | uniq -c

# Ver erros de hoje
cat logs/errors.json | jq 'select(.timestamp | startswith("2026-02-18"))'

# Erros de webhook específico
cat logs/errors.json | jq 'select(.webhook_type == "CHECKLIST")'
```

### 3. Via Docker Logs

```bash
# Ver logs em tempo real
docker compose logs -f app | grep "Erro"

# Buscar erro específico
docker compose logs app | grep "422"
```

## Casos de Uso

### Debugging de Erro 422 (Validação)

**Problema:** Cliente reporta erro 422 mas não sabe o que está errado

**Solução:**
```bash
# Buscar últimos erros 422
curl http://localhost:8000/errors?limit=100 | jq '.errors[] | select(.status_code == 422)'
```

**Análise:**
- Verificar `error_detail` para mensagem específica
- Inspecionar `payload` completo para ver dados enviados
- Comparar com modelo esperado (Pydantic schema)

### Debugging de Erro 500 (Server Error)

**Problema:** API retorna 500 sem detalhes

**Solução:**
```bash
# Buscar erros 500 com traceback
curl http://localhost:8000/errors | jq '.errors[] | select(.status_code == 500) | .traceback'
```

**Análise:**
- Ler `traceback` completo para identificar causa raiz
- Verificar se é erro de banco, Drive, criptografia, etc.
- Consultar `payload` para reproduzir erro

### Monitoramento de Erros Frequentes

**Objetivo:** Identificar padrões de erros

**Comandos:**
```bash
# Contar erros por código
cat logs/errors.json | jq -r '.status_code' | sort | uniq -c

# Erros mais comuns (top 5)
cat logs/errors.json | jq -r '.error_detail' | sort | uniq -c | sort -rn | head -5

# Taxa de erros por webhook type
cat logs/errors.json | jq -r '.webhook_type' | sort | uniq -c
```

### Análise de IP Suspeito

**Objetivo:** Investigar erros de IP específico

```bash
# Todos os erros de um IP
cat logs/errors.json | jq 'select(.request.source_ip == "192.168.1.100")'

# Códigos de erro por IP
cat logs/errors.json | jq -r '"\(.request.source_ip) - \(.status_code)"' | sort | uniq -c
```

## Exemplos de Erros Reais

### Exemplo 1: Campo Obrigatório Ausente (422)

```json
{
  "timestamp": "2026-02-18 14:35:22",
  "status_code": 422,
  "error_type": "CLIENT_ERROR",
  "error_detail": "Dados inválidos: field required: placa",
  "webhook_type": "CHECKLIST",
  "event_id": "e4f5a6b7c8d9...",
  "request": {
    "method": "POST",
    "url": "http://localhost:8000/webhook",
    "source_ip": "192.168.1.50"
  },
  "payload": {
    "metodo": "CHECKLIST",
    "codchecklist": 456,
    "resultado": "APROVADO"
    // ❌ Faltou o campo "placa"
  },
  "traceback": null
}
```

**Solução:** Cliente deve adicionar campo `placa` ao payload.

### Exemplo 2: Body Vazio (400)

```json
{
  "timestamp": "2026-02-18 14:40:15",
  "status_code": 400,
  "error_type": "CLIENT_ERROR",
  "error_detail": "Body obrigatório",
  "webhook_type": null,
  "event_id": null,
  "request": {
    "method": "POST",
    "url": "http://localhost:8000/webhook",
    "source_ip": "203.0.113.42"
  },
  "payload": null,
  "traceback": null
}
```

**Solução:** Cliente deve enviar JSON válido no body.

### Exemplo 3: Erro Interno no Drive Upload (500)

```json
{
  "timestamp": "2026-02-18 15:10:33",
  "status_code": 500,
  "error_type": "SERVER_ERROR",
  "error_detail": "Erro interno: The parents field includes a non-existent ID",
  "webhook_type": "PESQUISACONCULTA",
  "event_id": "a9b8c7d6e5f4...",
  "request": {
    "method": "POST",
    "url": "http://localhost:8000/webhook",
    "source_ip": "10.0.0.5"
  },
  "payload": {
    "metodo": "PESQUISACONCULTA",
    "identification": "12345678900",
    "base64": "iVBORw0KGgo..."
  },
  "traceback": "Traceback (most recent call last):\n  File \"/app/google_drive.py\", line 180, in upload_document\n    file = service.files().create(...).execute()\n  File \"googleapiclient/...\", line 135, in execute\n    raise HttpError(...)\ngoogleapiclient.errors.HttpError: <HttpError 404 when requesting ... returned \"The parents field includes a non-existent ID\"...>"
}
```

**Solução:** Verificar `GOOGLE_DRIVE_FOLDER_ID` no `.env` - ID da pasta está incorreto ou pasta foi deletada.

### Exemplo 4: Webhook Type Não Suportado (400)

```json
{
  "timestamp": "2026-02-18 16:20:00",
  "status_code": 400,
  "error_type": "CLIENT_ERROR",
  "error_detail": "Webhook type 'OUTRO_TIPO' não é suportado",
  "webhook_type": "OUTRO_TIPO",
  "event_id": "b1c2d3e4f5...",
  "request": {
    "method": "POST",
    "url": "http://localhost:8000/webhook",
    "source_ip": "172.16.0.10"
  },
  "payload": {
    "metodo": "OUTRO_TIPO",
    "dados": "..."
  },
  "traceback": null
}
```

**Solução:** Cliente deve usar tipos válidos: CHECKLIST, RESULTADOCHECKLIST, PESQUISACONCULTA.

## Manutenção do Error Log

### Rotação de Logs

O arquivo `logs/errors.json` cresce continuamente. Para manter apenas logs recentes:

**Opção 1: Backup e limpeza manual**
```bash
# Backup
cp logs/errors.json logs/errors_backup_$(date +%Y%m%d).json

# Limpar
> logs/errors.json
```

**Opção 2: Manter apenas últimas N linhas**
```bash
# Manter últimos 1000 erros
tail -n 1000 logs/errors.json > logs/errors_temp.json
mv logs/errors_temp.json logs/errors.json
```

**Opção 3: Limpar erros antigos (> 30 dias)**
```bash
# Filtrar erros dos últimos 30 dias
cat logs/errors.json | jq 'select(.timestamp >= "2026-01-19")' > logs/errors_temp.json
mv logs/errors_temp.json logs/errors.json
```

### Monitoramento via Cron

Adicionar job para alertar em caso de muitos erros:

```bash
# Crontab: verificar a cada hora
0 * * * * [ $(tail -n 100 /app/logs/errors.json | grep '"status_code": 500' | wc -l) -gt 10 ] && echo "ALERTA: Muitos erros 500" | mail -s "Webhook Errors" admin@example.com
```

## Integração com Ferramentas

### Grafana / Prometheus

Parse o arquivo `errors.json` e exponha métricas:

```python
# metrics_exporter.py
from prometheus_client import Counter, Gauge
from utils import get_error_logs

errors_total = Counter('webhook_errors_total', 'Total de erros', ['status_code', 'webhook_type'])
errors_recent = Gauge('webhook_errors_recent_1h', 'Erros na última hora', ['status_code'])

def update_metrics():
    logs = get_error_logs(limit=1000)
    for log in logs:
        errors_total.labels(
            status_code=log['status_code'],
            webhook_type=log.get('webhook_type', 'unknown')
        ).inc()
```

### ELK Stack

Enviar logs para Elasticsearch:

```bash
# Logstash pipeline
input {
  file {
    path => "/app/logs/errors.json"
    codec => "json_lines"
  }
}

filter {
  date {
    match => ["timestamp", "yyyy-MM-dd HH:mm:ss"]
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "webhook-errors-%{+YYYY.MM.dd}"
  }
}
```

### Datadog / New Relic

Custom log forwarder:

```python
import requests
from utils import get_error_logs

def send_to_datadog(error_log):
    requests.post(
        'https://http-intake.logs.datadoghq.com/v1/input',
        json={
            'ddsource': 'webhook-raster',
            'service': 'webhook-api',
            'message': error_log
        },
        headers={'DD-API-KEY': 'YOUR_API_KEY'}
    )
```

## LGPD e Privacidade

⚠️ **IMPORTANTE:** Os payloads salvos no error log são **sanitizados automaticamente** via `sanitize_payload()`:

- **Campos criptografados:** placa, CPF, senha, base64
- **Mantidos:** Estrutura do payload, IDs, timestamps
- **Segurança:** Mesmo com acesso ao error log, dados pessoais estão protegidos

**Exemplo de Payload Sanitizado:**
```json
{
  "payload": {
    "metodo": "CHECKLIST",
    "placa": "ENCRYPTED_XYZ123...",  // ✅ Criptografado
    "codchecklist": 456,              // ✅ ID público
    "resultado": "APROVADO"           // ✅ Não sensível
  }
}
```

## Troubleshooting

### Error log não está sendo criado

**Verificar:**
1. Pasta `logs/` existe e tem permissões de escrita
2. Função `save_error_log()` está sendo chamada nos exception handlers
3. Imports corretos no `main.py`

```bash
# Verificar permissões
ls -la logs/

# Criar manualmente se necessário
touch logs/errors.json
chmod 666 logs/errors.json
```

### Endpoint /errors returna lista vazia

**Verificar:**
1. Arquivo `logs/errors.json` existe
2. Arquivo não está vazio: `cat logs/errors.json`
3. Linhas são JSON válido: `cat logs/errors.json | jq` 

```bash
# Debug
docker compose exec app python -c "from utils import get_error_logs; print(get_error_logs(limit=5))"
```

### Payload não aparece no error log

**Causa:** Body do request já foi consumido antes do exception handler.

**Solução:** Middleware `IdempotencyMiddleware` já salva body no `request.state._body` (implementado).

### Erro: "FALHA ao salvar error log"

**Verificar logs do app:**
```bash
docker compose logs app | grep "FALHA ao salvar error log"
```

**Causas comuns:**
- Permissões de arquivo
- Disco cheio
- Payload muito grande (> 16MB pode causar problemas de memória)

## Boas Práticas

✅ **Revisar error log diariamente** para identificar problemas recorrentes

✅ **Configurar alertas** para erros 500 (indicam problemas no servidor)

✅ **Rotacionar logs** mensalmente para evitar arquivos muito grandes

✅ **Analisar padrões** de erros 422 para melhorar documentação da API

✅ **Monitorar IPs** com muitos erros (possível ataque ou cliente com problema)

❌ **Não compartilhar** error logs sem sanitizar dados sensíveis

❌ **Não ignorar** erros 500 - sempre investigar causa raiz

❌ **Não deletar** error logs antes de analisar (fazer backup)

## Referência Rápida

```bash
# Ver últimos erros
curl http://localhost:8000/errors | jq

# Erros 500 com traceback
cat logs/errors.json | jq 'select(.status_code == 500) | {timestamp, error: .error_detail, trace: .traceback}'

# Erros por webhook type
cat logs/errors.json | jq -r '.webhook_type' | sort | uniq -c

# Erros de hoje
cat logs/errors.json | jq "select(.timestamp | startswith(\"$(date +%Y-%m-%d)\"))"

# Limpar logs antigos (> 30 dias)
cat logs/errors.json | jq "select(.timestamp >= \"$(date -d '30 days ago' +%Y-%m-%d)\")" > logs/errors_temp.json && mv logs/errors_temp.json logs/errors.json
```

## Suporte

Para dúvidas ou problemas com o sistema de error logs:

1. Verificar este documento primeiro
2. Consultar logs do Docker: `docker compose logs app`
3. Testar endpoint `/errors` para validar funcionamento
4. Verificar permissões da pasta `logs/`

Happy debugging! 🐛🔍
