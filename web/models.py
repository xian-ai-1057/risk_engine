"""Pydantic response models for the web API.

The /api/analyze payload is the engine's own result dict (large, dynamic), so
it is returned pass-through rather than re-modelled here. These models cover
the small, stable responses and give FastAPI's OpenAPI docs useful shapes.
"""
from pydantic import BaseModel


class IndustriesResponse(BaseModel):
    """GET /api/industries."""

    industries: list[str]


class HealthResponse(BaseModel):
    """GET /api/health — resource availability snapshot for the UI."""

    status: str
    resource_dir: str
    has_xlsx: bool
    has_risk_prompt: bool
    has_narrative_prompt: bool


class ErrorResponse(BaseModel):
    """Uniform error body (mirrors FastAPI's default ``{"detail": ...}``)."""

    detail: str
