"""Utilities to format vector search results into prompt-ready context."""

from __future__ import annotations

from typing import Iterable, List

from app.services.rag.vector_client import VectorSearchResult


def format_rag_context(results: Iterable[VectorSearchResult]) -> str:
    """Return a human-readable context block for the language model."""

    formatted_sections: List[str] = []

    for index, result in enumerate(results, start=1):
        metadata = result.metadata or {}

        project_name = _first_non_empty(
            metadata.get("project_name"),
            metadata.get("name"),
            metadata.get("title"),
            metadata.get("property_name"),
            f"Proyecto {index}",
        )

        location = _combine_values(metadata.get("location"), metadata.get("city"))
        property_type = metadata.get("property_type") or metadata.get("type")
        status = metadata.get("status") or metadata.get("state")
        price = metadata.get("price") or metadata.get("starting_price")
        units = metadata.get("units") or metadata.get("available_units")

        description = (result.content or metadata.get("description") or "").strip()

        lines = [f"Nombre: {project_name}"]
        if location:
            lines.append(f"Ubicación: {location}")
        if property_type:
            lines.append(f"Tipo: {property_type}")
        if status:
            lines.append(f"Estado: {status}")
        if price:
            lines.append(f"Precio / desde: {price}")
        if units:
            lines.append(f"Unidades disponibles: {units}")
        if description:
            lines.append(f"Descripción: {description}")
        lines.append(f"Score de similitud: {result.score:.3f}")

        formatted_sections.append("\n".join(lines))

    if not formatted_sections:
        return ""

    return "\n\n".join(f"Proyecto #{idx}\n{block}" for idx, block in enumerate(formatted_sections, start=1))


def _first_non_empty(*values: str | None) -> str:
    for value in values:
        if value:
            text = str(value).strip()
            if text:
                return text
    return ""


def _combine_values(*values: str | None) -> str:
    parts = []
    for value in values:
        if value:
            text = str(value).strip()
            if text and text not in parts:
                parts.append(text)
    return ", ".join(parts)


__all__ = ["format_rag_context"]
