"""
crawler_v2 — Scrapling-powered crawler (parallel to crawler/).

继承 v1 模块，仅替换网络层：
  - HTTP 抓取：Fetcher (TLS 指纹伪装 Chrome) 替代 requests
  - 浏览器降级：StealthyFetcher (反指纹 Patchright) 替代 Selenium

V1 接口/返回结构完全保持兼容，可与 v1 并行运行做对比。
"""

from .extractor import MagnetExtractorV2
from .healer import HealerV2

__all__ = ['MagnetExtractorV2', 'HealerV2']
