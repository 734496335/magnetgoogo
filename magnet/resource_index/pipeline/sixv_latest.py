"""Backward-compatible aliases for the shared movie latest runner."""

from magnet.resource_index.pipeline.movie_latest import (
    MovieLatestResult,
    MovieLatestRunner,
)

SixVLatestRunner = MovieLatestRunner
SixVLatestResult = MovieLatestResult

__all__ = [
    "SixVLatestRunner",
    "SixVLatestResult",
    "MovieLatestRunner",
    "MovieLatestResult",
]
