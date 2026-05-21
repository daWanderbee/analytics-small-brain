from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, DateRange, Metric, Dimension, OrderBy
)
from google.oauth2.credentials import Credentials
import json

with open("ga4_token.json") as f:
    token_data = json.load(f)

creds = Credentials(
    token=token_data["token"],
    refresh_token=token_data["refresh_token"],
    token_uri=token_data["token_uri"],
    client_id=token_data["client_id"],
    client_secret=token_data["client_secret"],
)

client = BetaAnalyticsDataClient(credentials=creds)
PROPERTY = "properties/364059461"

def run_report(title, dimensions, metrics, limit=50):
    req = RunReportRequest(
        property=PROPERTY,
        date_ranges=[DateRange(start_date="30daysAgo", end_date="today")],
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name=metrics[0]), desc=True)],
        limit=limit,
    )
    resp = client.run_report(req)
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    total = sum(int(row.metric_values[0].value) for row in resp.rows)
    headers = dimensions + metrics
    print("  " + " | ".join(f"{h:28}" for h in headers) + " | %share")
    print("  " + "-" * (31 * len(headers) + 10))
    for row in resp.rows:
        vals = [d.value for d in row.dimension_values] + [m.value for m in row.metric_values]
        pct = round(int(row.metric_values[0].value) / total * 100, 1)
        print("  " + " | ".join(f"{v:28}" for v in vals) + f" | {pct}%")
    print(f"\n  Total unique {dimensions[0]}s: {len(resp.rows)} | Total {metrics[0]}: {total}")
    return resp.rows

# Channel groups
run_report("CHANNELS (How traffic arrives)", ["sessionDefaultChannelGroup"], ["sessions", "activeUsers", "newUsers"])

# Source/medium combined
run_report("SOURCE / MEDIUM (All entry points)", ["sessionSourceMedium"], ["sessions", "activeUsers"], limit=50)

# Just sources
run_report("ALL SOURCES", ["sessionSource"], ["sessions"], limit=50)
