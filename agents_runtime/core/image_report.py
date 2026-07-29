"""Visual report generator (Phase F4d.9).

Renders tabular data as PNG images formatted for WhatsApp preview.
Used by the orchestrator when the bot returns Drive listings, RAG
chunks, or any other structured result that benefits from a more
visual presentation than plain ASCII tables.

The styling follows the Coherence identity: off-white background,
jade accent for headers, light borders. Designed for the 1024px
preview width WhatsApp uses for image previews.

Dependencies:
- pillow >= 11.0 (declared in requirements.txt)

Failure modes:
- If Pillow is not installed, render_table_png() raises ImportError.
- The orchestrator wraps calls in try/except so the chat reply falls
  back to plain text rendering when image generation fails.
"""
from __future__ import annotations

import io
import logging
from typing import Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


_COHERENCE_JADE = (26, 107, 82)
_COHERENCE_AMBER = (184, 150, 42)
_COHERENCE_GRAPHITE = (44, 44, 40)
_COHERENCE_OFFWHITE = (250, 250, 247)
_COHERENCE_ROW_LIGHT = (244, 244, 240)
_COHERENCE_ROW_DARK = (255, 255, 255)
_COHERENCE_BORDER = (217, 217, 210)


def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
    )


def _wrap_text(draw, text: str, font, max_width: int) -> List[str]:
    """Wrap a single string into multiple lines that fit ``max_width``."""
    if not text:
        return [""]
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _load_default_font(size: int):
    """Try to load a sane DejaVu font; fall back to the Pillow default."""
    try:
        from PIL import ImageFont

        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size=size
        )
    except (OSError, IOError):
        try:
            from PIL import ImageFont

            return ImageFont.truetype("DejaVuSans.ttf", size=size)
        except (OSError, IOError):
            from PIL import ImageFont

            return ImageFont.load_default()


def _measure_lines(
    draw, lines: Sequence[str], font, max_width: int
) -> List[str]:
    wrapped: List[str] = []
    for line in lines:
        wrapped.extend(_wrap_text(draw, line, font, max_width))
    return wrapped


def render_table_png(
    title: str,
    rows: Iterable[Tuple[str, ...]],
    *,
    headers: Optional[Sequence[str]] = None,
    emoji_header: str = "",
    footer: str = "",
    accent: str = "#1A6B52",
    max_width_px: int = 1024,
    row_height_px: int = 56,
    padding_px: int = 24,
    title_size: int = 28,
    body_size: int = 18,
    return_format: str = "bytes",
) -> bytes:
    """Render a simple table as a PNG image.

    Args:
        title: bold title text at the top of the image.
        rows: iterable of row tuples. Each tuple length should match
            ``headers``. If ``headers`` is None the first row of
            ``rows`` is treated as the header.
        headers: explicit column headers. If provided, ``rows`` must
            contain only data (no header row).
        emoji_header: optional emoji to prepend to the title.
        footer: optional caption rendered at the bottom (e.g. source).
        accent: hex color for the title bar and column dividers.
        max_width_px: image width in pixels (default 1024 matches
            WhatsApp's preview width).
        row_height_px: target row height; auto-grows for wrapped text.
        padding_px: outer margin.
        title_size: font size for the title.
        body_size: font size for table cells.
        return_format: ``"bytes"`` returns PNG bytes; ``"pil"`` returns
            the PIL.Image so callers can further inspect it.

    Returns:
        PNG bytes (or a PIL.Image when ``return_format='pil'``).

    Raises:
        ImportError: if Pillow is not installed.
        ValueError: if the data shape is invalid.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise ImportError(
            "Pillow is required for render_table_png. "
            "Install with `pip install pillow==11.0.0`."
        ) from exc

    rows_list: List[Tuple[str, ...]] = [tuple(str(c) for c in r) for r in rows]
    if not rows_list and not headers:
        raise ValueError("render_table_png requires at least headers or one row")

    if headers is not None:
        headers = tuple(str(h) for h in headers)
    else:
        headers = rows_list[0]
        rows_list = rows_list[1:]

    if rows_list and any(len(r) != len(headers) for r in rows_list):
        raise ValueError(
            f"row width mismatch: header has {len(headers)} cols, "
            f"row has {len(rows_list[0])} cols"
        )

    accent_rgb = _hex_to_rgb(accent) if isinstance(accent, str) else accent
    body_font = _load_default_font(body_size)
    title_font = _load_default_font(title_size)
    bold_font = _load_default_font(body_size + 2)

    col_count = len(headers)
    body_max_width = (max_width_px - 2 * padding_px) // max(col_count, 1) - 16

    placeholder = Image.new("RGB", (max_width_px, 64), _COHERENCE_OFFWHITE)
    draw = ImageDraw.Draw(placeholder)

    wrapped_rows: List[List[str]] = []
    for row in rows_list:
        wrapped_cells: List[str] = []
        for cell in row:
            wrapped_cells.extend(_wrap_text(draw, str(cell), body_font, body_max_width))
        wrapped_rows.append(wrapped_cells)

    wrapped_headers: List[str] = []
    for h in headers:
        wrapped_headers.extend(_wrap_text(draw, str(h), bold_font, body_max_width))

    row_heights = [max(row_height_px, 16 + 22 * len(r)) for r in wrapped_rows]
    header_height = max(row_height_px, 16 + 22 * len(wrapped_headers))
    footer_height = 0
    if footer:
        footer_lines = _wrap_text(draw, footer, body_font, max_width_px - 2 * padding_px)
        footer_height = 16 + 22 * len(footer_lines)

    title_lines = _wrap_text(draw, f"{emoji_header} {title}".strip(), title_font, max_width_px - 2 * padding_px)
    title_height = 16 + 32 * len(title_lines)

    total_height = (
        padding_px + title_height + padding_px + header_height
        + sum(row_heights) + padding_px + footer_height + padding_px
    )

    img = Image.new("RGB", (max_width_px, total_height), _COHERENCE_OFFWHITE)
    draw = ImageDraw.Draw(img)

    y = padding_px
    for line in title_lines:
        draw.text((padding_px, y), line, fill=_COHERENCE_GRAPHITE, font=title_font)
        y += 32
    y += padding_px // 2
    draw.rectangle(
        (padding_px // 2, padding_px // 2, max_width_px - padding_px // 2, total_height - padding_px // 2),
        outline=accent_rgb,
        width=2,
    )

    y = padding_px + title_height + padding_px // 2
    header_y = y
    col_w = (max_width_px - 2 * padding_px) // col_count
    for i in range(col_count):
        x = padding_px + i * col_w + 8
        cell_lines = _wrap_text(draw, headers[i], bold_font, col_w - 16)
        for j, line in enumerate(cell_lines):
            draw.text((x, y + j * 22), line, fill=accent_rgb, font=bold_font)
    y += header_height

    for idx, row in enumerate(rows_list):
        bg = _COHERENCE_ROW_LIGHT if idx % 2 == 0 else _COHERENCE_ROW_DARK
        row_h = row_heights[idx]
        draw.rectangle(
            (padding_px // 2, y, max_width_px - padding_px // 2, y + row_h),
            fill=bg,
        )
        for i, cell in enumerate(row):
            x = padding_px + i * col_w + 8
            wrapped = _wrap_text(draw, str(cell), body_font, col_w - 16)
            for j, line in enumerate(wrapped):
                draw.text((x, y + 8 + j * 22), line, fill=_COHERENCE_GRAPHITE, font=body_font)
        for i in range(col_count + 1):
            x_line = padding_px + i * col_w
            draw.line(
                (x_line, y, x_line, y + row_h),
                fill=_COHERENCE_BORDER,
                width=1,
            )
        y += row_h

    if footer:
        y += padding_px // 2
        footer_lines = _wrap_text(draw, footer, body_font, max_width_px - 2 * padding_px)
        for line in footer_lines:
            draw.text(
                (padding_px, y),
                line,
                fill=_COHERENCE_AMBER,
                font=body_font,
            )
            y += 22

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    png_bytes = buf.getvalue()
    if return_format == "pil":
        return img  # type: ignore[return-value]
    return png_bytes


__all__ = ["render_table_png"]