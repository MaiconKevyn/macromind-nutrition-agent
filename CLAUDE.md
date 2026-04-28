# CLAUDE.md

Guia operacional do repositório `macromind-nutrition-agent`.

## Como rodar

```bash
uv sync
uv run pytest
uv run python -m src.bot.main
```

## Pontos importantes

- O bot aceita áudio e texto.
- Texto pode começar com o tipo da refeição na primeira linha.
- O lookup nutricional usa Open Food Facts direto.
- `DATABASE_URL` vazio cai para SQLite local em `data/macromind.db`.
- `DATABASE_URL` preenchido aponta para Postgres/Supabase.

## Arquivos centrais

- `src/bot/main.py`
- `src/bot/handlers/commands.py`
- `src/bot/handlers/text.py`
- `src/bot/handlers/voice.py`
- `src/agent/graph.py`
- `src/nutrition/repository.py`
- `src/db/repository.py`

## Validação

```bash
uv run ruff check src tests
uv run mypy src/
uv run pytest
```
