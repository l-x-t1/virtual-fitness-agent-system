"""
OpenTelemetry 链路追踪集成

使用方式（在 app/main.py lifespan 中调用）:
    from app.middleware.tracing import setup_tracing
    setup_tracing(app)

依赖安装:
    pip install opentelemetry-api opentelemetry-sdk
    pip install opentelemetry-instrumentation-fastapi
    pip install opentelemetry-exporter-otlp
"""

from __future__ import annotations

import logging

logger = logging.getLogger("fitness.tracing")


def setup_tracing(app, service_name: str = "fitness-api",
                  otlp_endpoint: str = "http://localhost:4317"):
    """
    初始化 OpenTelemetry，自动注入 FastAPI 仪表化

    Args:
        app: FastAPI 实例
        service_name: 服务名称（在 Jaeger/Tempo 中显示）
        otlp_endpoint: OTLP Collector gRPC 地址
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # 资源标识
        resource = Resource.create({SERVICE_NAME: service_name})

        # Tracer 提供者
        provider = TracerProvider(resource=resource)

        # OTLP 导出器
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)

        # 自动注入 FastAPI
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

        logger.info("OpenTelemetry tracing enabled (OTLP: %s)", otlp_endpoint)
    except ImportError:
        logger.info("OpenTelemetry not installed; skipping tracing setup")
    except Exception as exc:
        logger.warning("OpenTelemetry setup failed (non-fatal): %s", exc)
