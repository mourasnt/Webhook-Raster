FROM python:3.11-slim

# Evitar prompts interativos
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Criar usuário não-root
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

# Instalar dependências primeiro (cache de layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY config.py dependencies.py security.py middleware.py main.py models.py utils.py lgpd.py audit.py db.py db_models.py db_repository.py google_drive.py ./

# Criar diretório de logs com permissões adequadas
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

# Trocar para usuário não-root
USER appuser

EXPOSE 8000

# Health check interno
HEALTHCHECK --interval=3600s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
