FROM python:3.10-slim

WORKDIR /app

COPY mcp_server/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY common/ ./common/
COPY mcp_server/server.py .

# Exponemos el puerto SSE (Server Sent Events)
EXPOSE 8000

# Lanzar el servidor MCP
CMD ["python", "server.py"]