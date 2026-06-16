from __future__ import annotations

import json
import math
import os
import re
import textwrap
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd
from datasets import load_dataset
from tqdm.auto import tqdm


pd.set_option("display.max_colwidth", 160)

RNG = np.random.default_rng(42)
TODAY = pd.Timestamp.today().normalize()

#CORPUS_SOURCE = os.getenv("MOKU_CORPUS_SOURCE", "wiki40b")
CORPUS_SOURCE = os.getenv("MOKU_CORPUS_SOURCE", "opensubtitles")
LANGUAGE = os.getenv("MOKU_LANGUAGE", "zh_CN")
WIKI40B_DATASET_NAME = "google/wiki40b"
WIKI40B_SPLIT = "train"
OPENSUBTITLES_DATASET_NAME = "Helsinki-NLP/OpenSubtitles2024"
OPENSUBTITLES_SPLIT = os.getenv("MOKU_OPENSUBTITLES_SPLIT", "dev")
OPENSUBTITLES_LANGUAGE_PAIRS = os.getenv("MOKU_OPENSUBTITLES_LANGUAGE_PAIRS", "en-zh_CN")

MAX_ARTICLES = int(os.getenv("MOKU_MAX_ARTICLES", "1000_000"))
MAX_SENTENCES = int(os.getenv("MOKU_MAX_SENTENCES", "10"))
TOP_K_ALLOWED_WORDS = int(os.getenv("MOKU_TOP_K_ALLOWED_WORDS", "280000"))
MIN_SENTENCE_TOKENS = int(os.getenv("MOKU_MIN_SENTENCE_TOKENS", "6"))
MAX_SENTENCE_TOKENS = int(os.getenv("MOKU_MAX_SENTENCE_TOKENS", "32"))

BM25_TOP_K = 25
DUE_QUERY_HORIZON_DAYS = 14
URGENCY_DECAY = 0.22
## Text utilities

HAN_CHAR_CLASS = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
HAN_RUN_RE = re.compile(f"[{HAN_CHAR_CLASS}]+")
TOKEN_RE = re.compile(
    f"[{HAN_CHAR_CLASS}]+|[^\\W\\d_{HAN_CHAR_CLASS}]+(?:['-][^\\W\\d_{HAN_CHAR_CLASS}]+)?",
    re.UNICODE,
)
CONTENT_TOKEN_RE = re.compile(f"[{HAN_CHAR_CLASS}]|[^\\W_]", re.UNICODE)
SUBTITLE_OVERRIDE_RE = re.compile(r"\{\\[^}]*\}")
SUBTITLE_ESCAPE_RE = re.compile(r"\\[A-Za-z]+")
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'({\[]?[A-Z0-9])")
seg = None

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from", "had",
    "has", "have", "he", "her", "his", "in", "is", "it", "its", "of", "on", "or", "she",
    "that", "the", "their", "there", "they", "this", "to", "was", "were", "which", "with",
}

STOPWORDS = {
}


def is_chinese_language(language: str) -> bool:
    return language.lower().replace("-", "_").startswith("zh")


def chinese_segmenter():
    global seg
    if seg is None:
        import pkuseg

        seg = pkuseg.pkuseg()
    return seg


def clean_corpus_text(text: str) -> str:
    text = SUBTITLE_OVERRIDE_RE.sub(" ", text)
    text = SUBTITLE_ESCAPE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str, language: str = LANGUAGE) -> list[str]:
    text = clean_corpus_text(text)
    if is_chinese_language(language):
        return [token.lower() for token in chinese_segmenter().cut(text) if token.strip()]
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]


def content_tokens(text: str, language: str = LANGUAGE) -> list[str]:
    tokens = []
    for token in tokenize(text, language=language):
        if token not in STOPWORDS and CONTENT_TOKEN_RE.search(token):
            tokens.append(token)
    return tokens


from joblib import Parallel, delayed

seg = None

def chinese_segmenter():
    global seg
    if seg is None:
        import pkuseg
        seg = pkuseg.pkuseg()
    return seg

def content_tokens(text, language):
    text = clean_corpus_text(text)
    tokens = []
    if is_chinese_language(language):
        toks = [
            token.lower()
            for token in chinese_segmenter().cut(text)
            if token.strip()
        ]
    else:
        toks = [m.group(0).lower() for m in TOKEN_RE.finditer(text)]

    for token in toks:
        if token not in STOPWORDS and CONTENT_TOKEN_RE.search(token):
            tokens.append(token)

    return tokens


def clean_wiki40b_text(text: str) -> str:
    # Remove standalone section headings like:
    # _START_SECTION_ Death _END_SECTION_
    text = re.sub(
        r"_START_[A-Z]+_\s*[^.!?_\n]{1,80}\s*_END_[A-Z]+_",
        " ",
        text
    )

    # Remove remaining Wiki40B markers
    text = re.sub(r"_(?:START|END)_[A-Z]+_", " ", text)
    text = text.replace("_NEWLINE_", " ")

    return clean_corpus_text(text)


def split_sentences(text: str) -> list[str]:
    text = clean_corpus_text(text)
    if not text:
        return []
    return [sentence.strip() for sentence in SENTENCE_BOUNDARY_RE.split(text) if sentence.strip()]


def acceptable_sentence(sentence: str, language: str = LANGUAGE) -> bool:
    tokens = tokenize(sentence, language=language)
    return MIN_SENTENCE_TOKENS <= len(tokens) <= MAX_SENTENCE_TOKENS

content_tokens("-看着点 -朱莉娅 - Watch it!", "zh")
## Load a sentence corpus

FALLBACK_SENTENCES = [
    "The city council approved a new plan to protect the river during the summer festival.",
    "Several researchers compared the results with earlier measurements from the coastal station.",
    "The museum opened a public archive containing letters, maps, and photographs from the expedition.",
    "A small group of volunteers repaired the bridge after heavy rain damaged the old wooden supports.",
    "The committee delayed the final decision until every member had reviewed the financial report.",
    "Students in the language program practiced short conversations before reading the article aloud.",
    "The railway company introduced a faster service between the capital and the northern port.",
    "Local farmers adopted new irrigation methods to reduce water use during dry months.",
    "The author described the village as a quiet place surrounded by forests and narrow roads.",
    "Engineers tested the software carefully before releasing the update to hospitals and schools.",
    "The historic building survived the fire because workers had restored the stone walls.",
    "During the interview, the minister explained how the policy would affect regional transport.",
    "The team collected soil samples from the valley and recorded the temperature every morning.",
    "A traditional song became popular again after it was performed at the national theater.",
    "The court rejected the appeal because the evidence did not support the original claim.",
    "Scientists discovered that the island population had changed rapidly after the storm.",
    "The newspaper published a detailed timeline of the negotiations between the two governments.",
    "The library expanded its digital collection so readers could access rare books from home.",
    "A photographer documented the construction of the harbor over several winter seasons.",
    "The teacher selected sentences that repeated useful words without introducing too much vocabulary.",
    "The athlete returned to training after doctors confirmed that the injury had healed completely.",
    "The company reduced the price of the device after competitors released similar models.",
    "Archaeologists found decorated pottery near the entrance of an ancient settlement.",
    "The report noted that public demand for renewable energy had increased across the region.",
    "Visitors followed a narrow path through the garden and stopped beside the central fountain.",
    "The program recommends review material based on memory strength and the date of the last lesson.",
    "Several witnesses remembered the event differently, but all agreed that the meeting was brief.",
    "The singer recorded the album in a studio built inside a former railway warehouse.",
    "The village market sells fresh bread, fruit, and handmade tools every Saturday morning.",
    "Researchers warned that introducing too many new terms could slow progress for beginning learners.",
    "The national park protects mountain lakes, rare plants, and animals that live above the tree line.",
    "The translation preserved the meaning of the speech but changed several idiomatic expressions.",
    "The pilot adjusted the route when strong winds moved across the western coast.",
    "The database stores each word with its last review date, next due date, and current interval.",
    "A sentence is useful when it contains due words and avoids unnecessary unfamiliar vocabulary.",
]


def load_wiki40b_sentences(
    language: str = LANGUAGE,
    max_articles: int = MAX_ARTICLES,
    max_sentences: int = MAX_SENTENCES,
) -> pd.DataFrame:
    sentences: list[str] = []
    source = "wiki40b"

    try:
        dataset = load_dataset(WIKI40B_DATASET_NAME, language, split=WIKI40B_SPLIT, streaming=True)
        iterator = dataset.take(max_articles)
        for row in tqdm(iterator, total=max_articles, desc="Streaming Wiki40B"):
            text = clean_wiki40b_text(row.get("text", ""))
            for sentence in split_sentences(text):
                if acceptable_sentence(sentence, language=language):
                    sentences.append(sentence)
                if len(sentences) >= max_sentences:
                    break
            if len(sentences) >= max_sentences:
                break
    except Exception as exc:
        print(f"Could not load Wiki40B ({type(exc).__name__}: {exc}). Using fallback corpus.")
        sentences = FALLBACK_SENTENCES
        source = "fallback"

    frame = pd.DataFrame({"sentence": sentences})
    frame["source"] = source
    frame["tokens"] = frame["sentence"].map(lambda sentence: tokenize(sentence, language=language))
    frame["content_tokens"] = frame["sentence"].map(lambda sentence: content_tokens(sentence, language=language))
    frame["length"] = frame["tokens"].map(len)
    return frame.drop_duplicates("sentence").reset_index(drop=True)


def is_hf_auth_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "gated dataset",
            "must be authenticated",
            "401",
            "403",
            "unauthorized",
            "access to dataset",
            "please log in",
        )
    )


def is_hf_loading_script_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "loading script",
            "dataset scripts are no longer supported",
            "standard format like parquet",
        )
    )


def print_hf_loading_script_help(dataset_name: str) -> None:
    print(
        f"{dataset_name} is currently published with a Hugging Face loading script. "
        "Modern datasets versions no longer support remote loading scripts for datasets; "
        "ask the dataset author to convert it to a standard data format such as Parquet."
    )


def print_hf_auth_help(dataset_name: str) -> None:
    print(
        f"{dataset_name} requires Hugging Face authentication. "
        "Accept the dataset terms on the Hub, then authenticate this environment with one of:\n"
        "  uv run huggingface-cli login\n"
        "  $env:HF_TOKEN='hf_...'\n"
        "After setting credentials, restart the notebook kernel and rerun the corpus-loading cells."
    )


def _language_pairs_arg(language_pairs: str) -> list[str]:
    return [pair.strip() for pair in language_pairs.split(",") if pair.strip()]


def load_opensubtitles2024_sentences(
    language: str = LANGUAGE,
    split: str = OPENSUBTITLES_SPLIT,
    language_pairs: str = OPENSUBTITLES_LANGUAGE_PAIRS,
    max_segments: int = MAX_ARTICLES,
    max_sentences: int = MAX_SENTENCES,
) -> pd.DataFrame:
    sentences: list[str] = []
    source = "opensubtitles2024"
    segments_seen = 0
    stop_reason = "dataset exhausted"

    pairs = _language_pairs_arg(language_pairs)

    if not pairs:
        pairs = [f"{language}-en" if language != "en" else "en-es"]

    data_files = {
        split: [
            f"hf://datasets/{OPENSUBTITLES_DATASET_NAME}/{split}/{pair}/{pair}.parquet"
            for pair in pairs
        ]
    }

    load_kwargs = {
        "path": "parquet",
        "data_files": data_files,
        "split": split,
        "streaming": True,
    }

    try:
        dataset = load_dataset(**load_kwargs)
        iterator = dataset.take(max_segments)
        for segments_seen, row in enumerate(tqdm(iterator, total=max_segments, desc="Streaming OpenSubtitles2024"), start=1):
            texts = []
            if row.get("src_lang") == language:
                texts.append(row.get("src_text", ""))
            if row.get("tgt_lang") == language:
                texts.append(row.get("tgt_text", ""))

            for text in texts:
                for sentence in split_sentences(text):
                    if acceptable_sentence(sentence, language=language):
                        sentences.append(sentence)
                    if len(sentences) >= max_sentences:
                        stop_reason = f"sentence cap reached ({max_sentences:,})"
                        break
                if len(sentences) >= max_sentences:
                    break
            if len(sentences) >= max_sentences:
                break
        else:
            if segments_seen >= max_segments:
                stop_reason = f"segment cap reached ({max_segments:,})"
        print(f"Loaded {len(sentences):,} sentences from {segments_seen:,} aligned segments; {stop_reason}.")
    except Exception as exc:
        if is_hf_loading_script_error(exc):
            print_hf_loading_script_help(OPENSUBTITLES_DATASET_NAME)
        elif is_hf_auth_error(exc):
            print_hf_auth_help(OPENSUBTITLES_DATASET_NAME)
        print(f"Could not load OpenSubtitles2024 ({type(exc).__name__}: {exc}). Using fallback corpus.")
        sentences = FALLBACK_SENTENCES
        source = "fallback"

    frame = pd.DataFrame({"sentence": sentences})
    frame["source"] = source
    frame["tokens"] = frame["sentence"].map(lambda sentence: tokenize(sentence, language=language))

    frame["content_tokens"] = Parallel(
        n_jobs=32,
        #backend="loky",  # process-based
    )(
        delayed(content_tokens)(sentence, language)
        for sentence in frame["sentence"]
    )

    #frame["content_tokens"] = frame["sentence"].map(lambda sentence: content_tokens(sentence, language=language))
    frame["length"] = frame["tokens"].map(len)
    return frame.drop_duplicates("sentence").reset_index(drop=True)


def load_sentence_corpus(source: str = CORPUS_SOURCE) -> pd.DataFrame:
    normalized_source = source.lower().strip()
    if normalized_source == "wiki40b":
        return load_wiki40b_sentences()
    if normalized_source in {"opensubtitles", "opensubtitles2024"}:
        return load_opensubtitles2024_sentences()
    raise ValueError(f"Unknown corpus source: {source!r}. Use 'wiki40b' or 'opensubtitles2024'.")


def corpus_word_counts_from_token_lists(token_lists: pd.Series) -> Counter[str]:
    counts: Counter[str] = Counter()
    for tokens in token_lists:
        counts.update(tokens)
    return counts


def top_k_vocabulary(sentences: pd.DataFrame, k: int = TOP_K_ALLOWED_WORDS) -> set[str]:
    if k <= 0:
        return set()
    counts = corpus_word_counts_from_token_lists(sentences["content_tokens"])
    return {word for word, _count in counts.most_common(k)}


def filter_sentences_by_top_k_vocabulary(
    sentences: pd.DataFrame,
    k: int = TOP_K_ALLOWED_WORDS,
) -> tuple[pd.DataFrame, set[str]]:
    if k <= 0:
        return sentences.copy(), set()

    allowed_words = top_k_vocabulary(sentences, k=k)
    keep_mask = sentences["content_tokens"].map(lambda tokens: set(tokens).issubset(allowed_words))
    filtered = sentences.loc[keep_mask].copy().reset_index(drop=True)
    filtered["passed_top_k_filter"] = True
    return filtered, allowed_words


raw_sentences_df = load_sentence_corpus()
sentences_df, allowed_vocabulary = filter_sentences_by_top_k_vocabulary(raw_sentences_df)
print(
    f"Kept {len(sentences_df):,} of {len(raw_sentences_df):,} sentences "
    f"using top {TOP_K_ALLOWED_WORDS:,} corpus content words."
)
sentences_df.head()
