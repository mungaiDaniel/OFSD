"""
PDF Statement Generator for Investment Distributions

This module generates investor statements showing their fund positions,
accrued days, and distributed profits across funds.
"""

from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from datetime import datetime, timezone
from decimal import Decimal
import io
from typing import Optional, Dict, List, Any
from xml.sax.saxutils import escape

from app.utils.statement_theme import (
    append_branded_footer,
    append_divider_line,
    append_fund_title,
    build_doc_template,
    build_statement_brand_block,
    get_statement_theme,
    resolve_jh_logo_path,
)


class PDFStatementGenerator:
    """Generate PDF investment statements with multiple statement types"""

    STATEMENT_TYPE_DEPOSIT = "deposit"
    STATEMENT_TYPE_MONTHLY = "monthly"
    STATEMENT_TYPE_WITHDRAWAL = "withdrawal"

    def __init__(self, statement_data: Dict[str, Any], output_path: Optional[str] = None):
        self.statement_data = statement_data
        self.output_path = output_path
        self.statement_type = statement_data.get('statement_type', self.STATEMENT_TYPE_MONTHLY)
        fund = statement_data.get('fund', {}) or {}
        fund_name = fund.get('fund_name') or statement_data.get('fund_name')
        self.theme = get_statement_theme([fund_name] if fund_name else [])
        self.jh_logo_path = resolve_jh_logo_path([fund_name] if fund_name else [])
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _hex(self, value: str):
        return colors.HexColor(value)

    def _setup_custom_styles(self):
        """Define custom styles for the PDF"""
        theme = self.theme
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=self._hex(theme.primary),
            spaceAfter=12,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold'
        )

        self.heading_style = ParagraphStyle(
            'CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=self._hex(theme.primary),
            spaceAfter=8,
            fontName='Helvetica-Bold'
        )

        self.fund_title_style = ParagraphStyle(
            'CustomFundTitle',
            parent=self.styles['Heading1'],
            fontSize=13,
            textColor=self._hex(theme.primary),
            spaceAfter=4,
            leading=16,
            fontName='Helvetica-Bold'
        )

        self.normal_style = ParagraphStyle(
            'CustomNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=self._hex('#333333'),
            leading=14
        )

        self.small_style = ParagraphStyle(
            'CustomSmall',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=self._hex(theme.text_muted),
            leading=12
        )
        self.table_value_style = ParagraphStyle(
            'TableValue',
            parent=self.normal_style,
            fontSize=10,
            textColor=self._hex('#333333'),
            leading=12
        )
        self.footer_style = ParagraphStyle(
            'CustomFooter',
            parent=self.normal_style,
            fontSize=9,
            textColor=self._hex(theme.text_muted),
            leading=12,
        )
        self.tagline_style = ParagraphStyle(
            'CustomTagline',
            parent=self.normal_style,
            fontSize=8,
            textColor=self._hex('#333333'),
            leading=11,
        )

    def _format_currency(self, amount: Decimal, currency: str) -> str:
        if currency == "KES":
            return f"KES {float(amount):,.2f}"
        return f"${float(amount):,.2f}"

    def _kv_table_style(self) -> TableStyle:
        theme = self.theme
        return TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), self._hex(theme.label_column_bg)),
            ('TEXTCOLOR', (0, 0), (0, -1), self._hex(theme.primary)),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ])

    def _history_table_style(self) -> TableStyle:
        theme = self.theme
        return TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self._hex(theme.table_header_bg)),
            ('TEXTCOLOR', (0, 0), (-1, 0), self._hex(theme.table_header_text)),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self._hex(theme.row_alt)])
        ])

    def generate(self):
        if self.output_path:
            doc = build_doc_template(self.output_path, self.theme)
        else:
            buffer = io.BytesIO()
            doc = build_doc_template(buffer, self.theme)

        story = []
        if self.statement_type == self.STATEMENT_TYPE_DEPOSIT:
            story.extend(self._build_deposit_statement())
        elif self.statement_type == self.STATEMENT_TYPE_MONTHLY:
            story.extend(self._build_monthly_statement())
        elif self.statement_type == self.STATEMENT_TYPE_WITHDRAWAL:
            story.extend(self._build_withdrawal_statement())
        else:
            raise ValueError(f"Unknown statement type: {self.statement_type}")

        doc.build(story)

        if self.output_path:
            return f"PDF saved to {self.output_path}"
        buffer.seek(0)
        return buffer.getvalue()

    def _build_header_section(self) -> List[Any]:
        content = []
        investor = self.statement_data.get('investor', {})
        share_class = self.statement_data.get('share_class', {})
        fund = self.statement_data.get('fund', {})

        title_text = {
            self.STATEMENT_TYPE_DEPOSIT: "Deposit Confirmation Statement",
            self.STATEMENT_TYPE_MONTHLY: "Monthly Valuation Statement",
            self.STATEMENT_TYPE_WITHDRAWAL: "Withdrawal Statement"
        }.get(self.statement_type, "Investment Statement")

        brand_block = build_statement_brand_block(self.theme, self.jh_logo_path)
        if brand_block is not None:
            content.append(brand_block)
            content.append(Spacer(1, 0.08 * inch))
            append_divider_line(content, self.theme, width=6.5)
            content.append(Spacer(1, 0.10 * inch))

        fund_name = fund.get('fund_name')
        if self.theme.is_jh and fund_name:
            content.append(Paragraph(escape(str(fund_name).upper()), self.fund_title_style))
            content.append(Spacer(1, 0.06 * inch))

        content.append(Paragraph(title_text, self.title_style))
        content.append(Spacer(1, 0.2 * inch))

        header_data = [
            ['Investor Name', Paragraph(escape(str(investor.get('investor_name', 'N/A'))), self.table_value_style)],
            ['Client Code', Paragraph(escape(str(investor.get('internal_client_code', 'N/A'))), self.table_value_style)],
            ['Fund Name', Paragraph(escape(str(fund.get('fund_name', 'N/A'))), self.table_value_style)],
            ['Share Class', Paragraph(escape(f"{share_class.get('class_name', 'N/A')} ({share_class.get('currency', 'USD')})"), self.table_value_style)],
            ['Statement Date', Paragraph(datetime.now(timezone.utc).strftime('%Y-%m-%d'), self.table_value_style)]
        ]

        header_table = Table(header_data, colWidths=[2.5 * inch, 4 * inch])
        header_table.setStyle(self._kv_table_style())
        content.append(header_table)
        content.append(Spacer(1, 0.2 * inch))
        return content

    def _append_footer(self, content: List[Any], disclaimer: str) -> None:
        pdf_styles = {
            "footer": self.footer_style,
            "tagline": self.tagline_style,
        }
        append_branded_footer(
            content,
            self.theme,
            pdf_styles,
            disclaimer,
            f"Generated on: {datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')}",
        )

    def _build_deposit_statement(self) -> List[Any]:
        content = []
        content.extend(self._build_header_section())

        investor = self.statement_data.get('investor', {})
        share_class = self.statement_data.get('share_class', {})
        currency = share_class.get('currency', 'USD')

        content.append(Paragraph("Deposit Details", self.heading_style))

        deposit_data = [
            ['Deposit Amount', self._format_currency(investor.get('amount_deposited', Decimal('0')), currency)],
            ['Transfer Cost', self._format_currency(investor.get('transfer_fee_deducted', Decimal('0')), currency)],
            ['Entry Fee (2%)', self._format_currency(investor.get('entry_fee', Decimal('0')), currency)],
            ['Net Invested', self._format_currency(investor.get('net_invested', Decimal('0')), currency)],
            ['NAV per Share at Deployment', f"{float(investor.get('deployment_nav', 0)):,.6f}"],
            ['Shares Purchased', f"{float(investor.get('shares_purchased', 0)):,.2f}"],
            ['Contract Note Number', investor.get('contract_note', 'N/A')]
        ]

        deposit_table = Table(deposit_data, colWidths=[3 * inch, 3.5 * inch])
        deposit_table.setStyle(self._kv_table_style())
        content.append(deposit_table)
        content.append(Spacer(1, 0.3 * inch))

        self._append_footer(
            content,
            "<b>Disclaimer:</b> This statement confirms receipt of your deposit. Investment values may fluctuate. "
            "Please retain this document for your records.",
        )
        return content

    def _build_monthly_statement(self) -> List[Any]:
        content = []
        content.extend(self._build_header_section())

        share_class = self.statement_data.get('share_class', {})
        currency = share_class.get('currency', 'USD')

        content.append(Paragraph("Current Position", self.heading_style))

        position_data = [
            ['Shares Held', f"{float(self.statement_data.get('shares_held', 0)):,.2f}"],
            ['Previous NAV', f"{float(self.statement_data.get('previous_nav', 0)):,.6f}"],
            ['Current NAV', f"{float(self.statement_data.get('current_nav', 0)):,.6f}"],
            ['Performance %', f"{float(self.statement_data.get('performance_pct', 0)):,.2f}%"],
            ['Current Market Value', self._format_currency(self.statement_data.get('current_value', Decimal('0')), currency)]
        ]

        position_table = Table(position_data, colWidths=[3 * inch, 3.5 * inch])
        position_table.setStyle(self._kv_table_style())
        content.append(position_table)
        content.append(Spacer(1, 0.2 * inch))

        if self.statement_data.get('valuation_history'):
            content.append(Paragraph("Historical Valuations", self.heading_style))

            history_data = [['Date', 'NAV', 'Value']]
            for valuation in self.statement_data['valuation_history']:
                history_data.append([
                    valuation.get('date', 'N/A'),
                    f"{float(valuation.get('nav', 0)):,.6f}",
                    self._format_currency(valuation.get('value', Decimal('0')), currency)
                ])

            history_table = Table(history_data, colWidths=[1.5 * inch, 2.5 * inch, 2.5 * inch])
            history_table.setStyle(self._history_table_style())
            content.append(history_table)
            content.append(Spacer(1, 0.2 * inch))

        if self.statement_data.get('transaction_history'):
            content.append(Paragraph("Transaction History", self.heading_style))

            transaction_data = [['Date', 'Type', 'Amount']]
            for transaction in self.statement_data['transaction_history']:
                transaction_data.append([
                    transaction.get('date', 'N/A'),
                    transaction.get('type', 'N/A'),
                    self._format_currency(transaction.get('amount', Decimal('0')), currency)
                ])

            transaction_table = Table(transaction_data, colWidths=[1.5 * inch, 2 * inch, 2.5 * inch])
            transaction_table.setStyle(self._history_table_style())
            content.append(transaction_table)

        return content

    def _build_withdrawal_statement(self) -> List[Any]:
        content = []
        content.extend(self._build_header_section())

        share_class = self.statement_data.get('share_class', {})
        currency = share_class.get('currency', 'USD')

        content.append(Paragraph("Withdrawal Details", self.heading_style))

        withdrawal_data = [
            ['Shares Redeemed', f"{float(self.statement_data.get('shares_redeemed', 0)):,.2f}"],
            ['Redemption NAV', f"{float(self.statement_data.get('redemption_nav', 0)):,.6f}"],
            ['Gross Proceeds', self._format_currency(self.statement_data.get('gross_proceeds', Decimal('0')), currency)],
            ['Transfer Cost', self._format_currency(self.statement_data.get('transfer_cost', Decimal('0')), currency)],
            ['Exit Fee', self._format_currency(self.statement_data.get('exit_fee', Decimal('0')), currency)],
            ['Net Withdrawal', self._format_currency(self.statement_data.get('net_withdrawal', Decimal('0')), currency)]
        ]

        withdrawal_table = Table(withdrawal_data, colWidths=[3 * inch, 3.5 * inch])
        withdrawal_table.setStyle(self._kv_table_style())
        content.append(withdrawal_table)
        content.append(Spacer(1, 0.2 * inch))

        if self.statement_data.get('remaining_shares', 0) > 0:
            content.append(Paragraph("Remaining Position", self.heading_style))

            remaining_data = [
                ['Shares Remaining', f"{float(self.statement_data.get('remaining_shares', 0)):,.2f}"],
                ['Current Value', self._format_currency(self.statement_data.get('remaining_value', Decimal('0')), currency)]
            ]

            remaining_table = Table(remaining_data, colWidths=[3 * inch, 3.5 * inch])
            remaining_table.setStyle(self._kv_table_style())
            content.append(remaining_table)

        return content


def generate_deposit_statement_pdf(statement_data, output_path=None):
    statement_data['statement_type'] = PDFStatementGenerator.STATEMENT_TYPE_DEPOSIT
    generator = PDFStatementGenerator(statement_data, output_path)
    return generator.generate()


def generate_monthly_statement_pdf(statement_data, output_path=None):
    statement_data['statement_type'] = PDFStatementGenerator.STATEMENT_TYPE_MONTHLY
    generator = PDFStatementGenerator(statement_data, output_path)
    return generator.generate()


def generate_withdrawal_statement_pdf(statement_data, output_path=None):
    statement_data['statement_type'] = PDFStatementGenerator.STATEMENT_TYPE_WITHDRAWAL
    generator = PDFStatementGenerator(statement_data, output_path)
    return generator.generate()


def generate_investor_statement_pdf(batch_id, output_path=None):
    from app.Batch.model import Batch
    from app.Investments.model import Investment, EpochLedger

    try:
        from app.database.database import db
        batch = db.session.get(Batch, batch_id)
        if not batch:
            return False, "Batch not found"

        batch_data = {
            'batch': {
                'id': batch.id,
                'batch_name': batch.batch_name,
                'certificate_number': batch.certificate_number,
                'date_deployed': batch.date_deployed.isoformat(),
                'expected_close_date': batch.expected_close_date.isoformat()
            },
            'total_principal': sum(float(inv.amount_deposited) for inv in batch.investments),
            'investments': [
                {
                    'id': inv.id,
                    'investor_name': inv.investor_name,
                    'internal_client_code': inv.internal_client_code,
                    'amount_deposited': inv.amount_deposited,
                    'date_deposited': inv.date_deposited.isoformat(),
                    'fund_name': inv.fund_name,
                    'active': inv.active
                }
                for inv in batch.investments
            ],
            'distributions': []
        }

        distributions = []
        for ledger, inv in db.session.query(EpochLedger, Investment).join(
            Investment, Investment.internal_client_code == EpochLedger.internal_client_code
        ).filter(
            Investment.batch_id == batch_id
        ).all():
            distributions.append({
                'investor_name': getattr(inv, 'investor_name', 'Client'),
                'internal_client_code': ledger.internal_client_code,
                'fund_name': ledger.fund_name,
                'weighted_capital': ledger.start_balance,
                'profit_share_percentage': 0,
                'profit_allocated': ledger.profit
            })
        batch_data['distributions'] = distributions
        batch_data['total_profit'] = sum(float(d['profit_allocated']) for d in batch_data['distributions'])

        generator = PDFStatementGenerator(batch_data, output_path)
        result = generator.generate()
        return True, result

    except Exception as e:
        return False, f"Error generating PDF: {str(e)}"
