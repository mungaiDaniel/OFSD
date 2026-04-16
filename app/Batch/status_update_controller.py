import logging
from datetime import datetime, timezone
from decimal import Decimal
from app.utils.email_service import EmailService

logger = logging.getLogger(__name__)

class StatusUpdateController:
    """
    Dedicated controller for managing Batch progress tracker stages 
    and triggering asynchronous status-driven investor emails.
    """

    @classmethod
    def _parse_date_only(cls, raw_value):
        if raw_value is None:
            return None
        text = str(raw_value).strip()
        if not text:
            return None
        date_part = text[:10]
        return datetime.strptime(date_part, "%Y-%m-%d")

    @classmethod
    def handle_status_transition(cls, batch, data, session):
        """
        Detects changes in batch fields and triggers appropriate stage-based side effects.
        
        Transitions:
        - Stage 2 (Transferred): is_transferred False -> True
        - Stage 3 (Active): date_deployed set OR deployment_confirmed True
            * Applies pro-rata transaction cost deduction to all investors in batch
        """
        old_is_transferred = batch.is_transferred
        old_is_active = batch.is_active or batch.deployment_confirmed

        # 1. Update fields from incoming data
        if 'is_transferred' in data:
            batch.is_transferred = bool(data['is_transferred'])
        
        # 2. Handle transaction costs
        if 'transaction_cost' in data:
            batch.transaction_cost = Decimal(str(data['transaction_cost']))
        
        if 'transfer_transaction_cost' in data:
            batch.transfer_transaction_cost = Decimal(str(data['transfer_transaction_cost']))
        transfer_entry_fee_percent = Decimal(str(data.get('entry_fee_percentage', data.get('transfer_entry_fee_percent', 0)) or 0))
        
        if 'date_deployed' in data and data['date_deployed']:
            try:
                batch.date_deployed = cls._parse_date_only(data['date_deployed'])
                # Deployment date implies confirmation and active status in this workflow
                batch.deployment_confirmed = True
                batch.is_active = True
            except ValueError:
                logger.warning(f"Invalid date format for batch {batch.id}: {data['date_deployed']}")

        if 'deployment_confirmed' in data:
            batch.deployment_confirmed = bool(data['deployment_confirmed'])
            if batch.deployment_confirmed:
                batch.is_active = True

        if 'is_active' in data:
            batch.is_active = bool(data['is_active'])

        # 3. Apply pro-rata transaction cost deductions
        new_is_active = batch.is_active or batch.deployment_confirmed
        if new_is_active and not old_is_active and batch.date_deployed is not None:
            cls._apply_transaction_cost_deduction(batch, session)
        
        new_is_transferred = batch.is_transferred
        if new_is_transferred and not old_is_transferred:
            deduction_summary = cls._apply_transfer_cost_deduction(
                batch,
                session,
                transfer_cost_total=batch.transfer_transaction_cost,
                entry_fee_percent=transfer_entry_fee_percent,
            )
            batch.transfer_transaction_cost = Decimal(str(deduction_summary["total_transaction_fee_usd"]))

        # 4. Persist state
        session.commit()

        # 5. Trigger Stage-based Emails (Asynchronous)
        
        # Stage 2: Offshore Transfer
        if batch.is_transferred and not old_is_transferred:
            logger.info(f"Triggering Stage 2 Emails for Batch {batch.id}")
            EmailService.send_offshore_transfer_batch(batch, trigger_source="batch.update_status.stage_2_transfer")
            batch.stage = 2
            session.commit()

        # Stage 3: Investment Active
        if new_is_active and not old_is_active and batch.date_deployed is not None:
            logger.info(f"Triggering Stage 3 Emails for Batch {batch.id}")
            EmailService.send_investment_active_batch(batch, trigger_source="batch.update_status.stage_3_deploy")
            batch.stage = 3
            session.commit()

    @classmethod
    def _apply_transaction_cost_deduction(cls, batch, session):
        """
        Apply pro-rata transaction cost deduction to all investors in the batch.
        
        Calculation:
        - Cost Per Investor = Total Transaction Cost / Number of Investors
        - New Principal = Original Deposit Amount - Cost Per Investor
        
        Updates the Investment model's deployment_fee_deducted field for each investor.
        """
        from app.Investments.model import Investment
        
        transaction_cost = Decimal(str(batch.transaction_cost or 0))
        
        if transaction_cost <= 0:
            logger.info(f"No transaction cost to deduct for batch {batch.id}")
            return
        
        # Get all investments in this batch
        investments = session.query(Investment).filter(
            Investment.batch_id == batch.id
        ).all()
        
        if not investments:
            logger.warning(f"No investments found for batch {batch.id}")
            return
        
        investor_count = len(investments)
        cost_per_investor = transaction_cost / Decimal(str(investor_count))
        
        logger.info(
            f"Batch {batch.id}: Deducting ${transaction_cost} across {investor_count} investors "
            f"(${cost_per_investor} per investor)"
        )
        
        # Apply deduction to each investor
        for investment in investments:
            original_deposit = Decimal(str(investment.amount_deposited))
            investment.deployment_fee_deducted = cost_per_investor
            new_principal = original_deposit - cost_per_investor
            
            logger.info(
                f"  Investor {investment.internal_client_code}: "
                f"${original_deposit} - ${cost_per_investor} = ${new_principal}"
            )
            
            session.add(investment)
        
        session.commit()
        logger.info(f"Transaction cost deduction completed for batch {batch.id}")

    @classmethod
    def _apply_transfer_cost_deduction(
        cls,
        batch,
        session,
        transfer_cost_total=None,
        entry_fee_percent=0,
    ):
        """
        Apply two-stage transfer deductions to all investors in the batch.

        Order of operations:
        A) transaction_fee_usd = total_transaction_cost * investor_weight
           net_after_transaction = amount_deposited - transaction_fee_usd
        B) entry_fee_usd = net_after_transaction * entry_fee_percent
           main_balance = net_after_transaction - entry_fee_usd
        """
        from app.Investments.model import Investment

        transfer_cost = Decimal(str(transfer_cost_total if transfer_cost_total is not None else (batch.transfer_transaction_cost or 0)))
        entry_fee_ratio = Decimal(str(entry_fee_percent or 0)) / Decimal("100")

        # Get all investments in this batch
        investments = session.query(Investment).filter(
            Investment.batch_id == batch.id
        ).all()
        
        if not investments:
            logger.warning(f"No investments found for batch {batch.id}")
            return {"total_transaction_fee_usd": Decimal("0.00"), "total_entry_fee_usd": Decimal("0.00"), "total_main_balance": Decimal("0.00")}

        total_principal = sum(Decimal(str(inv.amount_deposited or 0)) for inv in investments)
        if total_principal <= 0:
            logger.warning(f"Batch {batch.id}: total principal is zero; skipping weighted allocation")
            return {"total_transaction_fee_usd": Decimal("0.00"), "total_entry_fee_usd": Decimal("0.00"), "total_main_balance": Decimal("0.00")}

        logger.info(
            f"Batch {batch.id}: Two-stage transfer deduction | "
            f"transaction_total=${transfer_cost}, entry_fee_percent={entry_fee_percent}% "
            f"across principal=${total_principal} and investors={len(investments)}"
        )

        allocated_total = Decimal("0.00")
        quant = Decimal("0.01")
        total_entry_fee = Decimal("0.00")
        total_main_balance = Decimal("0.00")

        for idx, investment in enumerate(investments):
            investor_principal = Decimal(str(investment.amount_deposited or 0))
            weight = investor_principal / total_principal if total_principal > 0 else Decimal("0")

            # Allocate rounded cents; final row gets remainder to keep totals exact.
            if idx == len(investments) - 1:
                investor_fee = (transfer_cost - allocated_total).quantize(quant)
            else:
                investor_fee = (transfer_cost * weight).quantize(quant)
                allocated_total += investor_fee

            # Guard against edge-case negatives from remainder rounding.
            if investor_fee < Decimal("0"):
                investor_fee = Decimal("0.00")

            net_after_transaction = investor_principal - investor_fee
            if net_after_transaction < Decimal("0"):
                net_after_transaction = Decimal("0.00")

            entry_fee_usd = (net_after_transaction * entry_fee_ratio).quantize(quant)
            if entry_fee_usd < Decimal("0"):
                entry_fee_usd = Decimal("0.00")

            investment.transfer_fee_deducted = investor_fee      # transaction_fee_usd
            investment.deployment_fee_deducted = entry_fee_usd   # entry_fee_usd
            if batch.is_transferred and investment.date_transferred is None:
                investment.date_transferred = datetime.now(timezone.utc)

            total_entry_fee += entry_fee_usd
            total_main_balance += Decimal(str(investment.net_principal or 0))

            logger.info(
                f"  Investor {investment.internal_client_code}: principal=${investor_principal} "
                f"weight={float(weight) * 100:.4f}% transaction_fee=${investor_fee} "
                f"entry_fee=${entry_fee_usd} "
                f"net=${investment.net_principal}"
            )
            session.add(investment)
        
        session.commit()
        logger.info(f"Transfer cost deduction completed for batch {batch.id}")
        return {
            "total_transaction_fee_usd": transfer_cost,
            "total_entry_fee_usd": total_entry_fee.quantize(quant),
            "total_main_balance": total_main_balance.quantize(quant),
        }
