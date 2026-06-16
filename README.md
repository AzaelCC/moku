# Moku

Research scaffold for ranking language-learning sentences with:

- a weighted BM25 candidate retriever over Wiki40B sentences
- a scheduling score that penalizes early reviews and unrequested new words
- a two-step `best out of 25` retrieval strategy

## Setup

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
$env:MOKU_OPENSUBTITLES_LANGUAGE_PAIRS="en-es"
uv run jupyter lab notebooks/sentence_retrieval_experiment.ipynb
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
