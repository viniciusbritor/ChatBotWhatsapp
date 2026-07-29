"""Image report tool (Phase F4d.9).

Wraps ``core.image_report.render_table_png`` so the orchestrator and
agents can produce tabular PNG previews for WhatsApp. The tool returns
PNG bytes plus a base64 data URI; callers can either embed it in an
HTML preview or hand it to ``evolution_client.send_image``.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


def render_report(
    title: str,
    rows: List[List[str]],
    *,
    headers: Optional[Sequence[str]] = None,
    emoji_header: str = "",
    footer: str = "",
    accent: str = "#1A6B52",
    max_width_px: int = 1024,
    max_rows: Optional[int] = None,
) -> Dict[str, Any]:
    """Render a table to PNG bytes + base64 data URI.

    Args:
        title: title text (rendered in jade accent bar).
        rows: list of rows. If ``headers`` is None the first row is
            treated as the header row.
        headers: explicit column headers (overrides the first row).
        emoji_header: emoji prepended to the title.
        footer: caption rendered at the bottom.
        accent: hex color for the title bar.
        max_width_px: image width.
        max_rows: truncate rows beyond this count to keep the image
            readable (default: from env ``IMAGE_REPORT_MAX_ROWS``
            or 12). The truncation appends a "... +N more" footer.

    Returns:
        dict with keys ``png_bytes`` (bytes), ``data_uri`` (str),
        ``mime_type``, ``truncated`` (bool), ``row_count``.
    """
    try:
        from core.image_report import render_table_png
    except ImportError as exc:
        logger.warning("render_report unavailable: %s", exc)
        return {"error": "pillow_not_installed", "detail": str(exc)}

    max_rows_env = int(os.getenv("IMAGE_REPORT_MAX_ROWS", "12"))
    if max_rows is None:
        max_rows = max_rows_env

    truncated = False
    original_count = len(rows)
    if headers is None and rows:
        data_rows = rows[1:]
        effective_headers = list(rows[0])
    else:
        data_rows = rows
        effective_headers = list(headers) if headers else None

    if len(data_rows) > max_rows:
        data_rows = data_rows[:max_rows]
        truncated = True

    if truncated:
        footer = (
            f"{footer} | ... +{original_count - max_rows} mais"
            if footer
            else f"... +{original_count - max_rows} mais"
        )

    png_bytes = render_table_png(
        title=title,
        rows=[tuple(r) for r in data_rows],
        headers=effective_headers,
        emoji_header=emoji_header,
        footer=footer,
        accent=accent,
        max_width_px=max_width_px,
    )
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return {
        "png_bytes": png_bytes,
        "data_uri": f"data:image/png;base64,{encoded}",
        "mime_type": "image/png",
        "truncated": truncated,
        "row_count": len(data_rows),
    }


__all__ = ["render_report"]