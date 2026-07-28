# -*- coding: utf-8 -*-
"""Independent movie rating crawler (Douban / IMDb / RT / Bangumi + fallbacks)."""

from magnet.rating_resolver.service import RatingResolver, self_check

__all__ = ["RatingResolver", "self_check"]
__version__ = "1.0.0"
