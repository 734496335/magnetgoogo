#!/usr/bin/env python3
"""
主流程入口（适合定时任务 / CI）：默认开启无头模式，不等待交互式验证码。
本地需要浏览器过盾时，请使用 `python main.py` 并勿设置 NEBULA_HEADLESS。
"""
import os

os.environ.setdefault("NEBULA_HEADLESS", "1")

if __name__ == "__main__":
    from main import main

    main()
