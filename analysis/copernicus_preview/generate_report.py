from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
)


# =========================================================
# CONFIG
# =========================================================
OUTPUT_PDF = "Aceh_Ocean_Insight_Premium.pdf"

IMG_SST = "sst_premium.png"
IMG_CHL = "chl.png"
IMG_SCATTER = "sst_chl_scatter.png"

TITLE = "ACEH OCEAN INTELLIGENCE BRIEF"
SUBTITLE = "Extending Ocean Understanding with AI (2024–2026)"

INTRO = (
    "This brief presents an AI-assisted extension of Copernicus Marine data "
    "for the Aceh region, transforming observational data into operational "
    "ocean intelligence."
)

KEY_OBS = [
    "SST shows a persistent warming trend from February to April 2026.",
    "Chlorophyll-a remains highly variable and episodic.",
    "The SST–CHL relationship is dispersed and non-linear.",
]

SCIENTIFIC_INSIGHT = (
    "Marine productivity in the Aceh region is not directly governed by surface "
    "temperature alone, but by dynamic processes such as vertical mixing, nutrient "
    "transport, and episodic forcing."
)

SYSTEM_INTERPRETATION = (
    "The Aceh marine system exhibits non-linear behavior, indicating a complex "
    "interaction between physical and biological processes."
)

POSITIONING = (
    "This brief demonstrates how Copernicus Marine data can be translated into "
    "a real-world, AI-assisted ocean intelligence workflow for coastal "
    "understanding and scientific communication."
)

FOOTER_TEXT = "NELAYA-AI | Powered by Copernicus Marine Data | Aceh, Indonesia | 2026"


# =========================================================
# HELPERS
# =========================================================
def ensure_file_exists(path_str: str) -> Path:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {path.resolve()}")
    return path


def fit_image(path: str, max_width: float, max_height: float) -> Image:
    img = Image(path)
    iw, ih = img.imageWidth, img.imageHeight
    scale = min(max_width / iw, max_height / ih)
    img.drawWidth = iw * scale
    img.drawHeight = ih * scale
    return img


def bullet_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(f"• {text}", style)


# =========================================================
# VALIDATE INPUTS
# =========================================================
ensure_file_exists(IMG_SST)
ensure_file_exists(IMG_CHL)
ensure_file_exists(IMG_SCATTER)

# =========================================================
# DOCUMENT SETUP
# =========================================================
doc = SimpleDocTemplate(
    OUTPUT_PDF,
    pagesize=landscape(A4),
    leftMargin=10 * mm,
    rightMargin=10 * mm,
    topMargin=8 * mm,
    bottomMargin=8 * mm,
)

page_width, page_height = landscape(A4)
usable_width = page_width - doc.leftMargin - doc.rightMargin

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "TitleCustom",
    parent=styles["Title"],
    fontName="Helvetica-Bold",
    fontSize=18,
    leading=21,
    textColor=colors.HexColor("#0B1F33"),
    alignment=TA_CENTER,
    spaceAfter=2,
)

subtitle_style = ParagraphStyle(
    "SubtitleCustom",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=9.2,
    leading=11,
    textColor=colors.HexColor("#4F5D75"),
    alignment=TA_CENTER,
    spaceAfter=4,
)

section_style = ParagraphStyle(
    "SectionCustom",
    parent=styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=10,
    leading=12,
    textColor=colors.HexColor("#0B1F33"),
    spaceBefore=0,
    spaceAfter=2,
)

body_style = ParagraphStyle(
    "BodyCustom",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=8.2,
    leading=10,
    textColor=colors.HexColor("#222222"),
    spaceAfter=2,
)

bullet_style = ParagraphStyle(
    "BulletCustom",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=8.0,
    leading=9.5,
    textColor=colors.HexColor("#222222"),
    leftIndent=0,
    spaceAfter=1,
)

caption_style = ParagraphStyle(
    "CaptionCustom",
    parent=styles["Normal"],
    fontName="Helvetica-Oblique",
    fontSize=7.0,
    leading=8.2,
    textColor=colors.HexColor("#666666"),
    alignment=TA_LEFT,
)

footer_style = ParagraphStyle(
    "FooterCustom",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=7.3,
    leading=9,
    textColor=colors.HexColor("#5A5A5A"),
    alignment=TA_CENTER,
)

# =========================================================
# COLUMN WIDTHS
# =========================================================
left_col_width = usable_width * 0.58
right_col_width = usable_width * 0.42

# lebih kecil agar pasti muat
img_max_width = left_col_width - 8 * mm
sst_img = fit_image(IMG_SST, img_max_width, 58 * mm)
chl_img = fit_image(IMG_CHL, img_max_width, 40 * mm)
scatter_img = fit_image(IMG_SCATTER, img_max_width, 48 * mm)

# =========================================================
# LEFT COLUMN
# =========================================================
left_story = [
    sst_img,
    Spacer(1, 1.2 * mm),
    Paragraph("Figure 1. Sea Surface Temperature with 7-day moving average.", caption_style),
    Spacer(1, 2.2 * mm),
    chl_img,
    Spacer(1, 1.2 * mm),
    Paragraph("Figure 2. Chlorophyll-a variability indicating episodic productivity.", caption_style),
    Spacer(1, 2.2 * mm),
    scatter_img,
    Spacer(1, 1.2 * mm),
    Paragraph("Figure 3. Non-linear SST–CHL relationship.", caption_style),
]

left_panel = Table([[left_story]], colWidths=[left_col_width])
left_panel.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9E2EC")),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))

# =========================================================
# RIGHT COLUMN
# =========================================================
right_story = [
    Paragraph("Overview", section_style),
    Paragraph(INTRO, body_style),
    Spacer(1, 1.5 * mm),

    Paragraph("Key Observations", section_style),
    bullet_paragraph(KEY_OBS[0], bullet_style),
    bullet_paragraph(KEY_OBS[1], bullet_style),
    bullet_paragraph(KEY_OBS[2], bullet_style),
    Spacer(1, 1.5 * mm),

    Paragraph("Scientific Insight", section_style),
    Paragraph(SCIENTIFIC_INSIGHT, body_style),
    Spacer(1, 1.5 * mm),

    Paragraph("System Interpretation", section_style),
    Paragraph(SYSTEM_INTERPRETATION, body_style),
    Spacer(1, 1.5 * mm),

    Paragraph("Positioning", section_style),
    Paragraph(POSITIONING, body_style),
]

right_panel = Table([[right_story]], colWidths=[right_col_width])
right_panel.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D9E2EC")),
    ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
]))

# =========================================================
# MAIN CONTENT
# =========================================================
elements = []
elements.append(Paragraph(TITLE, title_style))
elements.append(Paragraph(SUBTITLE, subtitle_style))
elements.append(Spacer(1, 2 * mm))

main_grid = Table(
    [[left_panel, right_panel]],
    colWidths=[left_col_width, right_col_width],
)
main_grid.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 2),
    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ("TOPPADDING", (0, 0), (-1, -1), 0),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
]))

elements.append(main_grid)
elements.append(Spacer(1, 2.5 * mm))
elements.append(Paragraph(FOOTER_TEXT, footer_style))

# =========================================================
# BUILD
# =========================================================
doc.build(elements)
print(f"✅ PDF berhasil dibuat: {OUTPUT_PDF}")
