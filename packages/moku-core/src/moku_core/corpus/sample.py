"""Small explicit sample corpus for tests and local development."""

from __future__ import annotations

from collections.abc import Iterator

from moku_core.corpus.types import CorpusLoadConfig, CorpusSentence
from moku_core.corpus.utils import sentence_record

# ruff: noqa: E501

SAMPLE_SENTENCES = (
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
)


def iter_sample_sentences(config: CorpusLoadConfig) -> Iterator[CorpusSentence]:
    sentences = SAMPLE_SENTENCES
    if config.max_sentences is not None:
        sentences = sentences[: config.max_sentences]

    for index, text in enumerate(sentences):
        yield sentence_record(
            text=text,
            source="sample",
            language=config.language,
            metadata={"sample_index": index},
        )
