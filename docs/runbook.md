# Runbook

## Operação básica

1. Suba o bot com `uv run python -m src.bot.main`.
2. Verifique o healthcheck em `GET /health` na porta configurada por `HEALTHCHECK_PORT`.
3. Confirme geração de áudios em `data/audio/` e relatórios em `data/reports/`.

## Incidentes comuns

1. `401/403` no Telegram ou LLM: revisar `.env` e secrets de deploy.
2. Erros de banco SQLite: validar permissão de escrita em `data/`.
3. Falhas no relatório semanal: confirmar se o processo principal iniciou o scheduler.

## Rollback manual

1. Reimplantar a imagem anterior.
2. Preservar o volume com `data/`.
3. Validar `/health` e enviar um áudio de teste.
