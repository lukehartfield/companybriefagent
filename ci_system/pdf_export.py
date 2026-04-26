from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
import textwrap
from pathlib import Path
from urllib.parse import urlparse


PAGE_WIDTH = 612
PAGE_HEIGHT = 792


@dataclass
class StyledLine:
    text: str
    font: str = "F1"
    size: int = 11
    leading: int = 15
    align: str = "left"
    gap_before: int = 0
    indent: int = 0


def export_brief_pdf(
    text: str,
    output_path: str | Path,
    title: str = "Competitive Intelligence Brief",
    subtitle_lines: list[str] | None = None,
    style: str = "report",
) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    metrics = _style_metrics(style)
    global _ACTIVE_STYLE
    _ACTIVE_STYLE = metrics
    lines = _build_styled_lines(text, title=title, subtitle_lines=subtitle_lines, metrics=metrics)
    pages = _paginate_lines(lines, metrics)
    pdf_bytes = _build_pdf(pages, metrics)
    output.write_bytes(pdf_bytes)


def _build_styled_lines(
    text: str,
    title: str,
    subtitle_lines: list[str] | None = None,
    metrics: dict[str, int] | None = None,
) -> list[StyledLine]:
    metrics = metrics or _style_metrics("report")
    generated_on = datetime.now().strftime("%B %d, %Y")
    subtitle_block = subtitle_lines or [
        "Competitive Intelligence Report",
        f"Generated {generated_on}",
    ]
    lines: list[StyledLine] = [
        StyledLine(title, font="F2", size=metrics["title_font_size"], leading=metrics["title_leading"], align="center"),
    ]
    for idx, subtitle in enumerate(subtitle_block):
        lines.append(
            StyledLine(
                subtitle,
                font="F3",
                size=metrics["subtitle_font_size"],
                leading=metrics["subtitle_leading"],
                align="center",
                gap_before=4 if idx == 0 else 1,
            )
        )
    lines.append(StyledLine("", gap_before=metrics["title_gap_after"]))

    raw_lines = text.splitlines()
    if raw_lines and raw_lines[0].startswith("# "):
        raw_lines = raw_lines[1:]
        while raw_lines and not raw_lines[0].strip():
            raw_lines = raw_lines[1:]
    i = 0
    current_section = ""
    while i < len(raw_lines):
        raw = raw_lines[i].rstrip()
        stripped = raw.strip()

        if not stripped:
            lines.append(StyledLine("", gap_before=metrics["paragraph_gap"]))
            i += 1
            continue

        if _is_markdown_table_row(stripped) and i + 1 < len(raw_lines) and _is_markdown_table_separator(raw_lines[i + 1].strip()):
            i = _consume_table(raw_lines, i, lines)
            continue

        if stripped.startswith("## "):
            heading = stripped[3:].strip()
            current_section = heading
            lines.append(
                StyledLine(
                    heading,
                    font="F2",
                    size=metrics["section_font_size"],
                    leading=metrics["section_leading"],
                    gap_before=metrics["section_gap_before"],
                )
            )
            i += 1
            continue

        if stripped.startswith("# "):
            heading = stripped[2:].strip()
            current_section = heading
            lines.append(
                StyledLine(
                    heading,
                    font="F2",
                    size=metrics["section_font_size"],
                    leading=metrics["section_leading"],
                    gap_before=metrics["section_gap_before"],
                )
            )
            i += 1
            continue

        if stripped.startswith("- "):
            bullet = "- " + _clean_inline_markup(stripped[2:])
            for idx, wrapped in enumerate(_wrap_text(bullet, width=metrics["wrap_width"] - 4)):
                prefix_gap = 4 if idx == 0 else 0
                lines.append(StyledLine(wrapped, size=metrics["body_font_size"], leading=metrics["body_leading"], gap_before=prefix_gap))
            i += 1
            continue

        if _is_bold_only_line(stripped):
            subsection = _clean_inline_markup(stripped)
            lines.append(
                StyledLine(
                    subsection,
                    font="F2",
                    size=metrics["subsection_font_size"],
                    leading=metrics["subsection_leading"],
                    gap_before=8,
                )
            )
            i += 1
            continue

        if current_section.startswith("5. Recent News"):
            story_text, sources = _extract_sources(stripped)
            cleaned = _clean_inline_markup(story_text)
            for idx, wrapped in enumerate(_wrap_text(cleaned, width=metrics["wrap_width"])):
                lines.append(
                    StyledLine(
                        wrapped,
                        size=metrics["body_font_size"],
                        leading=metrics["body_leading"],
                        gap_before=metrics["paragraph_gap"] if idx == 0 else 0,
                    )
                )
            if sources:
                source_line = "Source: " + ", ".join(sources)
                for idx, wrapped in enumerate(_wrap_text(source_line, width=metrics["wrap_width"] - 6)):
                    lines.append(
                        StyledLine(
                            wrapped,
                            font="F3",
                            size=metrics["source_font_size"],
                            leading=metrics["source_leading"],
                            gap_before=2 if idx == 0 else 0,
                            indent=18,
                        )
                    )
            i += 1
            continue

        cleaned = _clean_inline_markup(stripped)
        for idx, wrapped in enumerate(_wrap_text(cleaned, width=metrics["wrap_width"])):
            lines.append(
                StyledLine(
                    wrapped,
                    size=metrics["body_font_size"],
                    leading=metrics["body_leading"],
                    gap_before=metrics["paragraph_gap"] if idx == 0 else 0,
                )
            )
        i += 1

    return lines


def _consume_table(raw_lines: list[str], start: int, lines: list[StyledLine]) -> int:
    headers = [cell.strip() for cell in raw_lines[start].strip().strip("|").split("|")]
    value_idx = 1 if len(headers) > 1 else 0
    i = start + 2
    lines.append(StyledLine("Financial Metrics", font="F2", size=12, leading=16, gap_before=6))
    while i < len(raw_lines):
        stripped = raw_lines[i].strip()
        if not _is_markdown_table_row(stripped):
            break
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 2:
            metric = _clean_inline_markup(cells[0])
            value = _clean_inline_markup(cells[value_idx])
            row_text = f"- {metric}: {value}"
            for idx, wrapped in enumerate(_wrap_text(row_text, width=WRAP_WIDTH - 4)):
                lines.append(StyledLine(wrapped, gap_before=3 if idx == 0 else 0))
        i += 1
    lines.append(StyledLine("", gap_before=4))
    return i


def _paginate_lines(lines: list[StyledLine], metrics: dict[str, int]) -> list[list[StyledLine]]:
    usable_height = PAGE_HEIGHT - metrics["top_margin"] - metrics["bottom_margin"] - 20
    pages: list[list[StyledLine]] = []
    current_page: list[StyledLine] = []
    used_height = 0

    for line in lines:
        line_height = line.leading + line.gap_before
        if current_page and used_height + line_height > usable_height:
            pages.append(current_page)
            current_page = []
            used_height = 0
        current_page.append(line)
        used_height += line_height

    if current_page:
        pages.append(current_page)
    return pages or [[StyledLine("No content available.")]]


def _build_pdf(pages: list[list[StyledLine]], metrics: dict[str, int]) -> bytes:
    objects: list[bytes] = []

    fonts = {
        1: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        2: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique >>",
    }

    pages_obj_id = len(fonts) + 1
    next_id = pages_obj_id + 1
    page_obj_ids: list[int] = []
    content_obj_ids: list[int] = []

    for _ in pages:
        page_obj_ids.append(next_id)
        next_id += 1
        content_obj_ids.append(next_id)
        next_id += 1

    catalog_obj_id = next_id

    for obj_id, payload in fonts.items():
        objects.append(_pdf_obj(obj_id, payload))

    kids = " ".join(f"{obj_id} 0 R" for obj_id in page_obj_ids)
    pages_dict = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_obj_ids)} >>".encode()
    objects.append(_pdf_obj(pages_obj_id, pages_dict))

    for page_num, (page_lines, page_obj_id, content_obj_id) in enumerate(zip(pages, page_obj_ids, content_obj_ids), start=1):
        stream = _content_stream(page_lines, page_num, len(pages), metrics)
        page_dict = (
            f"<< /Type /Page /Parent {pages_obj_id} 0 R "
            f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 1 0 R /F2 2 0 R /F3 3 0 R >> >> "
            f"/Contents {content_obj_id} 0 R >>"
        ).encode()
        objects.append(_pdf_obj(page_obj_id, page_dict))
        objects.append(_pdf_stream_obj(content_obj_id, stream))

    catalog_dict = f"<< /Type /Catalog /Pages {pages_obj_id} 0 R >>".encode()
    objects.append(_pdf_obj(catalog_obj_id, catalog_dict))

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    body = bytearray(header)
    offsets = [0]
    for obj in sorted(objects, key=lambda item: int(item.split(b" ", 1)[0])):
        offsets.append(len(body))
        body.extend(obj)
    xref_pos = len(body)
    body.extend(f"xref\n0 {len(offsets)}\n".encode())
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode())
    body.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root {catalog_obj_id} 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode()
    )
    return bytes(body)


def _content_stream(lines: list[StyledLine], page_num: int, page_count: int, metrics: dict[str, int]) -> bytes:
    chunks: list[str] = []

    if metrics["show_header_bar"]:
        chunks.extend([
            "0.13 0.22 0.38 rg",
            f"{metrics['left_margin']} {PAGE_HEIGHT - 34} {PAGE_WIDTH - metrics['left_margin'] - metrics['right_margin']} 6 re",
            "f",
        ])

        chunks.extend([
            "0.85 0.87 0.90 RG",
            "1 w",
            f"{metrics['left_margin']} {PAGE_HEIGHT - metrics['top_margin'] + 8} m",
            f"{PAGE_WIDTH - metrics['right_margin']} {PAGE_HEIGHT - metrics['top_margin'] + 8} l",
            "S",
        ])

    y = PAGE_HEIGHT - metrics["top_margin"]
    for line in lines:
        y -= line.gap_before
        x = _line_x(line)
        escaped = _escape_pdf_text(line.text)
        if metrics["show_section_box"] and line.font == "F2" and line.size == metrics["section_font_size"]:
            chunks.extend([
                "0.90 0.93 0.97 rg",
                f"{metrics['left_margin'] - 8} {y - 4} {metrics['content_width'] + 16} {line.leading + 6} re",
                "f",
            ])
        chunks.extend([
            "BT",
            *_set_fill_color(line),
            f"/{line.font} {line.size} Tf",
            f"1 0 0 1 {x:.2f} {y:.2f} Tm",
            f"({escaped}) Tj",
            "ET",
        ])
        y -= line.leading

    # Footer page number
    footer = f"Page {page_num} of {page_count}"
    footer_x = PAGE_WIDTH / 2 - _approx_text_width(footer, metrics["footer_font_size"]) / 2
    chunks.extend([
        "0.75 0.75 0.78 RG",
        "0.5 w",
        f"{metrics['left_margin']} {metrics['bottom_margin'] - 10} m",
        f"{PAGE_WIDTH - metrics['right_margin']} {metrics['bottom_margin'] - 10} l",
        "S",
        "BT",
        f"/F3 {metrics['footer_font_size']} Tf",
        f"1 0 0 1 {footer_x:.2f} {metrics['bottom_margin'] - 24:.2f} Tm",
        f"({_escape_pdf_text(footer)}) Tj",
        "ET",
    ])

    return "\n".join(chunks).encode("latin-1", errors="replace")


def _line_x(line: StyledLine) -> float:
    if line.align == "center":
        return (PAGE_WIDTH - _approx_text_width(line.text, line.size)) / 2
    return _ACTIVE_STYLE["left_margin"] + line.indent


def _approx_text_width(text: str, size: int) -> float:
    return len(text) * size * 0.52


def _wrap_text(line: str, width: int = 88) -> list[str]:
    return textwrap.wrap(
        line,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]


def _clean_inline_markup(text: str) -> str:
    cleaned = _format_markdown_links(text)
    cleaned = cleaned.replace("**", "").replace("__", "")
    return _normalize_pdf_text(cleaned)


def _is_bold_only_line(text: str) -> bool:
    if not (text.startswith("**") and text.endswith("**")):
        return False
    inner = text[2:-2].strip()
    return bool(inner) and "**" not in inner


def _is_markdown_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|") and "|" in line[1:-1]


def _is_markdown_table_separator(line: str) -> bool:
    cleaned = line.replace("|", "").replace("-", "").replace(":", "").strip()
    return cleaned == ""


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _set_fill_color(line: StyledLine) -> list[str]:
    if line.align == "center" and line.font == "F2" and line.size == _ACTIVE_STYLE["title_font_size"]:
        return ["0.12 0.16 0.22 rg"]
    if line.align == "center":
        return ["0.38 0.43 0.50 rg"]
    if line.font == "F2" and line.size == _ACTIVE_STYLE["section_font_size"]:
        return ["0.13 0.22 0.38 rg"]
    if line.font == "F2":
        return ["0.19 0.25 0.33 rg"]
    return ["0.12 0.12 0.12 rg"]


_ACTIVE_STYLE: dict[str, int] = {}


def _style_metrics(style: str) -> dict[str, int]:
    if style == "academic":
        left_margin = 44
        right_margin = 44
        top_margin = 42
        bottom_margin = 38
        return {
            "left_margin": left_margin,
            "right_margin": right_margin,
            "top_margin": top_margin,
            "bottom_margin": bottom_margin,
            "content_width": PAGE_WIDTH - left_margin - right_margin,
            "body_font_size": 11,
            "body_leading": 12,
            "section_font_size": 13,
            "section_leading": 16,
            "subsection_font_size": 11,
            "subsection_leading": 13,
            "title_font_size": 16,
            "title_leading": 20,
            "subtitle_font_size": 10,
            "subtitle_leading": 11,
            "source_font_size": 9,
            "source_leading": 11,
            "footer_font_size": 8,
            "wrap_width": 102,
            "paragraph_gap": 2,
            "section_gap_before": 6,
            "title_gap_after": 8,
            "show_header_bar": 0,
            "show_section_box": 0,
        }

    left_margin = 54
    right_margin = 54
    top_margin = 56
    bottom_margin = 48
    return {
        "left_margin": left_margin,
        "right_margin": right_margin,
        "top_margin": top_margin,
        "bottom_margin": bottom_margin,
        "content_width": PAGE_WIDTH - left_margin - right_margin,
        "body_font_size": 11,
        "body_leading": 15,
        "section_font_size": 15,
        "section_leading": 22,
        "subsection_font_size": 12,
        "subsection_leading": 17,
        "title_font_size": 20,
        "title_leading": 26,
        "subtitle_font_size": 10,
        "subtitle_leading": 14,
        "source_font_size": 10,
        "source_leading": 13,
        "footer_font_size": 9,
        "wrap_width": 88,
        "paragraph_gap": 4,
        "section_gap_before": 10,
        "title_gap_after": 14,
        "show_header_bar": 1,
        "show_section_box": 1,
    }


def _format_markdown_links(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        url = match.group(2).strip()
        domain = _domain_label(url)
        if label.startswith("(") and label.endswith(")"):
            label = label[1:-1].strip()
        if label.lower() == domain.lower():
            return f"{label} ({domain})"
        return f"{label} [{domain}]"

    return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", replace, text)


def _extract_sources(text: str) -> tuple[str, list[str]]:
    sources: list[str] = []

    def replace(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        url = match.group(2).strip()
        domain = _domain_label(url)
        display = label
        if display.startswith("(") and display.endswith(")"):
            display = display[1:-1].strip()
        if display.lower() == domain.lower():
            source = domain
        else:
            source = f"{display} ({domain})"
        sources.append(_normalize_pdf_text(source))
        return ""

    cleaned = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", replace, text).strip()
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    return cleaned, sources


def _domain_label(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _normalize_pdf_text(text: str) -> str:
    substitutions = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "-",
        "\u2026": "...",
        "\u00a0": " ",
        "\u2248": "~",
    }
    normalized = text
    for source, target in substitutions.items():
        normalized = normalized.replace(source, target)
    return normalized.encode("latin-1", errors="replace").decode("latin-1")


def _pdf_obj(obj_id: int, payload: bytes) -> bytes:
    return f"{obj_id} 0 obj\n".encode() + payload + b"\nendobj\n"


def _pdf_stream_obj(obj_id: int, stream: bytes) -> bytes:
    header = f"{obj_id} 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode()
    return header + stream + b"\nendstream\nendobj\n"
