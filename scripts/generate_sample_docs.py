"""Sample document generator for DocMind fictional law-firm demo dataset.

Generates realistic legal documents for 'Sterling & Rauf Law Associates' in data/sample_docs/:
- Fee_Schedule_2026.pdf (4 pages)
- Practice_Areas_Brochure.pdf (3 pages)
- Client_Intake_SOP.pdf (4 pages)
- Confidentiality_and_Data_Policy.pdf (3 pages)
- Client_Engagement_Letter_Template.docx (multi-page template)
- Client_FAQ.txt (UTF-8 English FAQ)
"""

import datetime
import io
import os
from pathlib import Path
from typing import Dict, List, Tuple
import zipfile

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_docs"
FOOTER_NOTICE = "Fictional demo document - not real legal advice"


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and draw total page count and footer notice."""

    page_counts: Dict[str, int] = {}

    def __init__(self, *args, **kwargs):
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[dict] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()
        if hasattr(self, "_filename") and self._filename:
            NumberedCanvas.page_counts[str(self._filename)] = num_pages

    def draw_page_decorations(self, total_pages: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#555555"))

        # Top running header on pages > 1
        if self._pageNumber > 1:
            self.drawString(54, 792, "Sterling & Rauf Law Associates — Legal Practice Documentation")
            self.setStrokeColor(colors.HexColor("#D1D5DB"))
            self.setLineWidth(0.5)
            self.line(54, 784, 541, 784)

        # Bottom running footer on all pages
        self.setStrokeColor(colors.HexColor("#D1D5DB"))
        self.setLineWidth(0.5)
        self.line(54, 45, 541, 45)
        self.drawString(54, 32, FOOTER_NOTICE)
        self.drawRightString(541, 32, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


def get_pdf_styles():
    """Build consistent typography styles for PDF documents."""
    styles = getSampleStyleSheet()

    primary_color = colors.HexColor("#1E1B4B")  # Deep indigo
    accent_color = colors.HexColor("#4F46E5")   # Indigo accent
    body_color = colors.HexColor("#1F2937")     # Neutral dark grey

    styles.add(ParagraphStyle(
        name="DocTitle",
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=primary_color,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="DocSubtitle",
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=accent_color,
        spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading",
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=primary_color,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="SubSectionHeading",
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        textColor=accent_color,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="LegalBody",
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=body_color,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="LegalBullet",
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=body_color,
        leftIndent=14,
        firstLineIndent=-10,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="CalloutText",
        fontName="Helvetica-Oblique",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#374151"),
        spaceBefore=4,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="TableHeader",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
        alignment=0,
    ))
    styles.add(ParagraphStyle(
        name="TableCell",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=body_color,
        alignment=0,
    ))
    styles.add(ParagraphStyle(
        name="TableCellBold",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=body_color,
        alignment=0,
    ))
    return styles


def build_fee_schedule_pdf(output_path: Path) -> None:
    """Generate Fee_Schedule_2026.pdf (4 pages minimum)."""
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=60,
        bottomMargin=54,
        invariant=1,
    )
    styles = get_pdf_styles()
    story = []

    # ---------------- PAGE 1: Overview, Initial Consultations & Hourly Rates ----------------
    story.append(Paragraph("STERLING & RAUF LAW ASSOCIATES", styles["DocSubtitle"]))
    story.append(Paragraph("Schedule of Professional Fees & Billing Policies (2026)", styles["DocTitle"]))
    story.append(Paragraph("Principal Office: Suite 402-404, Gulberg Executive Heights, Main Boulevard, Gulberg III, Lahore, Pakistan", styles["LegalBody"]))
    story.append(Paragraph("Official Contact: Phone: +92 42 3578 9000 | Email: contact@sterlingrauf.com | Currency: Pakistani Rupee (PKR)", styles["LegalBody"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#4F46E5"), spaceAfter=10))

    story.append(Paragraph("1. Preliminary Legal Consultations", styles["SectionHeading"]))
    story.append(Paragraph(
        "1.1. <b>Initial Consultation Fee:</b> The firm charges a standard consultation fee of <b>PKR 5,000 for 45 minutes</b>. "
        "This preliminary meeting enables our advocates to assess case merits, establish jurisdiction, and review essential documents.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "1.2. <b>Engagement Waiver Clause:</b> If the prospective client executes a formal Letter of Engagement within "
        "<b>7 days</b> of the initial consultation, the <b>PKR 5,000 consultation fee is fully waived</b> and credited "
        "towards the client's opening invoice balance.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "1.3. <b>Consultation Booking & Rescheduling:</b> Appointments must be booked at least 24 hours in advance during standard office hours. "
        "Cancellations made with less than 12 hours notice forfeit the consultation slot.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("2. Hourly Professional Billing Rates", styles["SectionHeading"]))
    story.append(Paragraph(
        "2.1. When legal representation or specialized advisory services are billed on a time-spent basis, fees are calculated using the "
        "following hourly billing schedule according to seniority level:",
        styles["LegalBody"],
    ))

    rates_data = [
        [Paragraph("Fee Earner Classification", styles["TableHeader"]), Paragraph("Hourly Billing Rate", styles["TableHeader"]), Paragraph("Scope of Responsibility", styles["TableHeader"])],
        [Paragraph("Senior Partner", styles["TableCellBold"]), Paragraph("PKR 25,000", styles["TableCellBold"]), Paragraph("Complex High Court litigation, strategic corporate transactions, partner-level negotiations.", styles["TableCell"])],
        [Paragraph("Associate Advocate", styles["TableCellBold"]), Paragraph("PKR 12,000", styles["TableCellBold"]), Paragraph("Drafting pleadings, conducting regulatory filings, court appearances, legal research.", styles["TableCell"])],
        [Paragraph("Paralegal / Legal Assistant", styles["TableCellBold"]), Paragraph("PKR 4,000", styles["TableCellBold"]), Paragraph("Document inspection, court record retrieval, witness coordination, indexing.", styles["TableCell"])],
    ]
    rates_table = Table(rates_data, colWidths=[130, 100, 257])
    rates_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E1B4B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(rates_table)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "2.2. <b>Time Increments:</b> Professional time is logged in minimum increments of one-tenth of an hour (6 minutes). "
        "Detailed time records with precise descriptions are attached to every monthly billing statement.",
        styles["LegalBody"],
    ))
    story.append(PageBreak())

    # ---------------- PAGE 2: Retainers & Fixed-Fee Services ----------------
    story.append(Paragraph("3. Advance Retainer Deposits by Practice Area", styles["SectionHeading"]))
    story.append(Paragraph(
        "3.1. Prior to commencing active representation, clients are required to place an advance retainer deposit in the firm's dedicated "
        "client trust account. Retainers are earmarked funds against which earned fees and out-of-pocket disbursements are drawn.",
        styles["LegalBody"],
    ))

    retainer_data = [
        [Paragraph("Practice Area Category", styles["TableHeader"]), Paragraph("Mandatory Retainer Deposit", styles["TableHeader"]), Paragraph("Billing Mechanism", styles["TableHeader"])],
        [Paragraph("Family Law Matters", styles["TableCellBold"]), Paragraph("PKR 75,000", styles["TableCellBold"]), Paragraph("Advance deposit against custody, guardianship, or marital dispute proceedings.", styles["TableCell"])],
        [Paragraph("Property & Real Estate Matters", styles["TableCellBold"]), Paragraph("PKR 100,000", styles["TableCellBold"]), Paragraph("Advance deposit covering title verification, registry vetting, or land suits.", styles["TableCell"])],
        [Paragraph("Corporate Advisory (Monthly)", styles["TableCellBold"]), Paragraph("PKR 150,000", styles["TableCellBold"]), Paragraph("Standing monthly retainer covering up to 15 hours of advisory per month.", styles["TableCell"])],
        [Paragraph("Civil Litigation (General)", styles["TableCellBold"]), Paragraph("PKR 120,000", styles["TableCellBold"]), Paragraph("Advance deposit for District Court and High Court representation.", styles["TableCell"])],
    ]
    retainer_table = Table(retainer_data, colWidths=[140, 120, 227])
    retainer_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E1B4B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(retainer_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("4. Fixed-Fee Legal Services", styles["SectionHeading"]))
    story.append(Paragraph(
        "4.1. For routine transactional and non-contentious legal work, the firm provides fixed-price packages to ensure fee predictability:",
        styles["LegalBody"],
    ))

    fixed_data = [
        [Paragraph("Service Description", styles["TableHeader"]), Paragraph("Fixed Professional Fee", styles["TableHeader"]), Paragraph("Standard Deliverable Scope", styles["TableHeader"])],
        [Paragraph("Commercial Contract Review", styles["TableCellBold"]), Paragraph("PKR 35,000", styles["TableCellBold"]), Paragraph("Review and clause-by-clause markup of contracts up to 15 pages in length.", styles["TableCell"])],
        [Paragraph("Trademark Registration Filing", styles["TableCellBold"]), Paragraph("PKR 45,000", styles["TableCellBold"]), Paragraph("Per class application filing with IPO Pakistan (exclusive of official gov fees).", styles["TableCell"])],
        [Paragraph("Basic Will & Succession Drafting", styles["TableCellBold"]), Paragraph("PKR 50,000", styles["TableCellBold"]), Paragraph("Drafting comprehensive testamentary will and asset distribution schedule.", styles["TableCell"])],
        [Paragraph("Formal Legal Notice Issuance", styles["TableCellBold"]), Paragraph("PKR 20,000", styles["TableCellBold"]), Paragraph("Drafting, partner sign-off, and registered service with acknowledgment due.", styles["TableCell"])],
        [Paragraph("Company Incorporation Package", styles["TableCellBold"]), Paragraph("PKR 60,000", styles["TableCellBold"]), Paragraph("Private Limited incorporation with SECP including Memorandum and Articles.", styles["TableCell"])],
    ]
    fixed_table = Table(fixed_data, colWidths=[140, 110, 237])
    fixed_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E1B4B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(fixed_table)
    story.append(PageBreak())

    # ---------------- PAGE 3: Invoicing, Terms of Payment & Late Surcharges ----------------
    story.append(Paragraph("5. Invoicing Schedules & Payment Terms", styles["SectionHeading"]))
    story.append(Paragraph(
        "5.1. <b>Billing Frequency:</b> Detailed billing statements are rendered on a monthly basis, itemizing all work executed, "
        "attending fee earners, hourly increments, and statutory disbursements incurred during the preceding calendar month.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "5.2. <b>Invoice Due Date:</b> All invoices are <b>due within 15 days</b> from the date of invoice issuance. "
        "Clients are requested to remit payment promptly to avoid interruption of legal representation.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "5.3. <b>Late Fee Surcharge:</b> Overdue accounts that remain unsettled after the 15-day period are subject to a mandatory "
        "<b>late fee of 2% per month</b>, calculated on the outstanding balance until full settlement is received.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "5.4. <b>Suspension of Work:</b> In the event an invoice remains unpaid for more than 30 consecutive days, the firm reserves the right "
        "to pause active preparation, withhold court filings, and seek formal leave of court for withdrawal from representation.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("6. Approved Payment Channels", styles["SectionHeading"]))
    story.append(Paragraph(
        "6.1. For security, audit compliance, and bar ethics rules, payments to Sterling & Rauf Law Associates must be executed solely "
        "through verified banking channels:",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "• <b>Direct Bank Wire / Interbank Funds Transfer (IBFT):</b> Payments may be deposited into the firm's main client account at "
        "Allied Bank Limited (Account Title: <i>Sterling & Rauf Law Associates</i>). Bank account details and IBAN are specified on invoice headers.",
        styles["LegalBullet"],
    ))
    story.append(Paragraph(
        "• <b>Crossed Account Payee Cheques:</b> Drawn in favor of 'Sterling & Rauf Law Associates' and delivered to the firm's Lahore office.",
        styles["LegalBullet"],
    ))
    story.append(Paragraph(
        "6.2. <b>Cash Policy:</b> In compliance with anti-money laundering regulations, cash transactions exceeding PKR 20,000 are strictly prohibited.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("7. Reimbursable Disbursements & Court Costs", styles["SectionHeading"]))
    story.append(Paragraph(
        "7.1. Hourly rates and retainers cover legal expertise and internal overhead only. Out-of-pocket disbursements incurred directly "
        "on the client's behalf are billed at actual cost without firm markup. These include:",
        styles["LegalBody"],
    ))
    story.append(Paragraph("• Court institution fees, court fees stamps, and revenue stamps prescribed by procedural codes.", styles["LegalBullet"]))
    story.append(Paragraph("• Certified copy fees from court record rooms, sub-registrar offices, and land revenue authorities.", styles["LegalBullet"]))
    story.append(Paragraph("• Official government filing fees (e.g. SECP statutory fees, IPO Pakistan official application fees).", styles["LegalBullet"]))
    story.append(Paragraph("• Courier service fees, bailiff service charges, and formal newspaper publication charges for legal citations.", styles["LegalBullet"]))
    story.append(PageBreak())

    # ---------------- PAGE 4: Refund Policy & Final Settlement ----------------
    story.append(Paragraph("8. Retainer Refund Policy & Case Closure Settlement", styles["SectionHeading"]))
    story.append(Paragraph(
        "8.1. <b>Trust Fund Protection:</b> All advance retainer funds remain the client's property until earned through verified professional "
        "time or disbursed for official expenses.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "8.2. <b>Refund Timeline:</b> Upon formal conclusion of legal proceedings, settlement, or termination of engagement, any "
        "<b>unused retainer is refunded within 30 days of case closure</b>.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "8.3. <b>Administrative Charge Deduction:</b> In accordance with firm policy, a <b>10% administrative charge</b> is deducted "
        "from the unexpended balance prior to refund issuance. This fee covers closing file reconciliation, archive indexing, and accounting audits.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "8.4. <b>Final Statement of Account:</b> Every refund remittance is accompanied by a comprehensive, itemized Final Statement of Account "
        "delineating all earned fees, disbursements incurred, administrative charge calculations, and the net refundable sum.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("9. Practice Limitations & Matter Exceptions", styles["SectionHeading"]))
    story.append(Paragraph(
        "9.1. Sterling & Rauf Law Associates maintains dedicated practice focus. Prospective clients should note that the firm "
        "<b>does NOT handle criminal defense or immigration matters</b>. Any inquiries in these areas will be declined during initial intake.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("10. Authorization & Governance", styles["SectionHeading"]))
    story.append(Paragraph(
        "10.1. This Schedule of Professional Fees is effective as of January 1, 2026, and supersedes all prior schedules. "
        "Any amendment or custom fee arrangement must be reduced to writing and counter-signed by Managing Partner Barrister Tariq Sterling.",
        styles["LegalBody"],
    ))
    story.append(Spacer(1, 15))

    auth_data = [
        [Paragraph("<b>Approved By:</b>", styles["TableCellBold"]), Paragraph("<b>Effective Date:</b>", styles["TableCellBold"]), Paragraph("<b>Jurisdiction:</b>", styles["TableCellBold"])],
        [Paragraph("Barrister Tariq Sterling<br/>Managing Partner", styles["TableCell"]), Paragraph("January 1, 2026", styles["TableCell"]), Paragraph("High Court of Judicature, Lahore, Pakistan", styles["TableCell"])],
    ]
    auth_table = Table(auth_data, colWidths=[160, 140, 187])
    auth_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(auth_table)

    doc.build(story, canvasmaker=NumberedCanvas)


def build_practice_areas_pdf(output_path: Path) -> None:
    """Generate Practice_Areas_Brochure.pdf (3 pages minimum)."""
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=60,
        bottomMargin=54,
        invariant=1,
    )
    styles = get_pdf_styles()
    story = []

    # ---------------- PAGE 1: Firm Overview, Approach & Team ----------------
    story.append(Paragraph("STERLING & RAUF LAW ASSOCIATES", styles["DocSubtitle"]))
    story.append(Paragraph("Practice Areas & Institutional Capability Statement", styles["DocTitle"]))
    story.append(Paragraph("Premier Civil, Corporate, Property & Domestic Relations Practice | Lahore, Pakistan", styles["LegalBody"]))
    story.append(Paragraph("Office: Suite 402-404, Gulberg Executive Heights, Main Boulevard, Gulberg III, Lahore | Phone: +92 42 3578 9000", styles["LegalBody"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#4F46E5"), spaceAfter=10))

    story.append(Paragraph("1. Firm Overview & Philosophy", styles["SectionHeading"]))
    story.append(Paragraph(
        "Sterling & Rauf Law Associates is a boutique legal practice established in Lahore, offering focused counsel to corporate entities, "
        "commercial enterprises, family offices, and individual clients. We integrate rigorous analytical standards with practical commercial acumen, "
        "delivering robust representation before trial courts, appellate tribunals, and regulatory bodies.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "Our ethos prioritizes preventative legal engineering: mitigating exposure before disputes arise, structuring transactions with airtight "
        "drafting, and pursuing assertive litigation when judicial intervention is necessary.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("2. Senior Leadership & Practice Team", styles["SectionHeading"]))
    story.append(Paragraph(
        "Our multidisciplinary team comprises seasoned advocates enrolled with the Punjab Bar Council and High Court Bar:",
        styles["LegalBody"],
    ))

    team_data = [
        [Paragraph("Professional Name", styles["TableHeader"]), Paragraph("Designation & Role", styles["TableHeader"]), Paragraph("Core Practice Specialization", styles["TableHeader"])],
        [Paragraph("Barrister Tariq Sterling", styles["TableCellBold"]), Paragraph("Managing Partner", styles["TableCellBold"]), Paragraph("Corporate governance, commercial arbitration, appellate civil litigation, joint ventures.", styles["TableCell"])],
        [Paragraph("Ayesha Rauf", styles["TableCellBold"]), Paragraph("Senior Partner", styles["TableCellBold"]), Paragraph("Family law, succession planning, guardianship, complex estate disputes, mediation.", styles["TableCell"])],
        [Paragraph("Zainab Malik", styles["TableCellBold"]), Paragraph("Senior Associate", styles["TableCellBold"]), Paragraph("Property due diligence, commercial lease vetting, land acquisition, tenancy disputes.", styles["TableCell"])],
        [Paragraph("Hamza Farooq", styles["TableCellBold"]), Paragraph("Associate Advocate", styles["TableCellBold"]), Paragraph("Intellectual property registration, commercial contract drafting, regulatory compliance.", styles["TableCell"])],
    ]
    team_table = Table(team_data, colWidths=[120, 110, 257])
    team_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E1B4B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(team_table)
    story.append(Spacer(1, 10))
    story.append(Paragraph("3. Transparent Professional Fee Structure", styles["SectionHeading"]))
    story.append(Paragraph(
        "We maintain clear, structured pricing across all matters. Initial 45-minute consultations are provided at <b>PKR 5,000</b> "
        "(waived if an engagement is signed within 7 days). Hourly rates are benchmarked at <b>PKR 25,000 for Senior Partners</b>, "
        "<b>PKR 12,000 for Associates</b>, and <b>PKR 4,000 for Paralegals</b>.",
        styles["LegalBody"],
    ))
    story.append(PageBreak())

    # ---------------- PAGE 2: Core Practice Areas ----------------
    story.append(Paragraph("4. Core Legal Practice Disciplines", styles["SectionHeading"]))
    story.append(Paragraph(
        "Sterling & Rauf Law Associates concentrates expertise in six dedicated practice areas:",
        styles["LegalBody"],
    ))

    story.append(Paragraph("4.1. Corporate & Commercial Advisory", styles["SubSectionHeading"]))
    story.append(Paragraph(
        "We serve private limited companies, partnerships, and entrepreneurial enterprises across Pakistan. Services include SECP corporate secretarial "
        "compliance, shareholding restructuring, commercial joint ventures, supplier agreements, and regulatory advisory. We offer standing monthly "
        "corporate advisory retainers at <b>PKR 150,000 per month</b>.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("4.2. Property & Real Estate Law", styles["SubSectionHeading"]))
    story.append(Paragraph(
        "Real estate transactions in Punjab require rigorous scrutiny. Our practice conducts comprehensive title investigations across sub-registrar offices, "
        "revenue authorities, and development authorities (LDA, DHA). We draft transfer deeds, commercial leases, and represent clients in title rectifications, "
        "with advance property retainers set at <b>PKR 100,000</b>.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("4.3. Family Law & Domestic Relations", styles["SubSectionHeading"]))
    story.append(Paragraph(
        "Led by Senior Partner Ayesha Rauf, our family law team provides compassionate yet rigorous representation in custody disputes, guardianship petitions, "
        "maintenance enforcement, inheritance partition, and succession certificates. Advance family law retainers are structured at <b>PKR 75,000</b>.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("4.4. Civil Litigation & Dispute Resolution", styles["SubSectionHeading"]))
    story.append(Paragraph(
        "Our trial advocates appear regularly before Civil Courts, District Courts, and the Lahore High Court. We handle recovery suits, declaration suits, "
        "permanent and temporary injunctions, execution proceedings, and commercial breach of contract actions.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("4.5. Contract Drafting & Commercial Vetting", styles["SubSectionHeading"]))
    story.append(Paragraph(
        "We craft bespoke contracts designed to withstand rigorous judicial scrutiny. Standard commercial contract reviews up to 15 pages are executed "
        "at a fixed fee of <b>PKR 35,000</b>, covering risk analysis, indemnity structuring, and dispute clause optimization.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("4.6. Intellectual Property Protection", styles["SubSectionHeading"]))
    story.append(Paragraph(
        "We safeguard client intellectual capital through trademark filing, opposition drafting, copyright registration, and IP licensing. "
        "Trademark application filing is offered at a fixed fee of <b>PKR 45,000 per class</b> (excluding official government fees).",
        styles["LegalBody"],
    ))
    story.append(PageBreak())

    # ---------------- PAGE 3: Exclusions, Operational Standards & Office Hours ----------------
    story.append(Paragraph("5. Matters the Firm Does NOT Handle", styles["SectionHeading"]))
    story.append(Paragraph(
        "To preserve the highest standards of focused excellence and client care, Sterling & Rauf Law Associates observes strict institutional limitations. "
        "<b>The firm does NOT handle criminal defense or immigration matters</b> under any circumstances.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "We do not accept representation in criminal bail applications, criminal trials, narcotics proceedings, foreign visa applications, "
        "or overseas asylum petitions. Inquiries relating to these areas are immediately declined during our initial intake screening.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("6. Intake & Operational Standards", styles["SectionHeading"]))
    story.append(Paragraph(
        "6.1. <b>Conflict of Interest Clearance:</b> Integrity is non-negotiable. Before accepting any instruction, our compliance officer executes "
        "a thorough conflict check which takes <b>2 working days</b> to complete. No engagement is confirmed until this clearance is formally recorded.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "6.2. <b>Communication Responsiveness:</b> We respect our clients' time. All telephone messages and official client emails "
        "(contact@sterlingrauf.com) are answered within <b>1 business day</b>.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "6.3. <b>Standard Office Hours:</b> Consultations, client appointments, and document reviews are conducted during our official working hours:<br/>"
        "• <b>Monday to Friday:</b> 9:30 AM to 5:30 PM (9:30 - 17:30)<br/>"
        "• <b>Saturday:</b> 10:00 AM to 2:00 PM (10:00 - 14:00)<br/>"
        "• <b>Sunday & Public Holidays:</b> Closed",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "6.4. <b>File Preservation Guarantee:</b> In compliance with our professional conduct rules, all physical and digital client case files "
        "are securely retained for <b>7 years after case closure</b> before confidential destruction.",
        styles["LegalBody"],
    ))

    story.append(Spacer(1, 10))
    story.append(Paragraph("7. Contact & Consultation Scheduling", styles["SectionHeading"]))
    contact_box = [
        [Paragraph("<b>Office Location:</b>", styles["TableCellBold"]), Paragraph("Suite 402-404, Gulberg Executive Heights, Main Boulevard, Gulberg III, Lahore, Pakistan", styles["TableCell"])],
        [Paragraph("<b>Telephone:</b>", styles["TableCellBold"]), Paragraph("+92 42 3578 9000 (Reception & Intake Desk)", styles["TableCell"])],
        [Paragraph("<b>Email:</b>", styles["TableCellBold"]), Paragraph("contact@sterlingrauf.com (General & Intake Queries)", styles["TableCell"])],
        [Paragraph("<b>Escalations:</b>", styles["TableCellBold"]), Paragraph("escalation@sterlingrauf.com (Head of Client Operations)", styles["TableCell"])],
    ]
    contact_table = Table(contact_box, colWidths=[120, 367])
    contact_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(contact_table)

    doc.build(story, canvasmaker=NumberedCanvas)


def build_intake_sop_pdf(output_path: Path) -> None:
    """Generate Client_Intake_SOP.pdf (4 pages minimum)."""
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=60,
        bottomMargin=54,
        invariant=1,
    )
    styles = get_pdf_styles()
    story = []

    # ---------------- PAGE 1: Purpose, Intake Logging & Consultation ----------------
    story.append(Paragraph("STERLING & RAUF LAW ASSOCIATES", styles["DocSubtitle"]))
    story.append(Paragraph("Standard Operating Procedure: Client Onboarding & Intake (SOP-01)", styles["DocTitle"]))
    story.append(Paragraph("Operational Guidelines for Administrative Staff, Associates, and Practice Managers | Version 2.4", styles["LegalBody"]))
    story.append(Paragraph("Effective Date: January 1, 2026 | Governing Office: Lahore Main Office", styles["LegalBody"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#4F46E5"), spaceAfter=10))

    story.append(Paragraph("1. Purpose & Administrative Scope", styles["SectionHeading"]))
    story.append(Paragraph(
        "1.1. This Standard Operating Procedure (SOP) establishes the mandatory steps that must be executed by front-desk administrators, "
        "intake coordinators, and legal associates from the initial client inquiry through to formal execution of the Letter of Engagement.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "1.2. Strict compliance with this SOP ensures ethical compliance under the Legal Practitioners and Bar Councils Act, prevents inadvertent "
        "conflicts of interest, and standardizes the client onboarding experience.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("2. Initial Inquiry Reception & Logging", styles["SectionHeading"]))
    story.append(Paragraph(
        "2.1. <b>Inquiry Channels:</b> Initial client contacts occur via telephone (+92 42 3578 9000), official email (contact@sterlingrauf.com), "
        "or scheduled walk-ins at our Lahore office.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "2.2. <b>Response Timeframe:</b> All prospective client emails and recorded phone messages must be answered within <b>1 business day</b> "
        "by the intake coordinator.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "2.3. <b>Intake Record Creation:</b> Front desk personnel must complete an electronic Client Intake Form (Form INT-01), recording:<br/>"
        "• Full legal name and contact details of prospective client.<br/>"
        "• Opposing party names, corporate affiliations, and known legal counsel.<br/>"
        "• High-level summary of legal subject matter.<br/>"
        "• Confirmation that the matter does <b>NOT</b> involve criminal defense or immigration (which the firm strictly does not handle).",
        styles["LegalBody"],
    ))

    story.append(Paragraph("3. Preliminary Consultation Booking", styles["SectionHeading"]))
    story.append(Paragraph(
        "3.1. Consultations are scheduled within standard office hours: <b>Monday to Friday 9:30-17:30</b> and <b>Saturday 10:00-14:00</b>. "
        "No consultations may be scheduled on Sundays or official gazetted public holidays.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "3.2. <b>Consultation Fee Policy:</b> Staff must explicitly inform the client that the preliminary consultation fee is "
        "<b>PKR 5,000 for 45 minutes</b>. Staff must advise that if the client proceeds to execute a formal Letter of Engagement within "
        "<b>7 days</b>, this consultation fee is <b>fully waived</b> as a credit on their initial ledger.",
        styles["LegalBody"],
    ))
    story.append(PageBreak())

    # ---------------- PAGE 2: Conflict of Interest Screening Protocol ----------------
    story.append(Paragraph("4. Conflict of Interest Verification Protocol", styles["SectionHeading"]))
    story.append(Paragraph(
        "4.1. <b>Mandatory Screening Period:</b> Under no circumstances may an advocate provide substantive legal counsel or execute an engagement "
        "prior to completing the formal conflict-of-interest check. This screening requires <b>2 working days</b> before engagement confirmation.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "4.2. <b>Conflict Search Procedure:</b> The Compliance Administrator executes a comprehensive database query across:<br/>"
        "• Active litigation and advisory clients of Sterling & Rauf Law Associates.<br/>"
        "• Former clients whose files have been closed within the statutory 7-year file retention window.<br/>"
        "• Adversary databases, opposing parties, co-defendants, and designated key witnesses in ongoing proceedings.<br/>"
        "• Corporate parent entities, subsidiaries, and majority directors of existing commercial retainers.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "4.3. <b>Conflict Clearance Validity:</b> A formal Conflict Clearance Certificate (Form CC-02) is issued upon successful search. "
        "This clearance remains <b>valid for 30 calendar days</b>. If an engagement is not finalized within 30 days, a re-check is mandatory.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "4.4. <b>Conflict Discovery Protocol:</b> If a direct or imputed conflict of interest is identified:<br/>"
        "• The matter is immediately flagged to Managing Partner Barrister Tariq Sterling.<br/>"
        "• An adverse determination notice is logged in the register.<br/>"
        "• The prospective client is issued a standard non-engagement letter within 24 hours politely declining representation.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("5. Scope Assessment & Excluded Matters Screening", styles["SectionHeading"]))
    story.append(Paragraph(
        "5.1. Staff must verify that the matter falls squarely within our six authorized practice areas: Corporate & Commercial, "
        "Property & Real Estate, Family Law, Civil Litigation, Contract Drafting, or Intellectual Property.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "5.2. <b>Excluded Disciplines:</b> If the inquiry touches upon <b>criminal defense or immigration matters</b>, staff must politely decline "
        "at the intake stage and offer no preliminary appointment, reiterating that the firm does not practice in these areas.",
        styles["LegalBody"],
    ))
    story.append(PageBreak())

    # ---------------- PAGE 3: Client Document Checklists ----------------
    story.append(Paragraph("6. Required Onboarding Document Checklists", styles["SectionHeading"]))
    story.append(Paragraph(
        "6.1. Prior to final engagement sign-off, clients must submit verified documentation in accordance with Know-Your-Customer (KYC) "
        "guidelines and court filing regulations.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("6.2. Natural Persons (Individual Clients)", styles["SubSectionHeading"]))
    story.append(Paragraph("• <b>Primary Proof of Identity:</b> Clear copy of original, valid Computerized National Identity Card (CNIC) for Pakistani citizens, or valid Passport for foreign nationals.", styles["LegalBullet"]))
    story.append(Paragraph("• <b>Proof of Residence:</b> Utility bill (electricity, gas, or water) issued within the last 90 days matching the client's residential address.", styles["LegalBullet"]))
    story.append(Paragraph("• <b>Passport-Size Photographs:</b> Two recent color photographs for High Court power of attorney (Vakalatnama) registration.", styles["LegalBullet"]))
    story.append(Paragraph("• <b>Matter-Specific Documentation:</b> Original or certified copies of relevant title deeds, contracts, marriage registration certificates (Nikahnama), or contested notices.", styles["LegalBullet"]))

    story.append(Paragraph("6.3. Corporate & Commercial Entities", styles["SubSectionHeading"]))
    story.append(Paragraph("• <b>Incorporation Certificate:</b> Certified true copy of SECP Certificate of Incorporation.", styles["LegalBullet"]))
    story.append(Paragraph("• <b>Constitutional Documents:</b> Certified Memorandum and Articles of Association (for companies) or Partnership Deed / Form C (for firms).", styles["LegalBullet"]))
    story.append(Paragraph("• <b>Management Register:</b> Latest Form A (Annual Return) and Form 29 evidencing current directors and corporate officers.", styles["LegalBullet"]))
    story.append(Paragraph("• <b>Authorizing Board Resolution:</b> Duly passed resolution of the Board of Directors authorizing the execution of the Letter of Engagement and appointing the authorized signatory.", styles["LegalBullet"]))
    story.append(Paragraph("• <b>Signatory Identification:</b> CNIC or Passport copy of the authorized signatory executing the engagement.", styles["LegalBullet"]))

    story.append(Spacer(1, 6))
    story.append(Paragraph("7. Document Verification & Custody Procedure", styles["SectionHeading"]))
    story.append(Paragraph(
        "7.1. Original documents received for inspection must be recorded on a Document Deposit Receipt (Form DDR-01) signed by the receiving associate. "
        "Original documents are retained in the firm's fireproof vault, while working file binders utilize certified photocopies.",
        styles["LegalBody"],
    ))
    story.append(PageBreak())

    # ---------------- PAGE 4: Engagement, Retainer Invoicing & Escalation ----------------
    story.append(Paragraph("8. Engagement Letter Execution & Retainer Deposit", styles["SectionHeading"]))
    story.append(Paragraph(
        "8.1. Once conflict clearance is granted and documentation is verified, the matter associate prepares the standardized "
        "Letter of Engagement specifying agreed hourly rates and retainer requirements.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "8.2. <b>Required Retainer Deposit:</b> An initial retainer invoice is issued immediately:<br/>"
        "• Family Law Matters: <b>PKR 75,000</b><br/>"
        "• Property Matters: <b>PKR 100,000</b><br/>"
        "• Corporate Advisory (Monthly): <b>PKR 150,000</b>",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "8.3. <b>Standard Rates Applied:</b> Senior Partner (PKR 25,000/hr), Associate (PKR 12,000/hr), Paralegal (PKR 4,000/hr).",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "8.4. <b>Payment Terms:</b> Retainer invoices and monthly billing statements are <b>due within 15 days</b> of issuance. "
        "Accounts unpaid after 15 days incur a <b>2% per month late fee</b>. Payments are accepted via direct wire / IBFT to Allied Bank Limited "
        "or crossed cheque payable to 'Sterling & Rauf Law Associates'.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("9. Staff Escalation Hierarchy & Dispute Handling", styles["SectionHeading"]))
    story.append(Paragraph(
        "9.1. In the event of procedural delays, client grievances, or onboarding complications, staff must adhere to the following escalation protocol:",
        styles["LegalBody"],
    ))

    escalation_data = [
        [Paragraph("Escalation Tier", styles["TableHeader"]), Paragraph("Responsible Authority", styles["TableHeader"]), Paragraph("Resolution Window", styles["TableHeader"]), Paragraph("Trigger Criteria", styles["TableHeader"])],
        [Paragraph("Tier 1: Frontline", styles["TableCellBold"]), Paragraph("Senior Associate", styles["TableCellBold"]), Paragraph("4 business hours", styles["TableCellBold"]), Paragraph("Scheduling conflicts, document submission delays, intake form clarifications.", styles["TableCell"])],
        [Paragraph("Tier 2: Operational", styles["TableCellBold"]), Paragraph("Head of Client Operations", styles["TableCellBold"]), Paragraph("12 business hours", styles["TableCellBold"]), Paragraph("Unresolved billing queries, retainer discrepancies, complex conflict determinations.", styles["TableCell"])],
        [Paragraph("Tier 3: Executive", styles["TableCellBold"]), Paragraph("Managing Partner", styles["TableCellBold"]), Paragraph("24 business hours", styles["TableCellBold"]), Paragraph("Client grievances, ethical dilemmas, breach notifications, engagement termination requests.", styles["TableCell"])],
    ]
    escalation_table = Table(escalation_data, colWidths=[95, 115, 95, 182])
    escalation_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E1B4B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(escalation_table)
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "9.2. <b>Escalation Contacts:</b> Operational concerns may be routed to escalation@sterlingrauf.com or emergency hotline extension 9.",
        styles["LegalBody"],
    ))

    doc.build(story, canvasmaker=NumberedCanvas)


def build_data_policy_pdf(output_path: Path) -> None:
    """Generate Confidentiality_and_Data_Policy.pdf (3 pages minimum)."""
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=60,
        bottomMargin=54,
        invariant=1,
    )
    styles = get_pdf_styles()
    story = []

    # ---------------- PAGE 1: Confidentiality Obligations & Privilege ----------------
    story.append(Paragraph("STERLING & RAUF LAW ASSOCIATES", styles["DocSubtitle"]))
    story.append(Paragraph("Confidentiality, File Retention & Data Security Policy", styles["DocTitle"]))
    story.append(Paragraph("Policy Identifier: POL-SEC-2026 | Applicable to all Partners, Advocates, Staff & Contractors", styles["LegalBody"]))
    story.append(Paragraph("Effective Date: January 1, 2026 | Lahore, Pakistan", styles["LegalBody"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#4F46E5"), spaceAfter=10))

    story.append(Paragraph("1. Statutory Advocate-Client Privilege & Ethical Duties", styles["SectionHeading"]))
    story.append(Paragraph(
        "1.1. <b>Privilege Foundation:</b> The advocate-client relationship is grounded in absolute confidentiality, protected by Article 9 of the "
        "Qanun-e-Shahadat Order, 1984, and the canons of professional conduct issued by the Pakistan Bar Council. All communications, draft pleadings, "
        "negotiation notes, and documentary disclosures made to Sterling & Rauf Law Associates are strictly privileged.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "1.2. <b>Perpetual Obligation:</b> The duty of confidentiality is perpetual. It commences at the moment of initial inquiry and survives the "
        "conclusion of litigation, termination of representation, or decease of a client.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "1.3. <b>Authorized Disclosures:</b> Confidential information may only be disclosed under three narrow conditions:<br/>"
        "• Express, written authorization signed by the client or authorized corporate officer.<br/>"
        "• Disclosures strictly necessary in court pleadings or judicial filings authorized by the client's Vakalatnama.<br/>"
        "• Direct, mandatory statutory order issued by a court of competent jurisdiction after all legal appeals against disclosure are exhausted.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("2. Physical Security & Hard-Copy Handling", styles["SectionHeading"]))
    story.append(Paragraph(
        "2.1. <b>Clean-Desk Environment:</b> All physical case files, court briefs, and documentary evidence must be secured in lockable cabinets "
        "when unattended. Files must never be left exposed in public waiting areas or unattended conference suites.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "2.2. <b>Physical Archive Protection:</b> The firm's central physical archive is equipped with climate-controlled storage, fire suppression "
        "systems, and dual-key RFID access tracking restricted to designated records management personnel.",
        styles["LegalBody"],
    ))
    story.append(PageBreak())

    # ---------------- PAGE 2: Digital Security & 7-Year Retention Schedule ----------------
    story.append(Paragraph("3. Digital Information Security & Encryption Standards", styles["SectionHeading"]))
    story.append(Paragraph(
        "3.1. <b>Encryption at Rest and in Transit:</b> All digital client documents, communication records, and billing data are encrypted at rest "
        "using AES-256 standard and transmitted across encrypted TLS 1.3 channels.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "3.2. <b>Daily Automated Backups:</b> Digital case repositories undergo encrypted daily backups stored across redundant regional data centers. "
        "Backup integrity is verified through weekly restoration tests conducted by our technical systems administrator.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "3.3. <b>Role-Based Access Control (RBAC):</b> Electronic case folders are partitioned by practice group. Paralegals, associates, and external "
        "consultants are granted access solely to matters where their formal assignment is documented in the practice management software.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("4. Statutory 7-Year File Retention & Disposal Schedule", styles["SectionHeading"]))
    story.append(Paragraph(
        "4.1. <b>Mandatory Retention Window:</b> In conformity with professional standards and tax audit regulations, "
        "<b>client files are retained for 7 years after case closure</b>.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "4.2. <b>Closure Reconciliation:</b> The 7-year clock initiates on the date a formal Case Closure Memorandum is approved and any unused retainer "
        "is refunded (within 30 days of closure, subject to the 10% administrative deduction).",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "4.3. <b>Disposal Procedure:</b> Upon expiration of the 7-year retention period:<br/>"
        "• The client of record is sent a final notice offering the return of physical file contents.<br/>"
        "• Unclaimed physical files undergo secure cross-cut destruction with an audited Certificate of Destruction (Form DS-04).<br/>"
        "• Electronic case files and cloud backups are purged using cryptographic erasure algorithms conforming to industry standards.",
        styles["LegalBody"],
    ))
    story.append(PageBreak())

    # ---------------- PAGE 3: Breach Reporting Protocol & Governance ----------------
    story.append(Paragraph("5. Data Breach Notification & Incident Response Protocol", styles["SectionHeading"]))
    story.append(Paragraph(
        "5.1. <b>Definition of Incident:</b> A data security breach includes any confirmed or suspected unauthorized access, alteration, disclosure, "
        "accidental loss, or destruction of confidential client information, whether occurring in physical or digital formats.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "5.2. <b>Mandatory 24-Hour Internal Reporting:</b> Any advocate, staff member, or contractor who discovers or suspects a data security breach "
        "must report the incident internally to the Data Protection Officer and Managing Partner <b>within 24 hours of discovery</b>.",
        styles["LegalBody"],
    ))
    story.append(Paragraph(
        "5.3. <b>Incident Response Lifecycle:</b><br/>"
        "• <b>Hours 0 - 24:</b> Internal incident logging, preliminary containment, isolation of compromised accounts or storage nodes.<br/>"
        "• <b>Hours 24 - 48:</b> Forensic investigation to establish affected client records, exposure vectors, and potential risk to client privilege.<br/>"
        "• <b>Within 72 Hours:</b> If risk assessment indicates potential harm or material breach of privilege, affected clients must be notified in writing "
        "with mitigation recommendations and remediation timelines.",
        styles["LegalBody"],
    ))

    story.append(Paragraph("6. Disciplinary Enforcement & Ethical Compliance", styles["SectionHeading"]))
    story.append(Paragraph(
        "6.1. Failure to adhere to confidentiality protocols or willful neglect in reporting a breach within 24 hours constitutes gross professional misconduct. "
        "Sanctions include immediate termination of employment or partnership expulsion, alongside formal referral to the Punjab Bar Council for disciplinary review.",
        styles["LegalBody"],
    ))

    story.append(Spacer(1, 15))
    story.append(Paragraph("7. Administrative Oversight & Policy Attestation", styles["SectionHeading"]))
    signoff_box = [
        [Paragraph("<b>Supervising Authority:</b>", styles["TableCellBold"]), Paragraph("<b>Internal Reporting Channel:</b>", styles["TableCellBold"])],
        [Paragraph("Managing Partner & Compliance Committee<br/>Sterling & Rauf Law Associates, Lahore", styles["TableCell"]), Paragraph("Direct Email: contact@sterlingrauf.com<br/>Emergency Incident Line: Extension 9", styles["TableCell"])],
    ]
    signoff_table = Table(signoff_box, colWidths=[240, 247])
    signoff_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(signoff_table)

    doc.build(story, canvasmaker=NumberedCanvas)


def build_engagement_letter_docx(output_path: Path) -> None:
    """Generate Client_Engagement_Letter_Template.docx (2+ pages of structured text)."""
    doc = Document()

    # Fixed core properties for deterministic generation
    fixed_dt = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    doc.core_properties.created = fixed_dt
    doc.core_properties.modified = fixed_dt
    doc.core_properties.last_printed = fixed_dt
    doc.core_properties.revision = 1

    # Set margins
    for sec in doc.sections:
        sec.top_margin = Inches(0.8)
        sec.bottom_margin = Inches(0.8)
        sec.left_margin = Inches(0.8)
        sec.right_margin = Inches(0.8)
        # Footer notice on every page
        footer_p = sec.footer.paragraphs[0]
        footer_p.text = FOOTER_NOTICE
        footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer_p.style.font.size = Pt(8.5)
        footer_p.style.font.color.rgb = RGBColor(128, 128, 128)

    # Header / Letterhead
    h1 = doc.add_heading("STERLING & RAUF LAW ASSOCIATES", level=1)
    h1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph("Advocates & Legal Consultants | Lahore, Pakistan")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.style.font.size = Pt(10)
    sub.style.font.color.rgb = RGBColor(79, 70, 229)

    contact_p = doc.add_paragraph(
        "Suite 402-404, Gulberg Executive Heights, Main Boulevard, Gulberg III, Lahore, Pakistan\n"
        "Phone: +92 42 3578 9000 | Email: contact@sterlingrauf.com | Web: www.sterlingrauf.com"
    )
    contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    contact_p.style.font.size = Pt(8.5)
    contact_p.style.font.color.rgb = RGBColor(100, 100, 100)

    doc.add_paragraph("_________________________________________________________________________________")

    doc.add_heading("STANDARD CLIENT ENGAGEMENT LETTER & TERMS OF REPRESENTATION", level=2)

    doc.add_paragraph("Date: [____ / ____ / 2026]")
    doc.add_paragraph("Client Name: [Full Individual Name / Registered Corporate Entity]")
    doc.add_paragraph("Address: [Residential Address / Corporate Principal Office]")
    doc.add_paragraph("Contact Number: [Telephone / Mobile] | Email Address: [Email]")
    doc.add_paragraph("Matter Reference: [Matter Title / File Case Reference Number]")

    doc.add_heading("1. Engagement & Scope of Legal Representation", level=3)
    doc.add_paragraph(
        "1.1. Sterling & Rauf Law Associates ('the Firm') is hereby retained by the undersigned Client ('the Client') to provide legal advisory, "
        "drafting, and advocacy services strictly in connection with the specific matter described above ('the Matter').\n"
        "1.2. The scope of engagement is restricted exclusively to civil, corporate, property, contract, domestic relations, or intellectual property "
        "representation as agreed herein. The Client expressly acknowledges that the Firm does NOT handle criminal defense or immigration matters.\n"
        "1.3. Any expansion of representation beyond the designated scope requires a supplemental written amendment countersigned by a Senior Partner."
    )

    doc.add_heading("2. Conflict of Interest Clearance", level=3)
    doc.add_paragraph(
        "2.1. The Firm confirms that an internal conflict-of-interest check has been completed over the mandatory 2 working days screening period, "
        "and no direct conflict has been identified as of the date hereof.\n"
        "2.2. In accordance with Firm policy, this conflict clearance is valid for 30 calendar days from issuance. Should this Letter remain unexecuted "
        "beyond 30 days, re-screening shall be required prior to commencement of work."
    )

    doc.add_heading("3. Professional Fee Schedule & Hourly Rates", level=3)
    doc.add_paragraph(
        "3.1. Legal services provided on a time-charge basis shall be billed according to the Firm's approved 2026 fee schedule:\n"
        "   • Senior Partner (Barrister Tariq Sterling / Ayesha Rauf): PKR 25,000 per hour\n"
        "   • Associate Advocate: PKR 12,000 per hour\n"
        "   • Paralegal / Legal Assistant: PKR 4,000 per hour\n"
        "3.2. Initial Consultation Credit: If the initial consultation fee of PKR 5,000 was paid prior to signing this Letter, and this agreement is "
        "executed within 7 days of that consultation, the PKR 5,000 consultation fee shall be fully credited towards the initial invoice."
    )

    doc.add_heading("4. Retainer Deposit & Trust Account Administration", level=3)
    doc.add_paragraph(
        "4.1. Prior to commencing work, the Client shall deposit the required advance retainer into the Firm's designated client account:\n"
        "   • Family Law Matters: PKR 75,000 advance retainer\n"
        "   • Property Matters: PKR 100,000 advance retainer\n"
        "   • Corporate Advisory: PKR 150,000 monthly standing retainer\n"
        "4.2. Retainer funds remain client monies held in trust until earned by fee earners or disbursed for approved filing expenses."
    )

    doc.add_page_break()  # Ensure multi-page structure

    doc.add_heading("5. Invoicing Schedules, Payment Terms & Late Fees", level=3)
    doc.add_paragraph(
        "5.1. Itemized invoices are issued monthly, detailing specific services rendered, attending fee earners, hourly increments, and official disbursements.\n"
        "5.2. All invoices are due and payable within 15 days of issuance.\n"
        "5.3. Overdue accounts remaining unpaid after 15 days shall accrue a late fee surcharge of 2% per month on the unpaid balance until full settlement.\n"
        "5.4. Approved Payment Methods: Remittances must be executed via direct wire transfer / Interbank Funds Transfer (IBFT) to Allied Bank Limited "
        "(Account Title: Sterling & Rauf Law Associates) or crossed Account Payee cheque. Cash payments exceeding PKR 20,000 are not accepted."
    )

    doc.add_heading("6. Retainer Refund Policy upon Case Closure", level=3)
    doc.add_paragraph(
        "6.1. Upon formal conclusion or settlement of the Matter, or upon authorized termination of this agreement, any unexpended retainer balance "
        "shall be refunded to the Client within 30 days of case closure.\n"
        "6.2. A standard 10% administrative charge shall be deducted from the unexpended balance to cover closing file reconciliation and accounting auditing."
    )

    doc.add_heading("7. Client Responsibilities & Document Provision", level=3)
    doc.add_paragraph(
        "7.1. The Client agrees to provide candid, truthful disclosures and deliver necessary supporting documents in a timely fashion.\n"
        "7.2. Identification Check: Individual clients must submit a verified copy of CNIC or Passport plus a recent utility bill (within 90 days). "
        "Corporate clients must submit Certificate of Incorporation, Memorandum & Articles of Association, Form A/29, and an authorizing Board Resolution."
    )

    doc.add_heading("8. Operational Hours & Communication Protocols", level=3)
    doc.add_paragraph(
        "8.1. The Firm conducts consultations and operations during official office hours:\n"
        "   • Monday to Friday: 9:30 AM to 5:30 PM (9:30-17:30)\n"
        "   • Saturday: 10:00 AM to 2:00 PM (10:00-14:00)\n"
        "   • Sunday & Public Holidays: Closed\n"
        "8.2. All client emails to contact@sterlingrauf.com shall receive a response within 1 business day."
    )

    doc.add_heading("9. Confidentiality, Data Protection & 7-Year File Retention", level=3)
    doc.add_paragraph(
        "9.1. Advocate-client privilege protects all disclosures under Article 9 of the Qanun-e-Shahadat Order, 1984. Communications are held in strict confidence.\n"
        "9.2. Any internal security breach involving confidential client data must be formally reported within 24 hours under Firm security policy.\n"
        "9.3. Following case resolution, case files are retained in secure archives for 7 years after case closure before confidential destruction."
    )

    doc.add_heading("10. Termination of Representation", level=3)
    doc.add_paragraph(
        "10.1. Either party may terminate this legal representation at any time by providing 14 calendar days prior written notice to the other party.\n"
        "10.2. Upon notice of termination, the Firm shall cease billable activity, prepare the final ledger, and deliver the Client's original documents."
    )

    doc.add_heading("11. Governing Law & Dispute Jurisdiction", level=3)
    doc.add_paragraph(
        "11.1. This agreement is governed by the laws of Pakistan. Any dispute arising out of or in connection with this agreement shall be submitted "
        "to the exclusive jurisdiction of the competent courts of Lahore, Pakistan."
    )

    doc.add_paragraph("\nIN WITNESS WHEREOF, the parties hereto have executed this Engagement Agreement as of the date first above written.\n")

    sig_table = doc.add_table(rows=2, cols=2)
    sig_table.rows[0].cells[0].text = "FOR THE CLIENT:\n\n\n__________________________________\nAuthorized Signature / Thumb Impression\nName:\nCNIC / Passport No.:\nDate:"
    sig_table.rows[0].cells[1].text = "FOR STERLING & RAUF LAW ASSOCIATES:\n\n\n__________________________________\nBarrister Tariq Sterling / Ayesha Rauf\nSenior Partner / Managing Partner\nDate:"

    # Save with normalized zip entry timestamps for deterministic generation
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    fixed_time = (2026, 1, 1, 0, 0, 0)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin:
        with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                zinfo = zipfile.ZipInfo(filename=item.filename, date_time=fixed_time)
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                zout.writestr(zinfo, data)
    output_path.write_bytes(out_buf.getvalue())


def build_client_faq_txt(output_path: Path) -> None:
    """Generate Client_FAQ.txt (UTF-8, 18 English Q&As)."""
    faq_content = """================================================================================
STERLING & RAUF LAW ASSOCIATES - CLIENT FREQUENTLY ASKED QUESTIONS (FAQ)
Office: Suite 402-404, Gulberg Executive Heights, Main Boulevard, Gulberg III, Lahore, Pakistan
Official Contact: Phone: +92 42 3578 9000 | Email: contact@sterlingrauf.com
Note: Fictional demo document - not real legal advice
================================================================================

Q1: What are the official office hours for Sterling & Rauf Law Associates?
A1: Our Lahore office is open Monday to Friday from 9:30 AM to 5:30 PM (9:30-17:30) and Saturday from 10:00 AM to 2:00 PM (10:00-14:00). The firm is closed on Sundays and gazetted public holidays.

Q2: How much does the firm charge for an initial consultation?
A2: The preliminary consultation fee is PKR 5,000 for a 45-minute consultation. However, this entire fee is waived if the client formally executes an engagement agreement within 7 days of the consultation.

Q3: What are the hourly billing rates for legal work?
A3: Hourly rates are structured according to fee-earner seniority: Senior Partner rates are PKR 25,000 per hour; Associate Advocate rates are PKR 12,000 per hour; and Paralegal / Legal Assistant rates are PKR 4,000 per hour.

Q4: What retainer deposits are required before work begins?
A4: Mandatory advance retainers are: Family Law matters require PKR 75,000; Property and Real Estate matters require PKR 100,000; and Corporate Advisory requires a standing monthly retainer of PKR 150,000.

Q5: When are invoices issued, and what is the payment due date?
A5: Billing statements are issued monthly and are due within 15 days of issuance.

Q6: What is the late payment penalty for overdue invoices?
A6: Invoices that remain unpaid after the 15-day due date are subject to a late fee surcharge of 2% per month on the outstanding balance.

Q7: What is the refund policy for unused retainer balances?
A7: Any unused retainer funds are refunded within 30 days of case closure, minus a 10% administrative charge for final ledger reconciliation and archive management.

Q8: How quickly does the firm respond to client inquiries and emails?
A8: All client emails sent to contact@sterlingrauf.com and recorded phone messages are answered within 1 business day.

Q9: What is the conflict-of-interest check procedure, and how long does it take?
A9: Every prospective instruction undergoes a mandatory conflict check against our past, present, and opposing party records. This screening takes 2 working days before any engagement can be confirmed. Cleared conflict checks remain valid for 30 calendar days.

Q10: What practice areas does Sterling & Rauf Law Associates cover?
A10: The firm specializes in six core disciplines: Corporate & Commercial Advisory, Property & Real Estate Law, Family Law & Domestic Relations, Civil Litigation, Contract Drafting & Vetting, and Intellectual Property Protection.

Q11: Are there legal matters that the firm does NOT handle?
A11: Yes, the firm strictly does NOT handle criminal defense or immigration matters under any circumstances. Inquiries relating to criminal bail, trials, foreign visas, or immigration petitions are declined at intake.

Q12: How long are client case files retained after a case concludes?
A12: In compliance with statutory regulations and bar standards, client files are retained for 7 years after case closure, after which they are securely destroyed unless an extension is requested.

Q13: What happens if there is an internal data security breach?
A13: Under our Confidentiality and Data Policy, any breach of confidential client data must be reported internally within 24 hours of discovery, followed by an immediate forensic investigation.

Q14: What fixed-fee transactional packages does the firm offer?
A14: Fixed-fee services include Standard Commercial Contract Review (up to 15 pages) for PKR 35,000; Trademark Registration Application Filing for PKR 45,000 per class (exclusive of government fees); Basic Will and Succession Drafting for PKR 50,000; and Company Incorporation Package for PKR 60,000.

Q15: What payment methods are accepted by the firm?
A15: The firm accepts direct wire transfers and Interbank Funds Transfer (IBFT) to our Allied Bank Limited account (Account Title: Sterling & Rauf Law Associates) and crossed Account Payee Cheques. Cash payments exceeding PKR 20,000 are not accepted.

Q16: What documents must individual clients provide during intake?
A16: Individual clients must submit a clear copy of their original CNIC (or valid Passport for foreign nationals), proof of address via a recent utility bill issued within the last 90 days, and two passport-sized photographs for court Vakalatnama filing.

Q17: What documents are required for corporate client onboarding?
A17: Corporate clients must furnish an SECP Certificate of Incorporation, Memorandum and Articles of Association, latest Form A and Form 29, and a Board Resolution authorizing the signatory to execute the engagement.

Q18: What is the notice period for terminating an engagement?
A18: Either party may terminate representation at any time by providing 14 calendar days written notice.

================================================================================
Fictional demo document - not real legal advice
Sterling & Rauf Law Associates, Lahore, Pakistan
================================================================================
"""
    output_path.write_text(faq_content.strip() + "\n", encoding="utf-8")


def main() -> None:
    """Generate all demo documents and verify their page counts and sizes."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating sample documents into: {OUTPUT_DIR}\n")

    pdf1 = OUTPUT_DIR / "Fee_Schedule_2026.pdf"
    pdf2 = OUTPUT_DIR / "Practice_Areas_Brochure.pdf"
    pdf3 = OUTPUT_DIR / "Client_Intake_SOP.pdf"
    pdf4 = OUTPUT_DIR / "Confidentiality_and_Data_Policy.pdf"
    docx_file = OUTPUT_DIR / "Client_Engagement_Letter_Template.docx"
    txt_file = OUTPUT_DIR / "Client_FAQ.txt"

    build_fee_schedule_pdf(pdf1)
    build_practice_areas_pdf(pdf2)
    build_intake_sop_pdf(pdf3)
    build_data_policy_pdf(pdf4)
    build_engagement_letter_docx(docx_file)
    build_client_faq_txt(txt_file)

    print("Generation complete. Verifying generated files:\n")
    print("=" * 80)
    print(f"{'Filename':<40} | {'Size (KB)':<12} | {'Pages / Details'}")
    print("-" * 80)

    for f in [pdf1, pdf2, pdf3, pdf4, docx_file, txt_file]:
        size_kb = f.stat().st_size / 1024
        if f.suffix == ".pdf":
            pages = NumberedCanvas.page_counts.get(str(f), "N/A")
            details = f"{pages} pages"
        elif f.suffix == ".docx":
            details = "DOCX Template (2+ pages text)"
        elif f.suffix == ".txt":
            details = "UTF-8 Text (18 English Q&As)"
        else:
            details = "N/A"
        print(f"{f.name:<40} | {size_kb:<12.1f} | {details}")

    print("=" * 80)


if __name__ == "__main__":
    main()
