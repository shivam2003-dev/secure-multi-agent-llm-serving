#!/usr/bin/env python3
"""Build the AegisServe white paper from its reviewable Markdown source."""

from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "WHITEPAPER.md"
OUTPUT = ROOT / "output" / "pdf" / "aegisserve-whitepaper.pdf"

NAVY = colors.HexColor("#102A43")
BLUE = colors.HexColor("#1363DF")
TEAL = colors.HexColor("#00A6A6")
PALE = colors.HexColor("#EAF4F8")
INK = colors.HexColor("#243B53")
MUTED = colors.HexColor("#627D98")
ORANGE = colors.HexColor("#F59E0B")
WHITE = colors.white


class WhitePaperDoc(BaseDocTemplate):
    def __init__(self, filename: str) -> None:
        super().__init__(
            filename,
            pagesize=A4,
            leftMargin=19 * mm,
            rightMargin=19 * mm,
            topMargin=21 * mm,
            bottomMargin=18 * mm,
            title="AegisServe: Secure and Efficient Multi-Agent LLM Inference",
            author="Shivam Kumar",
            subject="AI systems research proposal and benchmark specification",
        )
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="main",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates([PageTemplate(id="paper", frames=[frame], onPage=_page_chrome)])


class InvariantCanvas(Canvas):
    """Produce byte-stable PDFs so CI can verify the committed artifact."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs["invariant"] = 1
        kwargs["pageCompression"] = 1
        super().__init__(*args, **kwargs)


def _page_chrome(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    if doc.page == 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, width, height, fill=1, stroke=0)
        canvas.setFillColor(TEAL)
        canvas.rect(0, height - 13 * mm, width, 13 * mm, fill=1, stroke=0)
    else:
        canvas.setStrokeColor(colors.HexColor("#D9E2EC"))
        canvas.setLineWidth(0.6)
        canvas.line(19 * mm, height - 13 * mm, width - 19 * mm, height - 13 * mm)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(NAVY)
        canvas.drawString(19 * mm, height - 9.5 * mm, "AEGISSERVE WHITE PAPER")
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(
            width - 19 * mm,
            height - 9.5 * mm,
            "SECURE MULTI-AGENT LLM SERVING",
        )
        canvas.line(19 * mm, 11 * mm, width - 19 * mm, 11 * mm)
        canvas.setFont("Helvetica", 7.2)
        canvas.drawString(19 * mm, 7 * mm, "Research proposal - no measured AegisServe results")
        canvas.drawRightString(width - 19 * mm, 7 * mm, str(doc.page))
    canvas.restoreState()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=29,
            leading=33,
            textColor=WHITE,
            alignment=TA_LEFT,
            spaceAfter=6 * mm,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=15,
            leading=21,
            textColor=colors.HexColor("#D9EAF2"),
            spaceAfter=12 * mm,
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#B8E3EA"),
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15.5,
            leading=19,
            textColor=NAVY,
            spaceBefore=5 * mm,
            spaceAfter=2.5 * mm,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=14,
            textColor=BLUE,
            spaceBefore=3.5 * mm,
            spaceAfter=1.8 * mm,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.35,
            leading=13.1,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=2.4 * mm,
            splitLongWords=True,
            allowWidows=0,
            allowOrphans=0,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.2,
            leading=13.2,
            textColor=NAVY,
            backColor=PALE,
            borderColor=TEAL,
            borderWidth=0,
            borderPadding=(9, 10, 9, 10),
            leftIndent=4,
            rightIndent=4,
            spaceAfter=4 * mm,
        ),
        "code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.8,
            leading=10.5,
            textColor=colors.HexColor("#D9E2EC"),
            backColor=NAVY,
            borderPadding=8,
            leftIndent=3,
            rightIndent=3,
            spaceBefore=1.5 * mm,
            spaceAfter=3 * mm,
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=3 * mm,
        ),
        "list": ParagraphStyle(
            "List",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=12.7,
            textColor=INK,
            leftIndent=2,
            spaceAfter=1.2 * mm,
        ),
        "reference": ParagraphStyle(
            "Reference",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.15,
            leading=10.7,
            textColor=INK,
            leftIndent=8 * mm,
            firstLineIndent=-8 * mm,
            spaceAfter=2.1 * mm,
            splitLongWords=True,
        ),
    }


def _inline(text: str) -> str:
    escaped = html.escape(text.strip())
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`(.+?)`", r'<font name="Courier">\1</font>', escaped)
    escaped = re.sub(
        r"\[([^]]+)]\((https?://[^)]+)\)",
        r'<link href="\2" color="#1363DF">\1</link>',
        escaped,
    )
    if escaped.startswith("http://") or escaped.startswith("https://"):
        escaped = f'<link href="{escaped}" color="#1363DF">{escaped}</link>'
    return escaped


def _architecture_figure() -> Drawing:
    drawing = Drawing(455, 198)
    drawing.add(
        Rect(
            0,
            0,
            455,
            198,
            rx=8,
            ry=8,
            fillColor=colors.HexColor("#F5F9FC"),
            strokeColor=colors.HexColor("#BCCCDC"),
        )
    )
    boxes = [
        (14, 128, 86, 42, "TENANTS", "agent DAGs", TEAL),
        (116, 128, 94, 42, "ADMISSION", "identity + SLO", BLUE),
        (228, 128, 104, 42, "WCF SCHEDULER", "criticality + fair", NAVY),
        (351, 128, 88, 42, "WORKERS", "prefill/decode", ORANGE),
        (116, 42, 94, 42, "RECOVERY", "replay/restore", colors.HexColor("#7C3AED")),
        (228, 42, 104, 42, "KV DOMAINS", "GPU/CPU/remote", colors.HexColor("#0F766E")),
        (351, 42, 88, 42, "EVIDENCE", "joined events", colors.HexColor("#475569")),
    ]
    for x, y, width, height, title, subtitle, color in boxes:
        drawing.add(Rect(x, y, width, height, rx=5, ry=5, fillColor=color, strokeColor=color))
        drawing.add(
            String(
                x + width / 2,
                y + 25,
                title,
                fontName="Helvetica-Bold",
                fontSize=7.4,
                fillColor=WHITE,
                textAnchor="middle",
            )
        )
        drawing.add(
            String(
                x + width / 2,
                y + 11,
                subtitle,
                fontName="Helvetica",
                fontSize=7.1,
                fillColor=WHITE,
                textAnchor="middle",
            )
        )
    for x1, y1, x2, y2 in [
        (100, 149, 116, 149),
        (210, 149, 228, 149),
        (332, 149, 351, 149),
        (395, 128, 395, 84),
        (351, 63, 332, 63),
        (280, 128, 280, 84),
        (228, 63, 210, 63),
        (163, 84, 163, 128),
    ]:
        drawing.add(Line(x1, y1, x2, y2, strokeColor=MUTED, strokeWidth=1.5))
    drawing.add(
        String(
            14,
            14,
            "Private KV reuse is allowed only inside an authenticated security domain.",
            fontName="Helvetica-Oblique",
            fontSize=7.4,
            fillColor=MUTED,
        )
    )
    return drawing


def _benchmark_table(styles: dict[str, ParagraphStyle]) -> Table:
    rows = [
        ["Mechanism", "Controlled treatments", "Required outcomes"],
        ["Speculation", "off; draft; 3/5/8 tokens", "acceptance; TPOT; quality"],
        ["Batching", "concurrency; token budget", "queue; TTFT; goodput"],
        ["KV cache", "off; local; tenant; remote", "hits; transfer; memory"],
        ["Scheduling", "RR; affinity; WCF", "workflow tail; fairness"],
        ["Recovery", "recompute; checkpoint; replica", "RTO; lost work; correctness"],
        ["Security", "global; partition; keyed salt", "cross-hits; AUC; overhead"],
    ]
    data = [[Paragraph(_inline(cell), styles["body"]) for cell in row] for row in rows]
    table = Table(data, colWidths=[30 * mm, 69 * mm, 69 * mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BCCCDC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, colors.HexColor("#F5F9FC")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _title_page(styles: dict[str, ParagraphStyle]) -> list:
    return [
        Spacer(1, 35 * mm),
        Paragraph("AEGISSERVE", styles["title"]),
        Paragraph(
            "Secure and Efficient Multi-Agent LLM Inference in Distributed Clouds",
            styles["subtitle"],
        ),
        Spacer(1, 12 * mm),
        Table(
            [["AI SYSTEMS", "SECURITY", "RESILIENCE"]],
            colWidths=[42 * mm, 42 * mm, 42 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#163B59")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#B8E3EA")),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("BOX", (0, 0), (-1, -1), 0.6, TEAL),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, TEAL),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            ),
        ),
        Spacer(1, 45 * mm),
        Paragraph("WHITE PAPER / RESEARCH PROPOSAL", styles["meta"]),
        Spacer(1, 3 * mm),
        Paragraph("Version 0.2 - August 2026", styles["meta"]),
        Paragraph("Shivam Kumar", styles["meta"]),
        Spacer(1, 12 * mm),
        Paragraph(
            "Proposed system and benchmark. No measured AegisServe performance is claimed.",
            ParagraphStyle(
                "TitleCallout",
                parent=styles["meta"],
                textColor=WHITE,
                fontName="Helvetica",
                leading=13,
            ),
        ),
    ]


def _parse_markdown(text: str, styles: dict[str, ParagraphStyle]) -> list:
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.strip() == "## Abstract")
    lines = lines[start:]
    story: list = []
    index = 0
    references = False
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if stripped == "<!-- ARCHITECTURE_FIGURE -->":
            story.extend(
                [
                    Spacer(1, 2 * mm),
                    _architecture_figure(),
                    Paragraph(
                        "Figure 1. AegisServe logical architecture and evidence path.",
                        styles["caption"],
                    ),
                ]
            )
            index += 1
            continue
        if stripped == "<!-- BENCHMARK_TABLE -->":
            story.extend(
                [
                    Spacer(1, 1 * mm),
                    _benchmark_table(styles),
                    Paragraph(
                        "Table 1. Required mechanism families and outcomes.",
                        styles["caption"],
                    ),
                ]
            )
            index += 1
            continue
        if stripped.startswith("```"):
            code: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code.append(lines[index])
                index += 1
            code_block = Preformatted("\n".join(code), styles["code"], maxLineLength=88)
            story.append(
                Table(
                    [[code_block]],
                    colWidths=[168 * mm],
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ]
                    ),
                )
            )
            story.append(Spacer(1, 3 * mm))
            index += 1
            continue
        if stripped.startswith("## "):
            heading = stripped[3:]
            references = heading == "References"
            story.append(Paragraph(_inline(heading), styles["h1"]))
            index += 1
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(_inline(stripped[4:]), styles["h2"]))
            index += 1
            continue
        if stripped.startswith("> "):
            quote = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip().lstrip("> "))
                index += 1
            story.append(Paragraph(_inline(" ".join(quote)), styles["callout"]))
            continue
        if re.match(r"^[-*] ", stripped) or re.match(r"^\d+\. ", stripped):
            ordered = bool(re.match(r"^\d+\. ", stripped))
            items = []
            while index < len(lines):
                current = lines[index].strip()
                match = re.match(r"^(?:[-*]|\d+\.)\s+(.+)$", current)
                if not match:
                    break
                items.append(ListItem(Paragraph(_inline(match.group(1)), styles["list"])))
                index += 1
            story.append(
                ListFlowable(
                    items,
                    bulletType="1" if ordered else "bullet",
                    start="1",
                    leftIndent=16,
                    bulletFontName="Helvetica-Bold",
                    bulletFontSize=8,
                    bulletColor=TEAL,
                    spaceAfter=2.5 * mm,
                )
            )
            continue

        paragraph = [stripped]
        index += 1
        while index < len(lines):
            candidate = lines[index].strip()
            if not candidate or candidate.startswith(("#", ">", "```", "<!--")):
                break
            if re.match(r"^[-*] ", candidate) or re.match(r"^\d+\. ", candidate):
                break
            paragraph.append(candidate)
            index += 1
        rendered = _inline(" ".join(paragraph))
        style = (
            styles["reference"]
            if references and re.match(r"^\[\d+]", stripped)
            else styles["body"]
        )
        story.append(Paragraph(rendered, style))
    return story


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    non_ascii = sorted({character for character in text if ord(character) > 127})
    if non_ascii:
        raise SystemExit(f"white-paper source contains non-ASCII characters: {non_ascii}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    story = _title_page(styles)
    story.append(PageBreak())
    story.extend(_parse_markdown(text, styles))
    doc = WhitePaperDoc(str(OUTPUT))
    doc.build(story, canvasmaker=InvariantCanvas)
    print(OUTPUT)


if __name__ == "__main__":
    main()
