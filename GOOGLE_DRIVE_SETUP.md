# Configuração Google Drive Integration

Este documento descreve como configurar a integração com Google Drive para salvar automaticamente os documentos base64 recebidos via webhooks.

## Arquitetura

Quando um webhook `PESQUISACONCULTA` é recebido:
1. O base64 é salvo no banco de dados (campo `payload`)
2. O documento é automaticamente enviado para o Google Drive
3. O `drive_file_id` e `drive_file_url` são salvos no banco
4. A resposta da API inclui os links do Drive

## Passos de Configuração

### 1. Criar Projeto no Google Cloud Platform

1. Acesse https://console.cloud.google.com/
2. Crie um novo projeto ou selecione um existente
3. No menu lateral, vá em **APIs & Services** → **Library**
4. Busque por "Google Drive API" e clique em **Enable**

### 2. Criar Service Account

1. Vá em **IAM & Admin** → **Service Accounts**
2. Clique em **Create Service Account**
3. Preencha:
   - **Name**: `webhook-raster-drive`
   - **Description**: `Service account para upload automático de documentos`
4. Clique em **Create and Continue**
5. Não é necessário adicionar roles nesta etapa (clique em **Continue**)
6. Clique em **Done**

### 3. Baixar Credenciais JSON

1. Na lista de Service Accounts, clique na conta recém-criada
2. Vá na aba **Keys**
3. Clique em **Add Key** → **Create new key**
4. Selecione o tipo **JSON**
5. Clique em **Create** (o arquivo será baixado automaticamente)
6. **Renomeie** o arquivo para `credentials.json`
7. **Mova** o arquivo para a raiz do projeto Webhook-Raster

### 4. Criar Pasta no Google Drive

1. Acesse https://drive.google.com/
2. Crie uma nova pasta (ex: "Webhook Documents" ou "Documentos Raster")
3. Abra a pasta e copie o **ID da pasta** da URL:
   ```
   https://drive.google.com/drive/folders/1AbC2DeF3GhI4JkL5MnO6PqR
                                          ^^^^^^^^^^^^^^^^^^^^^^^^
                                          Este é o FOLDER_ID
   ```

### 5. Compartilhar Pasta com Service Account

1. Clique com o botão direito na pasta criada
2. Selecione **Share** (Compartilhar)
3. No campo de email, cole o **email do Service Account**
   - O email está no arquivo `credentials.json` no campo `client_email`
   - Formato: `webhook-raster-drive@seu-projeto.iam.gserviceaccount.com`
4. Altere a permissão para **Editor**
5. Desmarque a opção **Notify people** (não precisa enviar email)
6. Clique em **Share**

### 6. Configurar Variáveis de Ambiente

Adicione ao arquivo `.env` na raiz do projeto:

```env
# Google Drive Configuration
GOOGLE_DRIVE_FOLDER_ID=1AbC2DeF3GhI4JkL5MnO6PqR
GOOGLE_CREDENTIALS_FILE=credentials.json
```

**Importante**: Substitua o `GOOGLE_DRIVE_FOLDER_ID` pelo ID copiado no passo 4.

### 7. Executar Migração SQL

Execute a migração para adicionar as colunas `drive_file_id` e `drive_file_url`:

```bash
# Opção 1: Executar dentro do container
docker exec -it webhook-raster-db-1 psql -U postgres -d webhook_db -f /app/migrations/add_drive_fields.sql

# Opção 2: Via docker compose (se o volume estiver mapeado)
docker compose exec db psql -U postgres -d webhook_db < migrations/add_drive_fields.sql

# Opção 3: Conectar manualmente e executar
docker exec -it webhook-raster-db-1 psql -U postgres -d webhook_db

# Dentro do psql, copie e cole o conteúdo de migrations/add_drive_fields.sql
```

Verifique se as colunas foram criadas:

```sql
\d webhook_events
```

Você deve ver as colunas:
- `drive_file_id` (character varying(255))
- `drive_file_url` (text)

### 8. Rebuild e Restart Docker

```bash
# Para aplicar as novas dependências (google-api-python-client, google-auth)
docker compose down
docker compose build
docker compose up -d
```

### 9. Verificar Logs

```bash
docker compose logs -f app
```

Procure por mensagens como:
- `Serviço Google Drive inicializado com sucesso`
- `Iniciando upload: CPF - VALIDADE (DD-MM-YYYY).jpg`
- `Upload concluído: ... - ID: 1XyZ...`

## Testando a Integração

### Enviar Webhook de Teste

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_type": "PESQUISACONCULTA",
    "id": "test-123",
    "identification": "12345678900",
    "expiration_date": "2025-06-01",
    "situation": "REGULAR",
    "base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
  }'
```

### Verificar Resposta

A resposta deve incluir:

```json
{
  "status": "success",
  "drive_file_id": "1XyZaBcDeFgHiJkLmNoPqRsTuVwXyZ",
  "drive_file_url": "https://drive.google.com/file/d/1XyZaBcDeFgHiJkLmNoPqRsTuVwXyZ/view"
}
```

### Verificar Google Drive

1. Acesse a pasta criada no Drive
2. Você deve ver o arquivo com o nome formatado:
   ```
   12345678900 - VALIDADE (01-06-2025).png
   ```

### Verificar Banco de Dados

```sql
SELECT 
    id,
    webhook_type,
    payload->>'identification' as cpf,
    drive_file_id,
    drive_file_url,
    received_at
FROM webhook_events
WHERE webhook_type = 'PESQUISACONCULTA'
ORDER BY received_at DESC
LIMIT 5;
```

## Formato dos Nomes de Arquivo

Os documentos são salvos com o seguinte padrão:

```
{identification} - VALIDADE ({DD-MM-YYYY}).{extensão}
```

**Exemplos:**
- `12345678900 - VALIDADE (01-06-2025).jpg`
- `98765432100 - VALIDADE (15-12-2025).pdf`
- `12345678000190 - VALIDADE (30-11-2026).png`

## Tipos de Arquivo Suportados

O sistema detecta automaticamente o tipo MIME do base64:
- **JPEG/JPG** (image/jpeg)
- **PNG** (image/png)
- **PDF** (application/pdf)
- **GIF** (image/gif)
- **BMP** (image/bmp)

## Comportamento em Caso de Falha

Se o upload para o Drive falhar:
- O webhook **continua sendo processado** normalmente
- Os campos `drive_file_id` e `drive_file_url` ficam como `NULL`
- Um log de erro é registrado
- A API retorna os campos como `null` na resposta

Isso garante que problemas temporários com o Google Drive não impeçam o recebimento de webhooks.

## Troubleshooting

### Erro: "Arquivo de credenciais não encontrado"

- Verifique se `credentials.json` está na raiz do projeto
- Verifique a variável `GOOGLE_CREDENTIALS_FILE` no `.env`
- Reinicie o container: `docker compose restart app`

### Erro: "Permission denied" ou "Insufficient Permission"

- Verifique se a pasta foi compartilhada com o email do Service Account
- Verifique se a permissão é **Editor** (não apenas Viewer)
- Aguarde alguns minutos após compartilhar

### Erro: "The parents field includes a non-existent ID"

- Verifique se o `GOOGLE_DRIVE_FOLDER_ID` está correto no `.env`
- O ID deve ser copiado da URL da pasta aberta no Drive

### Upload não acontece, mas webhook é salvo

- Verifique se o payload contém o campo `base64`
- Verifique se os campos `identification` e `expiration_date` estão presentes
- Consulte os logs: `docker compose logs app | grep "Drive"`

### Erros de autenticação

- Verifique se a Google Drive API está habilitada no projeto
- Verifique se o JSON das credenciais está válido (formato correto)
- Tente gerar novas credenciais (new key) no Service Account

## Segurança

- O arquivo `credentials.json` contém chaves privadas - **NUNCA** faça commit dele
- Adicione ao `.gitignore`:
  ```
  credentials.json
  ```
- Use variáveis de ambiente para configuração
- Em produção, considere usar Google Secret Manager

## API Endpoints Relacionados

### Listar Dados de CPFs (com links do Drive)

```bash
GET /cpfsdados
```

Resposta inclui `drive_file_id` e `drive_file_url` para cada consulta:

```json
[
  {
    "cpf": "12345678900",
    "consultas": [
      {
        "pesquisa_id": "abc-123",
        "drive_file_id": "1XyZ...",
        "drive_file_url": "https://drive.google.com/...",
        "expiration_date": "2025-06-01"
      }
    ]
  }
]
```

## Manutenção

### Limpar Arquivos Antigos

O Google Drive retention pode ser configurado manualmente na pasta ou via script personalizado usando o `google_drive.py`:

```python
from google_drive import delete_document

# Deletar arquivo específico
delete_document("FILE_ID_HERE")
```

### Verificar Quota

- Service Accounts têm quota compartilhada com o projeto GCP
- Verifique em: https://console.cloud.google.com/apis/api/drive.googleapis.com/quotas

