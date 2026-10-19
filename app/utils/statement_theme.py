"""
Shared visual theme for investor statement PDFs.

Applies Janus Henderson co-branded styling when the investor holds a JH fund;
otherwise retains the default AXYS INVESTMENT BANK navy theme.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class StatementTheme:
    """Color and layout tokens for a statement PDF."""

    name: str
    is_jh: bool
    primary: str
    primary_dark: str
    primary_light: str
    row_alt: str
    co_brand: str
    table_header_bg: str
    table_header_text: str
    label_column_bg: str
    text_dark: str = "#111827"
    text_muted: str = "#666666"
    divider_grey: str = "#d1d5db"
    grid_grey: str = "#dddddd"


AXYS_THEME = StatementTheme(
    name="axys",
    is_jh=False,
    primary="#00005b",
    primary_dark="#00005b",
    primary_light="#f0f0f5",
    row_alt="#fafafa",
    co_brand="#00005b",
    table_header_bg="#f5f5f5",
    table_header_text="#00005b",
    label_column_bg="#f9f9fb",
)

JH_THEME = StatementTheme(
    name="janus_henderson",
    is_jh=True,
    primary="#00005b",
    primary_dark="#00005b",
    primary_light="#f0f0f5",
    row_alt="#fafafa",
    co_brand="#00005b",
    table_header_bg="#f5f5f5",
    table_header_text="#00005b",
    label_column_bg="#f9f9fb",
)


def _hex(value: str):
    return colors.HexColor(value)


def is_janus_henderson_fund(fund_names=(), fund_codes=()) -> bool:
    """Identify JH by fund code first, with a name fallback."""
    if any(str(code or "").strip().upper() == "JH" for code in fund_codes):
        return True
    return any(
        "janus" in str(name or "").casefold()
        and (
            "henderson" in str(name or "").casefold()
            or "hernderson" in str(name or "").casefold()
        )
        for name in fund_names
    )


def is_dangote_dprp_fund(fund_names=(), fund_codes=()) -> bool:
    """Identify Dangote Petroleum Refinery and Petrochemicals by fund code or name."""
    if any(str(code or "").strip().upper() == "DPRP" for code in fund_codes):
        return True
    return any(
        "dangote" in str(name or "").casefold()
        or "dprp" in str(name or "").casefold()
        for name in fund_names
    )


def resolve_product_type(fund_names=(), fund_codes=()) -> str:
    """
    FUNDS vs SHARES product classification for batches/deposits.

    Reuses is_dangote_dprp_fund — the single source of truth for DPRP identity,
    already used for statement/PDF theming — since DPRP is currently the only
    SHARES product. Everything else is FUNDS.
    """
    from app.database.product_type import FUNDS, SHARES

    return SHARES if is_dangote_dprp_fund(fund_names, fund_codes) else FUNDS


def get_statement_theme(fund_names=(), fund_codes=()) -> StatementTheme:
    """Return JH theme when any invested fund is Janus Henderson."""
    if is_janus_henderson_fund(fund_names, fund_codes):
        return JH_THEME
    return AXYS_THEME


def resolve_axys_logo_path() -> Optional[Path]:
    candidates = [
        PROJECT_ROOT / "assets" / "logo" / "AXYS LOGO ON lightmode BG@300x.png",
        PROJECT_ROOT / "frontend" / "public" / "AIBlight.png",
        PROJECT_ROOT / "ofds-frontend" / "public" / "AIBlight.png",
        PROJECT_ROOT / "backend" / "assets" / "AIBlight.png",
    ]
    for logo_path in candidates:
        if logo_path.exists():
            return logo_path
    return None


def resolve_jh_logo_path(fund_names=(), fund_codes=()) -> Optional[Path]:
    # Statements carry the AXYS logo only; the Janus Henderson logo is no
    # longer shown (the JH colour theme is unchanged).
    return None


def build_statement_brand_block(
    theme: StatementTheme,
    jh_logo_path: Optional[Path] = None,
    axys_logo_path: Optional[Path] = None,
) -> Optional[Table]:
    """
    Build the logo header block.

    JH statements use side-by-side JH | AXYS logos (matching official co-brand layout).
    Standard statements show AXYS only.
    """
    axys_path = axys_logo_path or resolve_axys_logo_path()
    if not axys_path or not axys_path.exists():
        return None

    axys_logo = Image(str(axys_path), width=135, height=43)

    if theme.is_jh and jh_logo_path and jh_logo_path.exists():
        jh_logo = Image(str(jh_logo_path), width=120, height=36)
        divider = Table([[""]], colWidths=[0.02 * inch], rowHeights=[0.42 * inch])
        divider.setStyle(TableStyle([
            ("LINEAFTER", (0, 0), (0, 0), 0.75, _hex("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        brand_block = Table([[jh_logo, divider, axys_logo]], colWidths=[1.35 * inch, 0.12 * inch, 1.45 * inch])
        brand_block.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return brand_block

    brand_block = Table([[axys_logo]], colWidths=[1.9 * inch])
    brand_block.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return brand_block


def build_paragraph_styles(
    theme: StatementTheme,
    base_styles,
    body_font: str,
    body_font_bold: str,
) -> Dict[str, ParagraphStyle]:
    """Build common paragraph styles for statement PDFs."""
    return {
        "title": ParagraphStyle(
            "StmtTitle",
            parent=base_styles["Heading1"],
            fontSize=18,
            textColor=_hex(theme.primary),
            spaceAfter=6,
            alignment=TA_LEFT,
            fontName=body_font_bold,
        ),
        "heading": ParagraphStyle(
            "StmtHeading",
            parent=base_styles["Heading2"],
            fontSize=12,
            textColor=_hex(theme.primary),
            spaceAfter=12,
            fontName=body_font_bold,
        ),
        "section_heading": ParagraphStyle(
            "StmtSectionHeading",
            parent=base_styles["Heading3"],
            fontSize=10,
            textColor=_hex(theme.primary),
            spaceAfter=8,
            fontName=body_font_bold,
        ),
        "fund_title": ParagraphStyle(
            "StmtFundTitle",
            parent=base_styles["Heading1"],
            fontSize=13,
            textColor=_hex(theme.primary),
            spaceAfter=4,
            spaceBefore=2,
            leading=16,
            fontName=body_font_bold,
        ),
        "normal": ParagraphStyle(
            "StmtNormal",
            parent=base_styles["Normal"],
            fontSize=9,
            textColor=_hex("#333333"),
            leading=11,
            fontName=body_font,
        ),
        "info_value": ParagraphStyle(
            "StmtInfoValue",
            parent=base_styles["Normal"],
            fontSize=9,
            leading=11,
            textColor=_hex(theme.text_dark),
            fontName=body_font,
        ),
        "small_right": ParagraphStyle(
            "StmtSmallRight",
            parent=base_styles["Normal"],
            fontSize=8,
            textColor=_hex("#333333"),
            alignment=2,
            leading=10,
            fontName=body_font,
        ),
        "footer": ParagraphStyle(
            "StmtFooter",
            parent=base_styles["Normal"],
            fontSize=9,
            textColor=_hex(theme.text_muted),
            leading=12,
            fontName=body_font,
        ),
        "tagline": ParagraphStyle(
            "StmtTagline",
            parent=base_styles["Normal"],
            fontSize=8,
            textColor=_hex("#333333"),
            leading=11,
            fontName=body_font,
        ),
    }


def append_divider_line(story: List[Any], theme: StatementTheme, width: float = 7.5) -> None:
    story.append(Table(
        [[""]],
        colWidths=[width * inch],
        style=[("LINEBELOW", (0, 0), (-1, -1), 1, _hex(theme.primary))],
    ))


def append_fund_title(story: List[Any], theme: StatementTheme, fund_name: str, styles: Dict[str, ParagraphStyle]) -> None:
    if not theme.is_jh or not fund_name or fund_name.strip() in {"—", "-"}:
        return
    story.append(Paragraph(escape_xml(fund_name.upper()), styles["fund_title"]))
    story.append(Spacer(1, 0.06 * inch))


def append_branded_footer(
    story: List[Any],
    theme: StatementTheme,
    styles: Dict[str, ParagraphStyle],
    disclaimer_html: str,
    generated_html: str,
) -> None:
    story.append(Spacer(1, 0.08 * inch))
    story.append(Table(
        [[""]],
        colWidths=[7.3 * inch],
        style=[("LINEBELOW", (0, 0), (-1, -1), 0.5, _hex(theme.divider_grey))],
    ))
    story.append(Spacer(1, 0.06 * inch))

    if theme.is_jh:
        accent = Table([[""]], colWidths=[0.45 * inch], rowHeights=[0.06 * inch])
        accent.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), _hex(theme.co_brand))]))
        story.append(accent)
        story.append(Spacer(1, 0.06 * inch))
        story.append(Paragraph(
            f'Investing in a Brighter Future <font color="{theme.primary}"><b>Together</b></font>',
            styles["tagline"],
        ))
        story.append(Spacer(1, 0.08 * inch))

    story.append(Paragraph(disclaimer_html, styles["footer"]))
    story.append(Paragraph(generated_html, styles["footer"]))


def make_page_callbacks(theme: StatementTheme) -> Tuple[Optional[Callable], Optional[Callable]]:
    """Return ReportLab onFirstPage / onLaterPages callbacks for themed decorations."""

    def _draw(canvas, doc) -> None:
        if not theme.is_jh:
            return
        canvas.saveState()
        _, page_height = doc.pagesize
        bar_width = 4
        canvas.setFillColor(_hex(theme.primary))
        canvas.rect(0, 0, bar_width, page_height, fill=1, stroke=0)
        canvas.restoreState()

    if theme.is_jh:
        return _draw, _draw
    return None, None


def apply_doc_page_callbacks(doc, theme: StatementTheme) -> None:
    on_first, on_later = make_page_callbacks(theme)
    if on_first and on_later:
        doc.onFirstPage = on_first
        doc.onLaterPages = on_later


def build_doc_template(
    buffer,
    theme: StatementTheme,
    *,
    left_margin: float = 0.72,
    right_margin: float = 0.6,
    top_margin: float = 0.55,
    bottom_margin: float = 0.55,
):
    """Create a SimpleDocTemplate with themed page margins and callbacks."""
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate

    left = (left_margin + 0.12) * inch if theme.is_jh else left_margin * inch
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=left,
        rightMargin=right_margin * inch,
        topMargin=top_margin * inch,
        bottomMargin=bottom_margin * inch,
    )
    apply_doc_page_callbacks(doc, theme)
    return doc


def escape_xml(value: Any) -> str:
    from xml.sax.saxutils import escape
    return escape(str(value or ""))


def summary_table_style(theme: StatementTheme, body_font: str, body_font_bold: str) -> TableStyle:
    return TableStyle([
        ("FONT", (0, 0), (-1, -1), body_font, 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), _hex(theme.text_dark)),
        ("FONTNAME", (0, 0), (-1, -1), body_font),
        ("BACKGROUND", (0, 0), (-1, 0), _hex(theme.table_header_bg)),
        ("TEXTCOLOR", (0, 0), (-1, 0), _hex(theme.table_header_text)),
        ("BACKGROUND", (0, 1), (-1, 1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, _hex(theme.grid_grey)),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), body_font_bold),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])


def history_table_style(theme: StatementTheme, body_font: str, body_font_bold: str) -> TableStyle:
    return TableStyle([
        ("FONT", (0, 0), (-1, 0), body_font_bold, 6),
        ("FONT", (0, 1), (-1, -1), body_font, 5.8),
        ("TEXTCOLOR", (0, 0), (-1, 0), _hex(theme.table_header_text)),
        ("BACKGROUND", (0, 0), (-1, 0), _hex(theme.table_header_bg)),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.25, _hex(theme.grid_grey)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _hex(theme.row_alt)]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ])


def kv_table_style(theme: StatementTheme, body_font: str, body_font_bold: str) -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), _hex(theme.label_column_bg)),
        ("TEXTCOLOR", (0, 0), (0, -1), _hex(theme.primary)),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, -1), body_font),
        ("FONTNAME", (0, 0), (0, -1), body_font_bold),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ])


def append_receipt_header(
    story: List[Any],
    theme: StatementTheme,
    pdf_styles: Dict[str, ParagraphStyle],
    *,
    jh_logo_path: Optional[Path],
    document_title: str,
    fund_name: Optional[str] = None,
) -> None:
    """Build the standard co-branded header used on deposit/withdrawal/transfer PDFs."""
    brand_block = build_statement_brand_block(theme, jh_logo_path)
    head_office_html = (
        "<para align=right>"
        "<font size=9><b>HEAD OFFICE</b></font><br/>"
        "<font size=8>The Promenade, 5th Floor | General Mathenge Rd</font><br/>"
        "<font size=8>P.O. Box 43676-00100 | Nairobi | Kenya</font><br/>"
        "<font size=8>T: 0711047000 | M: 0790404571</font><br/>"
        "<font size=8>W: www.aib-axysafrica.com</font>"
        "</para>"
    )
    header_cells = [
        brand_block if brand_block is not None else Paragraph(
            '<font size=18><b>AXYS INVESTMENT BANK</b></font>',
            pdf_styles["title"],
        ),
        Paragraph(head_office_html, pdf_styles["small_right"]),
    ]
    header_table = Table([header_cells], colWidths=[3.2 * inch, 4.3 * inch])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.04 * inch))
    append_divider_line(story, theme)
    story.append(Spacer(1, 0.10 * inch))
    if fund_name:
        append_fund_title(story, theme, fund_name, pdf_styles)
    story.append(Paragraph(document_title, pdf_styles["heading"]))
    story.append(Spacer(1, 0.15 * inch))


def highlight_banner_style(theme: StatementTheme, body_font_bold: str) -> TableStyle:
    """Style for prominent amount banners (withdrawal/deposit/transfer summaries)."""
    return TableStyle([
        ("FONT", (0, 0), (-1, -1), body_font_bold, 16),
        ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
        ("BACKGROUND", (0, 0), (0, 0), _hex(theme.primary)),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("FONTNAME", (1, 0), (1, 0), body_font_bold),
        ("GRID", (0, 0), (-1, -1), 1, _hex(theme.primary_dark)),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
        ("TOPPADDING", (0, 0), (-1, -1), 18),
        ("LEFTPADDING", (0, 0), (-1, -1), 15),
        ("RIGHTPADDING", (0, 0), (-1, -1), 15),
    ])


def build_orange_banner_table(
    text: str,
    theme: StatementTheme,
    body_font_bold: str,
    font_size: int = 10,
    width: float = 7.5,
) -> Table:
    """Build a full-width solid orange section banner (e.g. CLIENT STATEMENT)."""
    title_p = Paragraph(
        f'<font color="#FFFFFF"><b>{escape_xml(text.upper() if text == "CLIENT STATEMENT" else text)}</b></font>',
        ParagraphStyle(
            "OrangeBannerText",
            fontName=body_font_bold,
            fontSize=font_size,
            leading=font_size + 2,
            textColor=colors.white,
        ),
    )
    banner_table = Table([[title_p]], colWidths=[width * inch])
    banner_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _hex(theme.primary)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return banner_table


def build_jh_logo_block(jh_logo_path: Optional[Path] = None) -> Optional[Table]:
    """Build standalone Janus Henderson Investors logo block below the top header divider."""
    if not jh_logo_path or not jh_logo_path.exists():
        return None
    jh_img = Image(str(jh_logo_path), width=155, height=38)
    tbl = Table([[jh_img]], colWidths=[7.5 * inch])
    tbl.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


def client_info_table_style(theme: StatementTheme, body_font: str, body_font_bold: str) -> TableStyle:
    """Table style for client information with top & bottom solid border lines."""
    return TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), body_font),
        ("FONTNAME", (0, 0), (0, -1), body_font_bold),
        ("FONTNAME", (2, 0), (2, -1), body_font_bold),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), _hex("#111827")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.75, _hex("#000000")),
        ("LINEBELOW", (0, -1), (-1, -1), 0.75, _hex("#000000")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ])

