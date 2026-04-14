from main import create_app
from config import DevelopmentConfig
from app.database.database import db
from app.Investments.model import Investment, EpochLedger, Withdrawal
from app.Batch.core_fund import CoreFund
from sqlalchemy import func, or_, and_
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone

app = create_app(config_filename=DevelopmentConfig)

def q2(v):
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def chk(actual, expected):
    return "OK" if abs(float(actual) - float(expected)) < 0.02 else "MISMATCH !!!"

# Gemini's stated figures
GEMINI = {
    "Axiom": dict(june_close=165418.80, wds=24000.00, net_base=141418.80, profit=3464.76, ho=144883.56),
    "Atium": dict(june_close=109203.20, wds=30000.00, net_base= 79203.20, profit=1093.00, ho= 80296.20),
}

with app.app_context():
    JUL_START = datetime(2026, 7,  1, tzinfo=timezone.utc)
    JUL_END   = datetime(2026, 7, 31, tzinfo=timezone.utc)
    JUN_END   = datetime(2026, 6, 30, tzinfo=timezone.utc)
    RATES     = {"Axiom": Decimal("0.0245"), "Atium": Decimal("0.0138")}

    print("ALL WITHDRAWALS IN DB:")
    for w in db.session.query(Withdrawal).all():
        print(f"  [{w.internal_client_code}] {w.fund_name} | amt=${float(w.amount):.2f} | status={w.status} | date={w.date_withdrawn}")
    print("="*60)

    grand_ho = Decimal("0")

    for fname, rate in RATES.items():
        core = db.session.query(CoreFund).filter(
            func.lower(CoreFund.fund_name) == fname.lower()
        ).first()
        if not core:
            print("[" + fname + "] *** NOT FOUND ***")
            continue

        # 1. June closing balance (latest epoch <= Jun 30)
        latest_subq = db.session.query(
            EpochLedger.internal_client_code,
            func.max(EpochLedger.epoch_end).label("max_end"),
        ).filter(
            func.lower(EpochLedger.fund_name) == fname.lower(),
            EpochLedger.epoch_end <= JUN_END,
        ).group_by(EpochLedger.internal_client_code).subquery()

        june_rows = db.session.query(EpochLedger).join(
            latest_subq,
            (EpochLedger.internal_client_code == latest_subq.c.internal_client_code)
            & (EpochLedger.epoch_end == latest_subq.c.max_end)
            & (func.lower(EpochLedger.fund_name) == fname.lower()),
        ).all()

        june_closing = sum((Decimal(str(r.end_balance)) for r in june_rows), Decimal("0"))

        # 2. Fresh investors (no epoch at all)
        codes_in_epoch = {r.internal_client_code for r in june_rows}
        if codes_in_epoch:
            fresh_invs = db.session.query(Investment).filter(
                Investment.fund_id == core.id,
                ~Investment.internal_client_code.in_(codes_in_epoch)
            ).all()
        else:
            fresh_invs = db.session.query(Investment).filter(
                Investment.fund_id == core.id
            ).all()
        fresh_capital = sum((Decimal(str(i.amount_deposited)) for i in fresh_invs), Decimal("0"))

        # 3. July Approved withdrawals
        july_wd_rows = db.session.query(Withdrawal).filter(
            Withdrawal.status == "Approved",
            Withdrawal.date_withdrawn >= JUL_START,
            Withdrawal.date_withdrawn <= JUL_END,
            or_(
                Withdrawal.fund_id == core.id,
                and_(Withdrawal.fund_id.is_(None),
                     func.lower(Withdrawal.fund_name) == fname.lower()),
            ),
        ).all()
        july_wds = sum((Decimal(str(w.amount)) for w in july_wd_rows), Decimal("0"))

        # 4. Compute
        net_base   = q2(june_closing + fresh_capital - july_wds)
        profit     = q2(net_base * rate)
        net_aum    = q2(net_base + profit)
        head_total = q2(net_aum + july_wds)
        grand_ho  += head_total

        g = GEMINI[fname]
        sep = "-" * 60

        print("")
        print("=" * 60)
        print("  " + fname.upper() + " - JULY 2025  (rate: " + str(float(rate) * 100) + "%)")
        print("=" * 60)
        print("  " + sep)
        print("  Field                                DB Value     Gemini     Status")
        print("  " + sep)

        jc_str = "${:>12,.2f}".format(float(june_closing))
        gc_str = "${:>12,.2f}".format(g["june_close"])
        print("  June Closing Balance         " + jc_str + "  " + gc_str + "  " + chk(june_closing, g["june_close"]))

        if fresh_capital > 0:
            fc_str = "${:>12,.2f}".format(float(fresh_capital))
            print("  Fresh Capital (no epoch)     " + fc_str + "  (not in Gemini)")

        wd_str  = "${:>12,.2f}".format(float(july_wds))
        gwd_str = "${:>12,.2f}".format(g["wds"])
        print("  July Withdrawals            (" + wd_str + ") (" + gwd_str + ") " + chk(july_wds, g["wds"]))

        nb_str  = "${:>12,.2f}".format(float(net_base))
        gnb_str = "${:>12,.2f}".format(g["net_base"])
        print("  Net Invested Base            " + nb_str + "  " + gnb_str + "  " + chk(net_base, g["net_base"]))

        pr_str  = "${:>12,.2f}".format(float(profit))
        gpr_str = "${:>12,.2f}".format(g["profit"])
        print("  Profit                       " + pr_str + "  " + gpr_str + "  " + chk(profit, g["profit"]))

        ho_str  = "${:>12,.2f}".format(float(head_total))
        gho_str = "${:>12,.2f}".format(g["ho"])
        print("  HEAD OFFICE TOTAL  >>>       " + ho_str + "  " + gho_str + "  " + chk(head_total, g["ho"]))
        print("  " + sep)

        print("  Investors with June epoch: " + str(len(june_rows)))
        print("  July Approved WD records:  " + str(len(july_wd_rows)))

        if july_wd_rows:
            print("  Withdrawal detail:")
            for w in july_wd_rows:
                line = "    [" + str(w.internal_client_code) + "]  $" + "{:,.2f}".format(float(w.amount))
                line += "  status=" + str(w.status)
                line += "  date=" + str(w.date_withdrawn)[:10]
                print(line)

        if june_rows:
            print("  Per-investor July projection:")
            for r in sorted(june_rows, key=lambda x: x.internal_client_code):
                wd_amt = Decimal("0")
                for w in july_wd_rows:
                    if w.internal_client_code == r.internal_client_code:
                        wd_amt += Decimal(str(w.amount))
                base_i   = q2(Decimal(str(r.end_balance)) - wd_amt)
                profit_i = q2(base_i * rate)
                end_i    = q2(base_i + profit_i)
                wd_disp = "(" + "{:,.2f}".format(float(wd_amt)) + ")" if wd_amt else "none"
                line  = "    " + str(r.internal_client_code).ljust(22)
                line += "  june=${:,.2f}".format(float(r.end_balance))
                line += "  wd=" + wd_disp
                line += "  base=${:,.2f}".format(float(base_i))
                line += "  profit=${:,.2f}".format(float(profit_i))
                line += "  july_end=${:,.2f}".format(float(end_i))
                print(line)

    print("")
    print("=" * 60)
    print("  COMBINED JULY HEAD OFFICE TOTAL")
    print("=" * 60)
    gemini_combined = 144883.56 + 80296.20
    db_str = "${:>14,.2f}".format(float(grand_ho))
    gem_str = "${:>14,.2f}".format(gemini_combined)
    print("  DB Calculated:  " + db_str)
    print("  Gemini Stated:  " + gem_str + "  " + chk(grand_ho, gemini_combined))
    print("=" * 60)
