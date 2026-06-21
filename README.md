# Moku

Backend and research scaffold for ranking language-learning sentences with:

- a weighted BM25 candidate retriever over Wiki40B sentences
- a scheduling score that penalizes early reviews and unrequested new words
- a two-step `best out of 25` retrieval strategy

## Project Layout

```text
apps/backend/        FastAPI service, Alembic migrations, repositories, CLI
packages/moku-core/  Text processing, corpus loaders, BM25, recommendation logic
notebooks/           Research artifacts only
```

## Backend Setup

Run everything through Docker Compose:

```powershell
docker compose run --rm migrate
docker compose run --rm backend moku-backend import-corpus --source sample --language en
docker compose up -d backend
```

Or run the backend locally against Compose Postgres:

```powershell
uv sync --all-packages --group dev --extra notebooks
docker compose up -d postgres
cd apps/backend
uv run alembic upgrade head
cd ../..
uv run moku-backend import-corpus --source sample --language en
```

The `migrate` service runs Alembic and creates the database tables. The import
command expects those tables to exist.

Set `MOKU_POSTGRES_PORT` or `MOKU_BACKEND_PORT` in `.env` to expose services on
different host ports. For host-run backend commands, `MOKU_DATABASE_URL` can use
`${MOKU_POSTGRES_PORT}` so it stays in sync. Docker Compose injects
`.env.docker` into backend containers so they use the internal Postgres service
address instead.

Run the API:

```powershell
uv run uvicorn moku_backend.main:app --app-dir apps/backend/src --reload
```

Then request recommendations:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/v1/recommendations?top_k=5"
```

If you changed `MOKU_BACKEND_PORT`, use that port in the request URL instead.

## Tests

```powershell
uv run ruff check .
uv run pytest packages\moku-core\tests apps\backend\tests
```

The Postgres integration test is skipped unless `MOKU_TEST_DATABASE_URL` is set.

## Anki Import

With Anki running and the AnkiConnect add-on enabled, import a deck into the
default learner schedule with:

```powershell
uv run moku-backend import-anki --deck "Japanese" --word-field "Expression" --language en
```

The deck query includes subdecks. The importer replaces only the target
learner/language, stores suspended and new cards as non-scheduled learner cards,
and skips cards where the required field is missing or empty. Set
`MOKU_ANKI_CONNECT_URL` or `MOKU_ANKI_CONNECT_API_KEY` when your local
AnkiConnect configuration differs from the defaults.

## Notebook Setup

```powershell
uv sync
uv run python -m ipykernel install --user --name moku --display-name "Python (moku)"
uv run jupyter lab notebooks/sentence_retrieval_experiment.ipynb
```

The notebook attempts to stream `google/wiki40b` from Hugging Face. If the dataset is
unavailable or the machine is offline, it falls back to a small built-in sample corpus so
the metric code can still be exercised.

## Corpus Options

Wiki40B is the default:

```powershell
uv run jupyter lab notebooks/sentence_retrieval_experiment.ipynb
```

OpenSubtitles2024 can be selected through environment variables:

```powershell
$env:MOKU_CORPUS_SOURCE="opensubtitles2024"
$env:MOKU_LANGUAGE="en"
$env:MOKU_OPENSUBTITLES_SPLIT="validation"
uv run jupyter lab notebooks/sentence_retrieval_experiment.ipynb
```

When no OpenSubtitles language pairs are configured, the loader uses all pair
directories in the selected split whose left or right side matches `MOKU_LANGUAGE`.
Set `MOKU_OPENSUBTITLES_LANGUAGE_PAIRS` only when you want to restrict the import,
for example:

```powershell
$env:MOKU_OPENSUBTITLES_LANGUAGE_PAIRS="en-es"
```

`Helsinki-NLP/OpenSubtitles2024` is gated on Hugging Face and currently includes a
Hub loading script (`opensubtitles2024.py`). Modern `datasets` versions no longer
support remote loading scripts for datasets, so the OpenSubtitles loader will fall
back to the built-in sample corpus until the dataset author publishes the data in
a standard format such as Parquet. Accept the dataset terms in your Hugging Face
account first:

https://huggingface.co/datasets/Helsinki-NLP/OpenSubtitles2024

Then authenticate the local environment with either:

```powershell
uv run huggingface-cli login
```

or:

```powershell
$env:HF_TOKEN="hf_your_token_here"
```

After logging in or setting `HF_TOKEN`, restart the notebook kernel and rerun the
corpus-loading cells.
