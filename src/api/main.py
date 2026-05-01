"""FastAPI application entry point for the Contract Risk Analyzer.

Mounts all routers, configures CORS, and sets up the OpenAPI metadata
that makes the Swagger UI look professional in a portfolio context.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.analyze import router as analyze_router
from src.graph.graph import get_compiled_graph
from src.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Compile the LangGraph once at startup and store on app.state.

    This avoids recompiling the graph on every request — compilation is
    expensive (imports, DynamoDB checkpointer init, etc.).
    """
    logger.info(
        "api_starting",
        version="1.0.0",
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
    app.state.graph = get_compiled_graph()
    logger.info("graph_warmed_up")
    yield
    logger.info("api_shutdown")


app = FastAPI(
    title="Contract Risk Analyzer",
    description=(
        "Multi-agent contract analysis system powered by LangGraph + GPT-4o. "
        "Upload a PDF contract and receive a structured risk report with "
        "severity classifications, clause references, and recommendations."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    contact={
        "name": "Contract Risk Analyzer",
        "url": "https://github.com/your-user/agentic-contract-analyzer",
    },
    license_info={"name": "MIT"},
)

# ── CORS ───────────────────────────────────────────────────────────────────
# Restrict in production; wide-open here for local dev convenience.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(analyze_router, tags=["Analysis"])
