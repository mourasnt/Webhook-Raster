import uvicorn

from src.main import app

if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║  Webhook API - RasterIntegra v2.1 (Refatorado)              ║
    ║                                                                ║
    ║  Servidor rodando em: http://localhost:8000                   ║
    ║                                                                ║
    ║  Segurança:                                                   ║
    ║  ✓ Idempotência via SHA256 + Redis (TTL 24h)                 ║
    ║  ✓ Rate Limiting global (100 req/min por IP)                     ║
    ║  ✓ Proteção contra Replay (timestamp validation)                ║
    ║                                                                ║
    ║  Endpoints:                                                   ║
    ║  ✓ POST /webhook       - Receber webhooks                    ║
    ║  ✓ GET  /health        - Health check                      ║
    ╚════════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)