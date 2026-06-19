"""Language helpers."""


def normalize_language(language: str) -> str:
    """Return a normalized language key for matching local behavior."""
    return language.strip().lower().replace("-", "_")


def is_chinese_language(language: str) -> bool:
    """Return whether a language tag should use Chinese segmentation."""
    return normalize_language(language).startswith("zh")
