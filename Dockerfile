FROM python:3.12-slim

WORKDIR /app

# Dépendances en premier pour profiter du cache Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source (hors tests, debug scripts, venv)
COPY brvm_scraper/ ./brvm_scraper/
COPY server.py snapshot.py ./

# Répertoire de données persistant (base SQLite montée en volume)
RUN mkdir -p /data

# Variables par défaut — toutes surchargeables via docker-compose ou -e
ENV MCP_TRANSPORT=streamable-http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV BRVM_DB=/data/brvm_history.db

EXPOSE 8000

# Vérification TCP simple : le port répond-il ?
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import socket; s=socket.create_connection(('localhost', 8000), timeout=3); s.close()"

CMD ["python", "server.py"]
