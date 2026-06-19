"""Shared exceptions for core logic."""


class MokuCoreError(Exception):
    """Base exception for core package errors."""


class OptionalDependencyError(MokuCoreError):
    """Raised when a requested feature needs an optional dependency."""


class CorpusLoadError(MokuCoreError):
    """Raised when a corpus source cannot be loaded."""
