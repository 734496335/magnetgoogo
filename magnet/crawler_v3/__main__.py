"""Allow `python -m magnet.crawler_v3 ...`."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
