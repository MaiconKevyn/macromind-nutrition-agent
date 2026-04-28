# MacroMind — Agente Nutricional via Telegram

> Documento de planejamento técnico, avaliação da proposta e checkpoints de implementação.

---

## 1. Avaliação da Proposta

### 1.1 Resumo do produto

Um agente conversacional que:
1. Recebe **mensagens de áudio** no Telegram descrevendo refeições (ex.: *"comi 200g de arroz, 150g de frango grelhado e uma maçã"*).
2. Transcreve o áudio (Speech-to-Text).
3. Extrai itens alimentares e quantidades via LLM.
4. Calcula macros (kcal, proteína, carboidrato, gordura, fibra) consultando uma base nutricional.
5. Persiste o registro do dia.
6. Gera **relatórios semanais** (consumo médio, aderência a metas, tendências).

### 1.2 Pontos fortes

- **Escopo claro e enxuto**: 1 input (áudio), 1 output (resumo + relatório). Bom para um MVP.
- **Telegram como interface** elimina a necessidade de UI mobile/web — alta velocidade até o primeiro valor entregue.
- **Voz reduz fricção**: registrar refeições por texto é o motivo nº1 do abandono de apps de tracking nutricional. Voz é o vetor certo.
- **Caso de uso pessoal**: single-tenant simplifica auth, LGPD, multi-tenancy, billing.

### 1.3 Riscos e desafios (a endereçar nos checkpoints)

| Risco | Impacto | Mitigação |
|---|---|---|
| **Estimativa imprecisa de quantidades** ("um prato", "uma porção") | Macros errados → relatório inútil | Pedir confirmação quando confiança < threshold; manter histórico de "porções padrão" do usuário |
| **Pratos compostos** ("estrogonofe", "feijoada") | LLM precisa decompor em ingredientes | Cache de receitas frequentes; LLM-as-judge para validar decomposição |
| **Cobertura da base nutricional** (TACO tem ~600 itens; USDA tem ~400k) | Itens não encontrados → fallback para estimativa LLM (menos confiável) | Hierarquia: TACO → USDA → Open Food Facts → estimativa LLM com flag de baixa confiança |
| **Latência da pipeline** (áudio → STT → LLM → DB → resposta) | UX ruim se > 10s | Streaming de resposta; processar STT e extração em paralelo onde possível |
| **Custo** (Whisper API + GPT-4) | ~$0.05–0.15 por refeição em escala | Para uso pessoal (~5 refeições/dia) é desprezível (~$15/mês). Para escalar, considerar Whisper local |
| **Drift do agente sem avaliação** | Erros silenciosos acumulam | Eval set desde o checkpoint 3; logging estruturado de cada decisão |
| **Áudio em PT-BR com gírias e termos regionais** | Erros de transcrição | Whisper-large-v3 tem boa cobertura PT-BR; manter dicionário de correções comuns |

### 1.4 Decisões de escopo (recomendações)

- **MVP single-user**: você é o único usuário inicialmente. Adia auth, multi-tenancy.
- **Português brasileiro como idioma único** no MVP.
- **Sem app/UI**: tudo via Telegram (comandos `/daily`, `/weekly`, `/meta`).
- **Persistência mínima**: SQLite no MVP, migração para Postgres se/quando virar serviço.
- **Sem treinamento de modelo próprio**: usar APIs comerciais. Voltar a isso só se custo virar problema.

---

## 2. Stack de Tecnologias

### 2.1 Linguagem e gerenciamento

| Componente | Escolha | Justificativa |
|---|---|---|
| Linguagem | **Python 3.11+** | Ecossistema de IA/LLM dominante; tipagem moderna |
| Gerenciador de pacotes | **uv** | 10–100× mais rápido que pip/poetry; lockfile reproduzível |
| Lint/format | **ruff** | Substitui flake8+isort+black; rápido |
| Type check | **mypy** (strict no `src/`) | Detecta bugs antes do runtime |
| Testes | **pytest** + **pytest-asyncio** | Padrão de facto |

### 2.2 Bot e ingestão

| Componente | Escolha | Alternativas | Justificativa |
|---|---|---|---|
| Cliente Telegram | **python-telegram-bot v21+** (async) | aiogram, telethon | Maturidade, docs excelentes, suporta long-polling e webhook |
| Ingestão | Long-polling no MVP | Webhook + FastAPI | Long-polling não exige IP público; trivial para rodar local/VPS |

### 2.3 Speech-to-Text (STT)

| Opção | Custo | Latência | Qualidade PT-BR | Quando usar |
|---|---|---|---|---|
| **OpenAI Whisper API** (`whisper-1`) | $0.006/min | ~2–5s | Excelente | **MVP** |
| `faster-whisper` local (large-v3) | $0 (GPU) ou CPU lento | 1–10s | Excelente | Quando custo importar / GPU disponível |
| Google Speech-to-Text | $0.016/min | ~1s | Boa | Se já usar GCP |
| Deepgram Nova-2 | $0.0043/min | <1s | Boa, melhorando | Se latência for crítica |

**Decisão MVP**: Whisper API. Migrar para `faster-whisper` em ckpt 8 se custo justificar.

### 2.4 LLM e orquestração de agente

| Componente | Escolha | Justificativa |
|---|---|---|
| LLM principal | **Claude Sonnet 4.6** ou **GPT-4.1 mini** | Sonnet 4.6 tem ótima extração estruturada PT-BR; GPT-4.1 mini é mais barato. Decidir após eval inicial |
| Orquestração | **LangGraph** | Você já tem familiaridade pelo projeto anterior; bom para fluxos com nós condicionais e re-tentativas |
| Saídas estruturadas | **Pydantic v2** | Validação + serialização; integra com tool-calling |
| Prompt management | Arquivos `.md` versionados em `src/agent/prompts/` | Diff-friendly, sem dependência externa |

### 2.5 Base de dados nutricional

**Hierarquia de fontes**:

1. **TACO 4ª edição** (Tabela Brasileira de Composição de Alimentos) — ~600 itens, refeições brasileiras. Disponível em CSV livre.
2. **USDA FoodData Central** — ~400k itens, API gratuita. Boa para itens internacionais e marcas.
3. **Open Food Facts** — produtos industrializados com código de barras. API gratuita.
4. **Fallback LLM** — última instância com flag `confidence: low`.

Carregar TACO + USDA em SQLite local com índice FTS5 para busca textual rápida.

### 2.6 Persistência

| Componente | Escolha | Justificativa |
|---|---|---|
| DB | **Supabase free tier** (Postgres gerenciado) | Zero ops, dashboard web, backup automático (7 dias), SQL real para relatórios, free para uso pessoal |
| ORM | **SQLAlchemy 2.0** (typed) + asyncpg | Compatível com Supabase Postgres |
| Migrations | **Alembic** | Padrão SQLAlchemy |

### 2.7 Agendamento de relatórios

| Opção | Quando usar |
|---|---|
| **APScheduler** in-process | MVP — roda dentro do mesmo processo do bot |
| **Cron + script standalone** | Se separar serviços |
| **Celery beat + Redis** | Apenas se tiver muitos jobs concorrentes (não é o caso) |

### 2.8 Observabilidade

| Camada | Ferramenta |
|---|---|
| Logging | `structlog` (JSON estruturado) |
| Tracing de LLM | **Langfuse** (self-hostável, free tier) ou LangSmith |
| Métricas | Prometheus + Grafana (apenas se virar serviço) |
| Erros | Sentry (free tier) |

### 2.9 Deploy

| Componente | Escolha |
|---|---|
| Containerização | **Docker** + `docker-compose` (dev local) |
| Hospedagem | **Fly.io free tier** — 3 VMs compartilhadas, deploy com `fly deploy` |
| Secrets | `.env` local + `flyctl secrets set` em prod |
| CI | **GitHub Actions** (lint + test + build image) |

---

## 3. Arquitetura

```
┌────────────┐   audio    ┌──────────────┐
│  Telegram  │ ─────────► │  Bot (aiogram│
│   client   │            │  /python-tg) │
└────────────┘            └──────┬───────┘
                                 │ ogg/opus
                                 ▼
                          ┌──────────────┐
                          │  STT Service │ ── Whisper API
                          └──────┬───────┘
                                 │ texto PT-BR
                                 ▼
                    ┌────────────────────────┐
                    │  LangGraph Agent       │
                    │ ┌────────────────────┐ │
                    │ │ extract_meal_items │ │ ── LLM (structured output)
                    │ └─────────┬──────────┘ │
                    │           ▼            │
                    │ ┌────────────────────┐ │
                    │ │ resolve_nutrition  │ │ ── TACO/USDA/OFF lookup
                    │ └─────────┬──────────┘ │
                    │           ▼            │
                    │ ┌────────────────────┐ │
                    │ │ confirm_if_unsure  │ │ ── condicional
                    │ └─────────┬──────────┘ │
                    │           ▼            │
                    │ ┌────────────────────┐ │
                    │ │ persist_meal       │ │
                    │ └────────────────────┘ │
                    └───────────┬────────────┘
                                ▼
                          ┌──────────────┐
                          │   SQLite     │
                          └──────┬───────┘
                                 │
                ┌────────────────┴─────────────────┐
                ▼                                  ▼
        ┌──────────────┐                  ┌──────────────┐
        │ Daily summary│                  │ Weekly report│
        │ (reply imed.)│                  │ (APScheduler)│
        └──────────────┘                  └──────────────┘
```

### 3.1 Estrutura de diretórios proposta

```
macromind-nutrition-agent/
├── pyproject.toml
├── uv.lock
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── ROADMAP.md                  ← este arquivo
├── README.md
├── src/
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── main.py             # entry point
│   │   ├── handlers/
│   │   │   ├── voice.py
│   │   │   ├── commands.py     # /daily, /weekly, /meta
│   │   │   └── corrections.py  # callbacks de confirmação
│   │   └── keyboards.py
│   ├── stt/
│   │   ├── __init__.py
│   │   ├── base.py             # interface STTProvider
│   │   └── whisper.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── graph.py            # LangGraph
│   │   ├── nodes.py
│   │   ├── state.py
│   │   ├── schemas.py          # Pydantic
│   │   └── prompts/
│   │       ├── extract_meal.md
│   │       └── decompose_dish.md
│   ├── nutrition/
│   │   ├── __init__.py
│   │   ├── repository.py       # interface
│   │   ├── taco.py
│   │   ├── usda.py
│   │   ├── openfoodfacts.py
│   │   └── matcher.py          # fuzzy match nome→item
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations/         # alembic
│   ├── reports/
│   │   ├── __init__.py
│   │   ├── daily.py
│   │   ├── weekly.py
│   │   └── formatters.py       # markdown/charts
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── jobs.py
│   └── core/
│       ├── config.py           # pydantic-settings
│       ├── logging.py
│       └── exceptions.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── eval/
│   ├── datasets/
│   │   └── meals_ptbr.jsonl    # áudios + ground truth
│   ├── run_eval.py
│   └── metrics.py
├── data/
│   ├── taco.csv
│   └── nutrition.db            # SQLite com TACO+USDA pré-indexado
└── scripts/
    ├── load_taco.py
    ├── load_usda.py
    └── seed_user.py
```

### 3.2 Modelo de dados (SQLAlchemy)

```python
# Esboço — detalhes no checkpoint 5
User(id, telegram_id, name, daily_goals_json, created_at)
Meal(id, user_id, raw_audio_path, transcription, occurred_at, status, confidence)
MealItem(id, meal_id, food_name, quantity_g, food_id_taco, food_id_usda,
         kcal, protein_g, carb_g, fat_g, fiber_g, source, confidence)
Food(id, source, source_id, name, name_normalized, kcal_per_100g,
     protein_g, carb_g, fat_g, fiber_g, micros_json)
Correction(id, user_id, original_text, corrected_food_id, created_at)
DailyGoal(user_id, kcal, protein_g, carb_g, fat_g, fiber_g, valid_from)
```

---

## 4. Checkpoints de Implementação

> Cada checkpoint termina com **critério de aceite** verificável. Use `git tag ckpt-N` ao concluir.

---

### ✅ Checkpoint 0 — Fundação do projeto

**Objetivo**: estrutura mínima rodando, lint/test/CI verdes.

**Tarefas**:
1. `uv init` + `pyproject.toml` com Python 3.11.
2. Criar estrutura de diretórios da seção 3.1 (vazia).
3. Configurar `ruff`, `mypy`, `pytest` em `pyproject.toml`.
4. `.env.example` com: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DATABASE_URL`, `LOG_LEVEL`.
5. `src/core/config.py` com `pydantic-settings`.
6. `src/core/logging.py` com `structlog`.
7. `Dockerfile` multi-stage e `docker-compose.yml`.
8. `.github/workflows/ci.yml`: ruff + mypy + pytest.
9. `pre-commit` hooks (ruff format/check).
10. `README.md` com setup local em < 5 comandos.

**Critério de aceite**:
- [ ] `uv sync && uv run pytest` passa (com 1 teste smoke).
- [ ] `uv run ruff check .` e `uv run mypy src/` sem erros.
- [ ] `docker compose build` sucesso.
- [ ] CI verde no primeiro PR.

---

### ✅ Checkpoint 1 — Bot Telegram esqueleto

**Objetivo**: bot recebe `/start` e mensagens de voz, baixa o arquivo, responde com placeholder.

**Tarefas**:
1. Criar bot via @BotFather, salvar token no `.env`.
2. `src/bot/main.py`: app `python-telegram-bot` com long-polling.
3. Handler `/start` → mensagem de boas-vindas + comandos disponíveis.
4. Handler de `voice` e `audio` → baixa o `.ogg`, salva em `data/audio/{user_id}/{message_id}.ogg`, responde "🎙️ Áudio recebido (X.Y MB), processando…".
5. Handler de erro global com logging estruturado.
6. Allowlist de `telegram_id` (só você usa) — config em `.env`.

**Critério de aceite**:
- [ ] Enviar áudio no Telegram → arquivo aparece em `data/audio/`.
- [ ] Outro usuário enviando áudio recebe "não autorizado".
- [ ] Logs em JSON com `correlation_id` por mensagem.

---

### ✅ Checkpoint 2 — Speech-to-Text

**Objetivo**: transcrever áudio em PT-BR e responder no chat.

**Tarefas**:
1. `src/stt/base.py`: `class STTProvider(Protocol): async def transcribe(audio_path) -> Transcription`.
2. `src/stt/whisper.py`: implementação OpenAI Whisper API (`language="pt"`, `prompt="contexto: descrição de refeição em português"`).
3. Integrar no handler de voz: download → STT → reply com `"📝 Transcrição: {text}"`.
4. Tratar áudios > 25 MB (limite Whisper API) com erro amigável.
5. Métricas: tempo de STT, custo estimado por chamada.

**Critério de aceite**:
- [ ] Áudio de 30s → transcrição em < 10s.
- [ ] Acurácia subjetiva ≥ 95% em 10 áudios de teste seus.
- [ ] Teste de integração com áudio mockado em `tests/fixtures/`.

---

### ✅ Checkpoint 3 — Agente: extração de itens da refeição

**Objetivo**: dado um texto, retornar lista estruturada `[{food, quantity, unit}]`.

**Tarefas**:
1. `src/agent/schemas.py`:
   ```python
   class MealItem(BaseModel):
       food: str
       quantity: float
       unit: Literal["g", "ml", "unidade", "colher_sopa", "xicara", "porcao"]
       confidence: float  # 0-1
       raw_phrase: str    # trecho original da transcrição
   class ExtractedMeal(BaseModel):
       items: list[MealItem]
       meal_type: Literal["cafe", "almoco", "jantar", "lanche"] | None
       notes: str | None
   ```
2. `src/agent/prompts/extract_meal.md`: prompt com few-shot PT-BR.
3. `src/agent/nodes.py::extract_meal_items`: chama LLM com `response_format=ExtractedMeal`.
4. **Eval set inicial**: `eval/datasets/meals_ptbr.jsonl` com ≥ 30 exemplos:
   - Refeições simples ("200g de arroz e 150g de frango")
   - Quantidades vagas ("um prato de macarrão", "um copo de suco")
   - Pratos compostos ("estrogonofe com arroz")
   - Múltiplas refeições no mesmo áudio
5. `eval/run_eval.py`: roda o nó em todo o dataset, calcula F1 por item, salva relatório markdown.

**Critério de aceite**:
- [ ] F1 ≥ 0.80 no eval set para extração de food+quantity.
- [ ] LLM retorna `confidence < 0.5` em casos genuinamente ambíguos.
- [ ] Custo médio por extração < $0.005.

---

### ✅ Checkpoint 4 — Base nutricional + matching

**Objetivo**: dado `{food: "arroz branco cozido", quantity: 200, unit: "g"}`, retornar macros.

**Tarefas**:
1. `scripts/load_taco.py`: baixa TACO 4ª ed., normaliza, popula `Food` no SQLite.
2. `scripts/load_usda.py`: baixa subset USDA (Foundation + SR Legacy), popula.
3. Índice FTS5 no SQLite sobre `name_normalized`.
4. `src/nutrition/matcher.py`:
   - normaliza query (lowercase, remove acentos, stopwords)
   - busca FTS5 + ranking por similaridade (rapidfuzz)
   - retorna top-K candidatos com score
5. `src/nutrition/repository.py::resolve_nutrition(item) -> ResolvedItem`:
   - tenta TACO → USDA → OFF → fallback LLM
   - converte `unit` para gramas (tabela de conversões: 1 colher sopa arroz ≈ 25g, etc.)
   - calcula macros proporcionais
6. **Eval set de matching**: 50 nomes de comida → ID esperado.

**Critério de aceite**:
- [ ] Top-1 accuracy ≥ 0.85 no eval de matching.
- [ ] Conversões de unidades testadas (g, ml, unidade, colher, xícara, porção).
- [ ] Fallback LLM marca `source="llm_estimate"` e `confidence=low`.

---

### ✅ Checkpoint 5 — Persistência e fluxo end-to-end

**Objetivo**: áudio → resposta com macros + registro no DB.

**Tarefas**:
1. `src/db/models.py`: tabelas da seção 3.2.
2. Alembic init + primeira migration.
3. `src/agent/graph.py`: LangGraph com nós `transcribe → extract → resolve → persist → format_reply`.
4. Handler de voz orquestra o grafo.
5. Resposta no Telegram (markdown):
   ```
   🍽️ Refeição registrada (almoço)
   ━━━━━━━━━━━━━━━━━━━━━
   • Arroz branco cozido — 200g
   • Frango grelhado — 150g
   • Maçã — 1 unidade (130g)
   ━━━━━━━━━━━━━━━━━━━━━
   📊 Total: 612 kcal
      P: 45g  C: 78g  G: 12g  Fib: 5g
   ```
6. Botões inline: `✅ Confirmar` / `✏️ Corrigir` / `🗑️ Descartar`.
7. Salvar `Correction` quando usuário corrigir.

**Critério de aceite**:
- [ ] Fluxo completo < 15s p95.
- [ ] Re-execução é idempotente (mesmo áudio não duplica).
- [ ] Correções persistidas e usadas como hint nos próximos prompts (RAG simples).

---

### ✅ Checkpoint 6 — Comandos de consulta

**Objetivo**: usuário consulta consumo a qualquer momento.

**Tarefas**:
1. `/daily [data]` — resumo do dia (default: hoje), com % das metas.
2. `/meta` — define metas: `/meta kcal=2200 p=160 c=220 g=70`.
3. `/historico [n]` — últimos N dias em formato compacto.
4. `/desfazer` — remove última refeição.
5. Formatador comum em `src/reports/formatters.py`.

**Critério de aceite**:
- [ ] Comandos respondem em < 1s.
- [ ] Metas persistidas em `DailyGoal` com versionamento (valid_from).
- [ ] Testes de integração para cada comando.

---

### ✅ Checkpoint 7 — Relatórios semanais

**Objetivo**: relatório automático todo domingo + comando `/weekly`.

**Tarefas**:
1. `src/reports/weekly.py`:
   - médias diárias (kcal, P/C/G, fibra)
   - aderência às metas (% dias dentro de ±10%)
   - top 10 alimentos da semana
   - tendência vs semana anterior (↑/↓)
   - dias com registros incompletos (alerta)
2. Gerar gráficos com `matplotlib` → enviar como imagem no Telegram (kcal/dia, distribuição P/C/G).
3. `src/scheduler/jobs.py` com APScheduler: cron `0 20 * * SUN` → envia para todos usuários ativos.
4. Comando `/weekly [n]` para gerar on-demand (semana atual ou n semanas atrás).
5. Salvar relatórios em `data/reports/` para histórico.

**Critério de aceite**:
- [ ] Relatório gerado em < 5s.
- [ ] Job rodando em produção entrega no horário.
- [ ] Gráfico legível em mobile (testar visualmente).

---

### ✅ Checkpoint 8 — Avaliação contínua e qualidade

**Objetivo**: ter sinal sobre quando o agente regrediu.

**Tarefas**:
1. Expandir eval set para 100+ exemplos cobrindo edge cases.
2. **LLM-as-judge** para avaliar plausibilidade da extração (escala 1–5).
3. Métricas no relatório:
   - F1 extração
   - Top-1 matching
   - Taxa de fallback LLM
   - MAE de macros estimados (vs ground truth manual em 20 refeições)
4. `eval/run_eval.py` rodando no CI em PRs que tocam `src/agent/` ou `src/nutrition/`.
5. Logging com **Langfuse** (auto-hospedado via docker-compose) — cada interação fica rastreável.
6. Dashboard de custos por dia.

**Critério de aceite**:
- [ ] CI quebra se F1 cair > 5pp do baseline.
- [ ] Langfuse mostrando 100% das chamadas LLM.
- [ ] Painel de custos diário.

---

### ✅ Checkpoint 9 — Hardening e deploy

**Objetivo**: rodar 24/7 sem babá.

**Tarefas**:
1. **Retry e circuit breaker** para chamadas externas (Whisper, LLM).
2. **Rate limiting** por usuário (proteção contra abuso/bug).
3. **Backup automático** do SQLite (cron diário → S3/Backblaze).
4. Healthcheck endpoint (HTTP em porta separada) para o orquestrador.
5. Deploy em **Fly.io** ou VPS:
   - secrets via `flyctl secrets`
   - volume persistente para SQLite + áudios
6. Sentry para erros não-tratados.
7. Documentar runbook de operação em `docs/runbook.md`.

**Critério de aceite**:
- [ ] 7 dias sem incidente em produção.
- [ ] Rollback testado (deploy + revert).
- [ ] Backup restaurado em ambiente de teste com sucesso.

---

### 🔮 Checkpoints futuros (não-MVP)

- **Multi-usuário** com onboarding via Telegram.
- **Reconhecimento de imagem** (foto do prato → estimativa).
- **Integração com balança/wearables** (Withings, Garmin).
- **Coach proativo**: agente sugere ajustes ("você está 15g abaixo da meta de proteína por 4 dias").
- **Export para CSV/Apple Health/Google Fit**.
- **Whisper local** (`faster-whisper` em GPU) para reduzir custos.
- **Fine-tune de embeddings** para matching de comidas brasileiras.

---

## 5. Boas Práticas Adotadas

### 5.1 Software Engineering

- **Camadas claras**: bot ↔ agent ↔ nutrition ↔ db sem dependências circulares.
- **Interfaces (Protocol/ABC)** para STT, LLM, Nutrition source — permite trocar implementação e mockar em teste.
- **12-factor**: config via env, logs em stdout, processos stateless (estado no DB).
- **Migrations versionadas** desde o ckpt 5.
- **Tipagem estrita** com mypy strict no `src/`.
- **Sem comentários óbvios**; docstrings só onde a intenção não é clara pelo nome.
- **Testes em pirâmide**: muito unit, alguns integration, poucos e2e.
- **PRs pequenos** alinhados a 1 checkpoint = 1 PR.

### 5.2 AI Engineering

- **Saídas estruturadas (Pydantic)** em vez de parsear texto livre — elimina classe inteira de bugs.
- **Prompts versionados em arquivos**, não em strings inline.
- **Eval-driven**: cada mudança no agente passa pelo eval set antes do merge.
- **Telemetria de cada chamada LLM** (Langfuse) — tokens, custo, latência, prompt, resposta.
- **Confiança explícita** no schema — nunca esconder incerteza do usuário.
- **Human-in-the-loop**: botões de confirmação corrigem o agente e alimentam dataset de melhoria.
- **Custo por interação como métrica de produto**, não só latência.
- **Fallback hierárquico** com flag de qualidade — degrada graciosamente.
- **Não treinar modelo próprio** até ter ≥ 10k exemplos rotulados; APIs são suficientes.

---

## 6. Cronograma sugerido (esforço solo, ~10h/semana)

| Semana | Checkpoint(s) |
|---|---|
| 1 | Ckpt 0 + Ckpt 1 |
| 2 | Ckpt 2 |
| 3–4 | Ckpt 3 (incluindo eval set) |
| 5 | Ckpt 4 |
| 6 | Ckpt 5 |
| 7 | Ckpt 6 |
| 8 | Ckpt 7 |
| 9 | Ckpt 8 |
| 10 | Ckpt 9 + deploy |

**Total**: ~10 semanas até produção.

---

## 7. Próximo passo

Comece pelo **Checkpoint 0**. Quando estiver pronto, me peça para implementar — vou seguir este roadmap como referência.
