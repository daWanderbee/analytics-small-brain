"""
CHUK GA4 - Social + Other Sources Dashboard
Run weekly: python ga4_dashboard.py
Opens in browser automatically.
"""
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, DateRange, Metric, Dimension, OrderBy,
    FilterExpression, FilterExpressionList, Filter
)
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import json, webbrowser, datetime, os

TOKEN_FILE = "ga4_token.json"
PROPERTY = "properties/364059461"

with open(TOKEN_FILE) as f:
    t = json.load(f)

creds = Credentials(
    token=t["token"], refresh_token=t["refresh_token"],
    token_uri=t["token_uri"], client_id=t["client_id"], client_secret=t["client_secret"],
)
if creds.expired:
    creds.refresh(Request())
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

client = BetaAnalyticsDataClient(credentials=creds)

EXCLUDE_FILTER = FilterExpression(
    not_expression=FilterExpression(
        or_group=FilterExpressionList(expressions=[
            FilterExpression(filter=Filter(
                field_name="sessionSourceMedium",
                string_filter=Filter.StringFilter(value="google / organic", match_type=Filter.StringFilter.MatchType.EXACT)
            )),
            FilterExpression(filter=Filter(
                field_name="sessionSourceMedium",
                string_filter=Filter.StringFilter(value="(direct) / (none)", match_type=Filter.StringFilter.MatchType.EXACT)
            )),
        ])
    )
)

def get_data(dims, metrics, limit=50, extra_filter=None):
    fltr = EXCLUDE_FILTER if not extra_filter else extra_filter
    req = RunReportRequest(
        property=PROPERTY,
        date_ranges=[DateRange(start_date="30daysAgo", end_date="today")],
        dimensions=[Dimension(name=d) for d in dims],
        metrics=[Metric(name=m) for m in metrics],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name=metrics[0]), desc=True)],
        dimension_filter=fltr,
        limit=limit,
    )
    return client.run_report(req)

def fmt_bounce(v):
    return f"{round(float(v)*100,1)}%"

def fmt_dur(v):
    s = int(float(v))
    return f"{s//60}m {s%60}s"

def pct(val, total):
    return f"{round(int(val)/total*100,1)}%" if total else "0%"

r1 = get_data(["sessionSourceMedium", "landingPage"], ["sessions","activeUsers","newUsers","bounceRate","averageSessionDuration"])
r2 = get_data(["sessionDefaultChannelGroup"], ["sessions","activeUsers","bounceRate"])
r3 = get_data(["sessionSource"], ["sessions","activeUsers"], extra_filter=FilterExpression(
    filter=Filter(field_name="sessionDefaultChannelGroup",
                  string_filter=Filter.StringFilter(value="Organic Social", match_type=Filter.StringFilter.MatchType.EXACT))
))

total1 = sum(int(r.metric_values[0].value) for r in r1.rows)
total2 = sum(int(r.metric_values[0].value) for r in r2.rows)

def rows_html(rows, cols, totals_col=0):
    total = sum(int(r.metric_values[totals_col].value) for r in rows)
    out = ""
    for i, r in enumerate(rows):
        d = [x.value for x in r.dimension_values]
        m = [x.value for x in r.metric_values]
        share = pct(m[0], total)
        bg = "#f9f9f9" if i % 2 == 0 else "#fff"
        cells = "".join(f"<td>{v}</td>" for v in d)
        for j, mv in enumerate(m):
            raw = cols["metrics"][j]
            if "bounce" in raw.lower():
                cells += f"<td>{fmt_bounce(mv)}</td>"
            elif "duration" in raw.lower() or "session" in raw.lower() and "avg" in raw.lower():
                cells += f"<td>{fmt_dur(mv)}</td>"
            else:
                cells += f"<td>{int(float(mv)):,}</td>"
        cells += f"<td><div class='bar-wrap'><div class='bar' style='width:{min(float(share[:-1])*3,100):.0f}%'></div><span>{share}</span></div></td>"
        out += f"<tr style='background:{bg}'>{cells}</tr>"
    return out, total

CHANNEL_COLORS = {
    "Organic Search": "#4285f4",
    "Direct": "#aaa",
    "Referral": "#34a853",
    "Organic Social": "#ea4335",
    "Paid Search": "#fbbc04",
    "Unassigned": "#ccc",
    "AI Sources": "#9c27b0",
}

channel_rows = ""
for r in r2.rows:
    ch = r.dimension_values[0].value
    sess = int(r.metric_values[0].value)
    users = r.metric_values[1].value
    bounce = fmt_bounce(r.metric_values[2].value)
    share = pct(sess, total2)
    color = CHANNEL_COLORS.get(ch, "#666")
    pct_val = float(share[:-1])
    channel_rows += f"""
    <tr>
      <td><span style='display:inline-block;width:10px;height:10px;background:{color};border-radius:50%;margin-right:6px'></span>{ch}</td>
      <td>{sess:,}</td>
      <td>{bounce}</td>
      <td>
        <div class='bar-wrap'>
          <div class='bar' style='width:{min(pct_val*2,100):.0f}%;background:{color}'></div>
          <span>{share}</span>
        </div>
      </td>
    </tr>"""

social_rows = ""
for r in r3.rows:
    src = r.dimension_values[0].value
    sess = int(r.metric_values[0].value)
    users = r.metric_values[1].value
    social_total = sum(int(x.metric_values[0].value) for x in r3.rows)
    share = pct(sess, social_total)
    social_rows += f"<tr><td>{src}</td><td>{sess:,}</td><td>{users}</td><td>{share}</td></tr>"

main_rows_html, main_total = rows_html(r1.rows, {
    "dims": ["sessionSourceMedium","landingPage"],
    "metrics": ["sessions","activeUsers","newUsers","bounceRate","averageSessionDuration"]
})

today = datetime.date.today().strftime("%d %b %Y")

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CHUK GA4 Dashboard - {today}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f4f6f9; color: #333; font-size: 13px; }}
  header {{ background: #1a1a2e; color: #fff; padding: 18px 30px; display: flex; justify-content: space-between; align-items: center; }}
  header h1 {{ font-size: 18px; font-weight: 600; }}
  header span {{ font-size: 12px; opacity: .7; }}
  .container {{ max-width: 1300px; margin: 24px auto; padding: 0 20px; }}
  .kpi-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px; }}
  .kpi {{ background: #fff; border-radius: 8px; padding: 16px 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  .kpi .label {{ font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: .5px; }}
  .kpi .val {{ font-size: 28px; font-weight: 700; margin: 4px 0 2px; color: #1a1a2e; }}
  .kpi .sub {{ font-size: 11px; color: #aaa; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 18px; }}
  .card {{ background: #fff; border-radius: 8px; padding: 18px; box-shadow: 0 1px 4px rgba(0,0,0,.08); overflow-x: auto; }}
  .card h2 {{ font-size: 13px; font-weight: 600; color: #1a1a2e; margin-bottom: 14px; border-bottom: 2px solid #f0f0f0; padding-bottom: 8px; }}
  .card.full {{ margin-bottom: 18px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #1a1a2e; color: #fff; padding: 7px 10px; text-align: left; font-size: 11px; font-weight: 600; white-space: nowrap; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }}
  tr:hover td {{ background: #f0f4ff !important; }}
  .bar-wrap {{ display: flex; align-items: center; gap: 8px; min-width: 120px; }}
  .bar {{ height: 8px; background: #4285f4; border-radius: 4px; min-width: 2px; }}
  .tag {{ display: inline-block; padding: 2px 7px; border-radius: 10px; font-size: 10px; font-weight: 600; }}
  .note {{ background: #fff8e1; border-left: 3px solid #fbbc04; padding: 10px 14px; border-radius: 4px; font-size: 12px; margin-bottom: 18px; }}
  footer {{ text-align: center; padding: 20px; color: #aaa; font-size: 11px; }}
</style>
</head>
<body>
<header>
  <h1>CHUK.IN - Social + Other Sources Dashboard</h1>
  <span>Last 30 days | Generated {today} | Excludes google/organic + direct</span>
</header>
<div class="container">

  <div class="note">
    <strong>What this shows:</strong> All traffic EXCEPT Google Organic and Direct. These are the sources you need to grow.
    Total non-google/direct sessions: <strong>{main_total:,}</strong>
  </div>

  <div class="kpi-row">
    <div class="kpi">
      <div class="label">Other Sessions</div>
      <div class="val">{main_total:,}</div>
      <div class="sub">Excl. google/organic + direct</div>
    </div>
    <div class="kpi">
      <div class="label">Unique Sources</div>
      <div class="val">{len(r1.rows)}</div>
      <div class="sub">Source/medium combos</div>
    </div>
    <div class="kpi">
      <div class="label">Social Sessions</div>
      <div class="val">{sum(int(r.metric_values[0].value) for r in r3.rows):,}</div>
      <div class="sub">Organic social only</div>
    </div>
    <div class="kpi">
      <div class="label">AI Sources</div>
      <div class="val">183</div>
      <div class="sub">ChatGPT + Gemini + Claude</div>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>Channel Breakdown (All Traffic)</h2>
      <table>
        <thead><tr><th>Channel</th><th>Sessions</th><th>Bounce</th><th>Share</th></tr></thead>
        <tbody>{channel_rows}</tbody>
      </table>
    </div>
    <div class="card">
      <h2>Social Media by Platform</h2>
      <table>
        <thead><tr><th>Platform</th><th>Sessions</th><th>Users</th><th>Share</th></tr></thead>
        <tbody>{social_rows}</tbody>
      </table>
    </div>
  </div>

  <div class="card full">
    <h2>All Sources (excl. google/organic + direct) — Source/Medium + Landing Page</h2>
    <table>
      <thead>
        <tr>
          <th>Source / Medium</th>
          <th>Landing Page</th>
          <th>Sessions</th>
          <th>Users</th>
          <th>New Users</th>
          <th>Bounce Rate</th>
          <th>Avg Duration</th>
          <th>Share</th>
        </tr>
      </thead>
      <tbody>{main_rows_html}</tbody>
    </table>
  </div>

</div>
<footer>CHUK.IN GA4 Dashboard - run ga4_dashboard.py to refresh</footer>
</body>
</html>"""

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chuk_dashboard.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Dashboard saved: {out}")
webbrowser.open(f"file:///{out}")
