"""Backward-compatible aliases for the generic movie models."""

from magnet.resource_index.domain.movie_models import (
    MovieDetail as SixVMovieDetail,
    MovieListingCandidate as SixVListingCandidate,
    MovieResource as SixVMovieResource,
)

__all__ = ["SixVListingCandidate", "SixVMovieResource", "SixVMovieDetail"]
