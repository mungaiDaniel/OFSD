"""
PDF Statement Generator for Investment Distributions

This module generates investor statements showing their fund positions,
accrued days, and distributed profits across funds.
"""

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from datetime import datetime
from decimal import Decimal
import io


class PDFStatementGenerator:
    """Generate PDF investment statements grouped by fund"""

    def __init__(self, batch_data, output_path=None):
        """
        Initialize PDF generator.
        
        Args:
            batch_data: dict containing batch info, investments, and distributions
            output_path: Path to save PDF (if None, returns bytes)
        """
        self.batch_data = batch_data
        self.output_path = output_path
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Define custom styles for the PDF"""
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )

        self.heading_style = ParagraphStyle(
            'CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#333333'),
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )

        self.normal_style = ParagraphStyle(
            'CustomNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#333333')
        )

    def generate(self):
        """
        Generate the PDF document.
        
        Returns:
            bytes: PDF content if output_path is None, else writes to file
        """
        if self.output_path:
            doc = SimpleDocTemplate(self.output_path, pagesize=letter)
        else:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter)

        # Build content
        story = []
        
        # Title
        story.append(Paragraph(
            "Investment Statement",
            self.title_style
        ))
        story.append(Spacer(1, 0.2 * inch))

        # Batch Summary
        story.extend(self._build_batch_summary())
        story.append(Spacer(1, 0.2 * inch))

        # Fund Sections
        story.extend(self._build_fund_sections())

        # Build PDF
        doc.build(story)

        if self.output_path:
            return f"PDF saved to {self.output_path}"
        else:
            buffer.seek(0)
            return buffer.getvalue()

    def _build_batch_summary(self):
        """Build batch summary section"""
        content = []
        batch = self.batch_data.get('batch', {})

        summary_data = [
            ['Batch Name', batch.get('batch_name', 'N/A')],
            ['Certificate Number', batch.get('certificate_number', 'N/A')],
            ['Deployment Date', batch.get('date_deployed', 'N/A')],
            ['Expected Close Date', batch.get('expected_close_date', 'N/A')],
            ['Total Principal', f"${self.batch_data.get('total_principal', 0):,.2f}"],
            ['Statement Date', datetime.utcnow().strftime('%Y-%m-%d')]
        ]

        table = Table(summary_data, colWidths=[2.5 * inch, 4 * inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f4f8')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))

        content.append(table)
        return content

    def _build_fund_sections(self):
        """Build sections for each fund"""
        content = []
        investments = self.batch_data.get('investments', [])
        distributions = self.batch_data.get('distributions', [])

        # Group investments by fund
        funds_dict = {}
        for inv in investments:
            fund_name = inv.get('fund_name', 'Default')
            if fund_name not in funds_dict:
                funds_dict[fund_name] = []
            funds_dict[fund_name].append(inv)

        for fund_name in sorted(funds_dict.keys()):
            content.append(PageBreak())
            
            # Fund title
            content.append(Paragraph(
                f"Fund: {fund_name}",
                self.heading_style
            ))
            content.append(Spacer(1, 0.1 * inch))

            # Investments table
            content.extend(self._build_fund_investments_table(fund_name, funds_dict[fund_name]))
            content.append(Spacer(1, 0.15 * inch))

            # Distributions table
            fund_distributions = [d for d in distributions if d.get('fund_name') == fund_name]
            if fund_distributions:
                content.extend(self._build_distributions_table(fund_name, fund_distributions))

        return content

    def _build_fund_investments_table(self, fund_name, investments):
        """Build investments table for a specific fund"""
        content = []
        
        content.append(Paragraph("Investments by Fund", self.heading_style))

        table_data = [
            ['Internal Code', 'Investor Name', 'Amount (USD)', 'Date Deposited', 'Status']
        ]

        for inv in investments:
            table_data.append([
                inv.get('internal_client_code', 'N/A'),
                inv.get('investor_name', 'N/A'),
                f"${float(inv.get('amount_deposited', 0)):,.2f}",
                inv.get('date_deposited', 'N/A'),
                'Active' if inv.get('active', True) else 'Inactive'
            ])

        table = Table(table_data, colWidths=[1.2 * inch, 2 * inch, 1.2 * inch, 1.3 * inch, 0.8 * inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
        ]))

        content.append(table)
        return content

    def _build_distributions_table(self, fund_name, distributions):
        """Build profit distributions table"""
        content = []
        
        content.append(Paragraph("Profit Distributions", self.heading_style))

        table_data = [
            ['Internal Code', 'Investor', 'Days Active', 'Weighted Capital', 'Share %', 'Profit Allocated']
        ]

        total_allocated = Decimal('0.00')

        for dist in distributions:
            allocated = dist.get('profit_allocated', Decimal('0.00'))
            if isinstance(allocated, str):
                allocated = Decimal(allocated)
            
            table_data.append([
                dist.get('internal_client_code', 'N/A'),
                dist.get('investor_name', 'N/A'),
                str(dist.get('days_active', 0)),
                f"${float(dist.get('weighted_capital', 0)):,.2f}",
                f"{float(dist.get('profit_share_percentage', 0)):.2f}%",
                f"${float(allocated):,.2f}"
            ])
            total_allocated += allocated

        # Add total row
        table_data.append([
            '', '', '', '',
            'TOTAL',
            f"${float(total_allocated):,.2f}"
        ])

        table = Table(table_data, colWidths=[1 * inch, 1.5 * inch, 0.9 * inch, 1.3 * inch, 0.9 * inch, 1.2 * inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#D9E1F2')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 1), (-1, -2), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f0f0f0')])
        ]))

        content.append(table)
        return content


def generate_investor_statement_pdf(batch_id, output_path=None):
    """
    Convenience function to generate PDF statement for a batch.
    
    Args:
        batch_id: ID of the batch
        output_path: Optional path to save PDF
    
    Returns:
        bytes or str: PDF bytes or confirmation message
    """
    from app.Batch.model import Batch
    from app.Investments.model import Investment
    from app.Performance.pro_rata_distribution import ProRataDistribution

    try:
        batch = Batch.query.get(batch_id)
        if not batch:
            return False, "Batch not found"

        # Gather data
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
            'distributions': [
                {
                    'investment_id': dist.investment_id,
                    'investor_name': dist.investor_name,
                    'internal_client_code': dist.internal_client_code,
                    'fund_name': dist.fund_name,
                    'days_active': dist.days_active,
                    'weighted_capital': dist.weighted_capital,
                    'profit_share_percentage': dist.profit_share_percentage,
                    'profit_allocated': dist.profit_allocated
                }
                for dist in batch.distributions
            ]
        }

        # Generate PDF
        generator = PDFStatementGenerator(batch_data, output_path)
        result = generator.generate()

        return True, result

    except Exception as e:
        return False, f"Error generating PDF: {str(e)}"
