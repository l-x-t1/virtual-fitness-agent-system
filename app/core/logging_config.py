"""
统一日志配置 — 基于 Python logging + structlog 格式

使用方式（在 app/main.py lifespan 开始时调用）:
    from app.core.logging_config import setup_logging
    setup_logging()

输出:
  - 控制台: 彩色 structlog 格式（开发）
  - 文件: JSON 格式（生产，轮转，保留 7 天）
"""

from __future__ import annotations

import logging
import logging.config
import logging.handlers
import sys
from pathlib import Path


def setup_logging(
    level: str = "INFO",
    log_dir: str | None = None,
    json_format: bool = False,
):
    """
    配置全局日志

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_dir: 日志文件目录，为 None 则只输出到控制台
        json_format: True 输出 JSON 格式（适合 ELK/Loki 采集）
    """

    # 1. 根日志器级别
    root_level = getattr(logging, level.upper(), logging.INFO)

    # 2. 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(root_level)
    if json_format:
        console_handler.setFormatter(_JsonFormatter())
    else:
        console_handler.setFormatter(_ColorFormatter())

    # 3. 组装 root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(root_level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)

    # 4. 文件 handler（如果指定了目录）
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_path / "fitness.log",
            when="midnight",
            interval=1,
            backupCount=7,
            encoding="utf-8",
        )
        file_handler.setLevel(root_level)
        file_handler.setFormatter(_JsonFormatter())
        root_logger.addHandler(file_handler)

    # 5. 降低第三方库的日志噪音
    for noisy in ("uvicorn.access", "httpx", "httpcore", "neo4j", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # 6. 保持 uvicorn 自身日志可见
    logging.getLogger("uvicorn.error").setLevel(root_level)

    # 7. 首条日志
    logger = logging.getLogger("fitness")
    logger.info("Logging initialized (level=%s, json=%s)", level, json_format)


class _ColorFormatter(logging.Formatter):
    """开发用彩色格式"""
    COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        return (
            f"\033[90m{self.formatTime(record)}\033[0m "
            f"{color}{record.levelname:<7}{self.RESET} "
            f"\033[34m{record.name}\033[0m "
            f"{record.getMessage()}"
        )


class _JsonFormatter(logging.Formatter):
    """生产用 JSON 格式（适合 Filebeat/Promtail 采集）"""
    def format(self, record: logging.LogRecord) -> str:
        import json
        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            payload["exception"] = str(record.exc_info[1])
        return json.dumps(payload, ensure_ascii=False)
