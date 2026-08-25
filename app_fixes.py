from flask import jsonify

import app_v3

app = app_v3.app
get_db = app_v3.get_db
token_required = app_v3.token_required


@token_required
def report_analytics_fixed():
    with get_db() as db, db.cursor() as cur:
        cur.execute("select coalesce(sum(invoice_amount),0)::bigint invoice,coalesce(sum(received_amount),0)::bigint received,coalesce(sum(company_share_amount),0)::bigint company_share,coalesce(sum(customer_balance),0)::bigint customer_balance,count(*)::int services from service_visits")
        totals = app_v3.row_json(cur.fetchone())
        cur.execute("select coalesce(sum(amount),0)::bigint expenses from expenses")
        expenses = cur.fetchone()["expenses"]
        cur.execute("select coalesce(sum(amount),0)::bigint settled from company_settlements")
        settled = cur.fetchone()["settled"]

        cur.execute("""
            select date_trunc('month',coalesce(visited_at,created_at) at time zone 'Asia/Tehran')::date as report_month,
                   coalesce(sum(received_amount),0)::bigint received,
                   coalesce(sum(company_share_amount),0)::bigint company_share,
                   count(*)::int services
            from service_visits
            where coalesce(visited_at,created_at)>=now()-interval '15 months'
            group by 1 order by 1
        """)
        months = []
        for row in cur.fetchall():
            item = app_v3.row_json(row)
            item["month"] = item.pop("report_month")
            months.append(item)

        cur.execute("""
            select date_trunc('month',expense_date at time zone 'Asia/Tehran')::date as report_month,
                   coalesce(sum(amount),0)::bigint expenses
            from expenses
            where expense_date>=now()-interval '15 months'
            group by 1 order by 1
        """)
        expense_map = {str(row["report_month"]): row["expenses"] for row in cur.fetchall()}
        for month in months:
            month["expenses"] = expense_map.get(str(month["month"]), 0)
            month["net_profit"] = month["received"] - month["company_share"] - month["expenses"]

        cur.execute("select coalesce(service_type,'نامشخص') service_type,count(*)::int count,coalesce(sum(received_amount),0)::bigint received from service_visits group by service_type order by received desc limit 10")
        service_types = [app_v3.row_json(r) for r in cur.fetchall()]

    totals["expenses"] = expenses
    totals["net_profit"] = totals["received"] - totals["company_share"] - expenses
    totals["settled_company"] = settled
    totals["company_due"] = max(totals["company_share"] - settled, 0)
    return jsonify({"totals": totals, "months": months, "service_types": service_types})


app.view_functions["report_analytics"] = report_analytics_fixed
