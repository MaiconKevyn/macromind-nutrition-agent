# MacroMind Nutrition Agent

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot%20API-2AABEE.svg)](https://core.telegram.org/bots/api)
[![Supabase](https://img.shields.io/badge/Supabase-Postgres-3ECF8E.svg)](https://supabase.com/)
[![Fly.io](https://img.shields.io/badge/Fly.io-ready-7A4BFF.svg)](https://fly.io/)

> Agente nutricional em PT-BR para Telegram. Recebe áudio ou texto, identifica refeições, consulta macros no Open Food Facts, persiste os registros e gera resumos diários e semanais.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Run Locally](#run-locally)
- [Bot Commands](#bot-commands)
- [Input Format](#input-format)
- [Persistence](#persistence)
- [Tests](#tests)
- [Docs](#docs)
- [Deploy](#deploy)

---

## Overview

**MacroMind Nutrition Agent** foi construído para registrar refeições com fricção mínima. O fluxo atual prioriza uso prático no Telegram:

1. Recebe **áudio** ou **texto** no Telegram.
2. Transcreve áudio com STT quando necessário.
3. Extrai itens alimentares e quantidades com saída estruturada.
4. Consulta nutrição no **Open Food Facts** e calcula a quantidade enviada pelo usuário proporcionalmente a 100g.
5. Persiste a refeição no banco.
6. Gera resumos diários, históricos e relatório semanal.

### Core capabilities

- **Áudio e texto** no mesmo bot
- **Tipo de refeição explícito** no texto, com suporte a `café da manhã`, `lanche`, `pré-treino`, `pós-treino`, `janta`, `almoço`, `jantar` e `ceia`
- **Open Food Facts direto** como fonte nutricional principal
- **Persistência em Postgres/Supabase** ou SQLite local
- **Comandos de consumo diário** com resumo e histórico
- **Relatório semanal** com gráfico em imagem
- **Logs estruturados** para rastrear cada etapa do pipeline
- **Projeto em evolução contínua**, com melhorias incrementais documentadas no roadmap

---

## Architecture

```text
Telegram
  ├─ áudio ──► STT ──► extração estruturada ──► Open Food Facts ──► persistência ──► resposta
  └─ texto ──► parse do tipo de refeição ─► extração estruturada ──► Open Food Facts ──► persistência ──► resposta

Comandos:
  /daily     /historico     /weekly     /meta     /desfazer
```

### Design choices

1. **Texto e áudio compartilham o mesmo pipeline** depois da normalização inicial.
2. **O tipo da refeição pode vir na primeira linha do texto** e fica salvo em `meal_type`.
3. **Não há retrieval local de nutrição no runtime**; o lookup é feito no Open Food Facts.
4. **Quantidade informada pelo usuário é respeitada** e o cálculo é sempre proporcional a 100g.
5. **Falhas parciais não derrubam a refeição inteira**; itens não encontrados são reportados separadamente.

---

## Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Runtime | Python 3.11+ | Tipagem moderna e ecossistema forte para bots e IA |
| Telegram | `python-telegram-bot` | Bot async com long-polling estável |
| STT | Groq Whisper ou OpenAI Whisper | PT-BR com boa qualidade e troca simples por configuração |
| LLM | Anthropic Claude | Extração estruturada de itens alimentares |
| Orchestration | `langgraph` | Pipeline em nós, com persistência e formatação separadas |
| Nutritional data | Open Food Facts | Fonte aberta com produtos BR e marcas |
| Persistence | SQLAlchemy + Supabase Postgres ou SQLite | SQL real no deploy e fallback local no dev |
| Scheduling | APScheduler | Relatório semanal dentro do processo do bot |
| Logging | `structlog` | Logs JSON com `correlation_id` |
| Tests | `pytest` + mocks | Verificação local sem depender de rede |
| Deploy | Docker + Fly.io | Caminho simples para bot sempre ligado |

---

## Project Structure

```text
macromind-nutrition-agent/
├── .claude/
│   └── README.md              # instruções para agentes/assistentes
├── .codex                     # notas do workspace Codex
├── CLAUDE.md                  # instruções de operação do repositório
├── ROADMAP.md                 # checkpoints e visão de evolução
├── docs/
│   └── runbook.md             # operação, incidentes e rollback
├── eval/
│   └── run_eval.py            # runner de avaliação
├── src/
│   ├── bot/                   # handlers, entrypoint e comandos
│   ├── core/                  # config, logging, health e rate limit
│   ├── db/                    # models, session e repository
│   ├── nutrition/             # Open Food Facts, matching e conversão
│   ├── reports/               # formatação e gráfico semanal
│   ├── scheduler/             # jobs agendados
│   └── stt/                   # providers de speech-to-text
├── tests/                     # integração e unitários
├── data/
│   ├── taco_br.csv            # referência histórica
│   ├── audio/                 # áudio temporário local
│   └── reports/               # gráficos semanais
├── Dockerfile
├── docker-compose.yml
├── fly.toml
├── pyproject.toml
└── .env.example
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- `uv`
- Uma conta no Telegram para o bot
- `TELEGRAM_BOT_TOKEN` e `TELEGRAM_ALLOWED_USER_ID`
- `ANTHROPIC_API_KEY`
- `GROQ_API_KEY` se `STT_PROVIDER=groq`
- `OPENAI_API_KEY` se `STT_PROVIDER=whisper`
- `DATABASE_URL` apontando para Supabase/Postgres, ou vazio para SQLite local

### Installation

```bash
git clone https://github.com/MaiconKevyn/macromind-nutrition-agent.git
cd macromind-nutrition-agent
uv sync
```

### Configuration

```bash
cp .env.example .env
```

Exemplo mínimo:

```env
TELEGRAM_BOT_TOKEN=123456:abc
TELEGRAM_ALLOWED_USER_ID=123456789
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...
STT_PROVIDER=groq
DATABASE_URL=postgresql+psycopg://user:password@host:5432/macromind
```

Se `DATABASE_URL` ficar vazio, o bot usa SQLite local em `data/macromind.db`.

### Run Locally

```bash
uv run pytest
uv run python -m src.bot.main
```

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Boas-vindas e resumo do bot |
| `/ajuda` | Repeti a ajuda |
| `/daily` | Resumo nutricional do dia atual |
| `/daily 2026-04-27` | Resumo de uma data específica |
| `/historico` | Histórico recente padrão |
| `/historico 7` | Últimos 7 dias |
| `/weekly` | Resumo semanal com gráfico |
| `/meta kcal=2200 p=160 c=220 g=70` | Define metas diárias |
| `/desfazer` | Remove a última refeição registrada |

---

## Input Format

O bot aceita texto puro ou áudio. Para texto, você pode informar o tipo da refeição na primeira linha:

```text
café da manhã
3 ovos caipira, 1 pão francês
```

```text
pré-treino
20g pasta de amendoim growth
```

Se a primeira linha for um tipo válido, o bot:
- salva o `meal_type`
- usa apenas o restante como entrada para extração
- mantém o texto original no banco para rastreabilidade

Tipos aceitos:
- `café da manhã`
- `lanche`
- `pré-treino`
- `pós-treino`
- `janta`
- `almoço`
- `jantar`
- `ceia`

---

## Persistence

As refeições ficam persistidas nas tabelas:

- `users`
- `meals`
- `meal_items`
- `daily_goals`

Comportamento importante:

- `meals` representa a refeição
- `meal_items` representa os alimentos dentro da refeição
- o resumo diário conta refeições em `meals`, não itens em `meal_items`
- o banco de produção pode ser Supabase/Postgres
- no local, o fallback é SQLite em `data/macromind.db`

---

## Tests

Rodar a suíte completa:

```bash
uv run pytest
```

Checagens estáticas:

```bash
uv run ruff check src tests
uv run mypy src/
```

No CI, o repositório executa lint, type check, tests e build de Docker.

---

## Docs

- [ROADMAP.md](ROADMAP.md) - checkpoints técnicos e evolução do produto
- [docs/runbook.md](docs/runbook.md) - operação básica, incidentes e rollback
- [CLAUDE.md](CLAUDE.md) - instruções práticas para agentes e manutenção

---

## Deploy

O caminho de deploy esperado hoje é:

1. Build em Docker.
2. Secrets configurados no provedor.
3. Banco Postgres no Supabase.
4. Bot rodando em long-polling.

Para ambiente local ou MVP, SQLite também é suportado.
