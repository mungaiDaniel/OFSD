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

import functools
import io


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Statement PDFs use Times New Roman. ReportLab's built-in Times-Roman/Times-Bold are
# metric-compatible with it and need no font file on the server.
STATEMENT_FONT = "Times-Roman"
STATEMENT_FONT_BOLD = "Times-Bold"

# Receipt-style PDFs (deposit / transfer / deployment / withdrawal confirmations):
# everything sits inside one 6.5 in column so every left edge lines up.
RECEIPT_CONTENT_WIDTH = 6.5 * inch
_FRAME_PAD = 6  # SimpleDocTemplate frames pad 6 pt on each side


def statement_fonts() -> Tuple[str, str]:
    """(regular, bold) font names used for every statement PDF."""
    return STATEMENT_FONT, STATEMENT_FONT_BOLD


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


@functools.lru_cache(maxsize=16)
def _logo_png(path_str: str, width_pt: float) -> Optional[Tuple[bytes, float]]:
    """
    The logo trimmed of its blank margin and downscaled to ~300 dpi for the width it is
    printed at: (PNG bytes, height/width). The AXYS logo file is 7,892 px wide, printed
    ~2 in wide, and carries blank space on every side - embedding it as-is made each PDF
    spend over a second re-encoding the image, and the blank left margin kept the logo
    from lining up with the text below it. Built once per process, then reused.
    None -> caller falls back to the file as it is.
    """
    try:
        from PIL import Image as PILImage, ImageChops
        with PILImage.open(path_str) as im:
            im = im.convert("RGBA")
            work = im.copy()
            work.thumbnail((1600, 1600))
            flat = PILImage.alpha_composite(PILImage.new("RGBA", work.size, (255, 255, 255, 255)), work).convert("RGB")
            diff = ImageChops.difference(flat, PILImage.new("RGB", work.size, (255, 255, 255)))
            bbox = diff.point(lambda p: 255 if p > 12 else 0).getbbox()
            if bbox:
                sx = im.width / work.width
                sy = im.height / work.height
                pad = 2
                im = im.crop((
                    max(0, int(bbox[0] * sx) - pad), max(0, int(bbox[1] * sy) - pad),
                    min(im.width, int(bbox[2] * sx) + pad), min(im.height, int(bbox[3] * sy) + pad),
                ))
            target_w = max(1, int(width_pt / 72 * 300))
            if im.width > target_w:
                im = im.resize((target_w, max(1, round(im.height * target_w / im.width))), PILImage.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="PNG", optimize=True)
            return buf.getvalue(), im.height / im.width
    except Exception:
        return None


def logo_image(path, width: float, height: float) -> Image:
    """A platypus Image of a logo: trimmed + downscaled copy when available (height follows the trimmed shape)."""
    cached = _logo_png(str(path), float(width))
    if cached is not None:
        data, aspect = cached
        return Image(io.BytesIO(data), width=width, height=round(width * aspect, 2))
    return Image(str(path), width=width, height=height)


def resolve_axys_logo_path() -> Optional[Path]:
    candidates = [
        PROJECT_ROOT / "assets" / "logo" / "brand-logo-light.png",
        PROJECT_ROOT / "frontend" / "public" / "brand-logo.svg",
        PROJECT_ROOT / "ofds-frontend" / "public" / "brand-logo.svg",
        PROJECT_ROOT / "backend" / "assets" / "brand-logo.svg",
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
    logo_width: float = 135,
) -> Optional[Table]:
    """
    Build the logo header block.

    JH statements use side-by-side JH | AXYS logos (matching official co-brand layout).
    Standard statements show AXYS only.
    """
    axys_path = axys_logo_path or resolve_axys_logo_path()
    if not axys_path or not axys_path.exists():
        return None

    # The logo file is 7892 x 2517 px; keep that aspect ratio at any width.
    axys_logo = logo_image(axys_path, width=logo_width, height=round(logo_width * 2517 / 7892, 1))

    if theme.is_jh and jh_logo_path and jh_logo_path.exists():
        jh_logo = logo_image(jh_logo_path, width=120, height=36)
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

    brand_block = Table([[axys_logo]], colWidths=[max(1.9 * inch, logo_width + 4)])
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
    return _scale_for_times(_paragraph_styles(theme, base_styles, body_font, body_font_bold), body_font)


def _scale_for_times(styles: Dict[str, ParagraphStyle], body_font: str) -> Dict[str, ParagraphStyle]:
    # Times sets noticeably smaller than Montserrat at the same point size, so the
    # sizes are nudged up a little to keep the text comfortably readable.
    if body_font != STATEMENT_FONT:
        return styles
    bump = {"title": 1, "heading": 1, "section_heading": 1.5, "normal": 1, "info_value": 1, "footer": 0.5}
    for key, extra in bump.items():
        st = styles.get(key)
        if st is not None:
            st.fontSize = st.fontSize + extra
            st.leading = max(st.leading, st.fontSize * 1.2)
    return styles


def _paragraph_styles(
    theme: StatementTheme,
    base_styles,
    body_font: str,
    body_font_bold: str,
) -> Dict[str, ParagraphStyle]:
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


def _fit_story_to_column(story: List[Any], width: float) -> None:
    """
    Make every table in a receipt line up on one left edge.
    - tables wider than the column are scaled down to it; narrower ones keep their width
    - every table is left-aligned (platypus centres them by default, which is what
      pushed some tables left of the text)
    - tables without a box/grid/background (header, details, footer rule) get zero
      side padding so their text starts exactly on the edge the boxes start on
    """
    for flowable in story:
        if not isinstance(flowable, Table):
            continue
        widths = getattr(flowable, "_colWidths", None)
        if widths and all(isinstance(w, (int, float)) for w in widths):
            total = float(sum(widths))
            if total > width + 0.5:
                scaled = [w * width / total for w in widths]
                flowable._colWidths = scaled
                flowable._argW = list(scaled)  # Table re-reads _argW when it lays out
        flowable.hAlign = "LEFT"
        boxed = any(c[0] in ("GRID", "BOX") for c in getattr(flowable, "_linecmds", [])) or any(
            c[0] == "BACKGROUND" for c in getattr(flowable, "_bkgrndcmds", [])
        )
        if not boxed:
            flowable.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, -1), 0),
                ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
            ]))


def build_doc_template(
    buffer,
    theme: StatementTheme,
    *,
    left_margin: float = 0.72,
    right_margin: float = 0.6,
    top_margin: float = 0.55,
    bottom_margin: float = 0.55,
    receipt: bool = False,
):
    """Create a SimpleDocTemplate with themed page margins and callbacks.

    receipt=True: a single 6.5 in column, margins set so the frame's own 6 pt padding
    lands the content exactly 1 in from the page edge, and every table aligned to it.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate

    if receipt:
        class _ReceiptDoc(SimpleDocTemplate):
            def build(self, flowables, *args, **kwargs):
                _fit_story_to_column(flowables, RECEIPT_CONTENT_WIDTH)
                return super().build(flowables, *args, **kwargs)

        side = (letter[0] - RECEIPT_CONTENT_WIDTH) / 2 - _FRAME_PAD
        doc = _ReceiptDoc(
            buffer,
            pagesize=letter,
            leftMargin=side,
            rightMargin=side,
            topMargin=top_margin * inch,
            bottomMargin=bottom_margin * inch,
        )
        apply_doc_page_callbacks(doc, theme)
        return doc

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
    brand_block = build_statement_brand_block(theme, jh_logo_path, logo_width=190)
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
    header_table = Table([header_cells], colWidths=[3.1 * inch, 3.4 * inch])
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
        ("FONT", (0, 0), (-1, -1), body_font_bold, 12),
        ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
        ("BACKGROUND", (0, 0), (0, 0), _hex(theme.primary)),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("FONTNAME", (1, 0), (1, 0), body_font_bold),
        ("GRID", (0, 0), (-1, -1), 1, _hex(theme.primary_dark)),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
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
    jh_img = logo_image(jh_logo_path, width=155, height=38)
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

