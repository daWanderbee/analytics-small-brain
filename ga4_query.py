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

def run(title, dimensions, metrics, order_metric=None, limit=10):
    req = RunReportRequest(
        property=PROPERTY,
        date_ranges=[DateRange(start_date="30daysAgo", end_date="today")],
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        limit=limit,
    )
    if order_metric:
        req.order_bys = [OrderBy(metric=OrderBy.MetricOrderBy(metric_name=order_metric), desc=True)]
    resp = client.run_report(req)
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")
    headers = dimensions + metrics
    print("  " + " | ".join(f"{h:25}" for h in headers))
    print("  " + "-" * (28 * len(headers)))
    for row in resp.rows:
        vals = [d.value for d in row.dimension_values] + [m.value for m in row.metric_values]
        print("  " + " | ".join(f"{v:25}" for v in vals))

# Overview
req = RunReportRequest(
    property=PROPERTY,
    date_ranges=[DateRange(start_date="30daysAgo", end_date="today")],
    metrics=[
        Metric(name="sessions"),
        Metric(name="activeUsers"),
        Metric(name="newUsers"),
        Metric(name="screenPageViews"),
        Metric(name="bounceRate"),
        Metric(name="averageSessionDuration"),
    ],
)
resp = client.run_report(req)
print("\n" + "="*50)
print("  OVERVIEW — Last 30 Days")
print("="*50)
row = resp.rows[0]
metrics_list = ["sessions","activeUsers","newUsers","pageViews","bounceRate","avgSessionDuration"]
for i, m in enumerate(resp.metric_headers):
    print(f"  {m.name:30} {row.metric_values[i].value}")

run("TOP PAGES", ["pagePath"], ["screenPageViews","activeUsers"], "screenPageViews")
run("TOP CHANNELS", ["sessionDefaultChannelGroup"], ["sessions","activeUsers","bounceRate"], "sessions")
run("TOP COUNTRIES", ["country"], ["sessions","activeUsers"], "sessions")
run("DEVICE CATEGORY", ["deviceCategory"], ["sessions","activeUsers"], "sessions", limit=5)
run("TOP SOURCES", ["sessionSource"], ["sessions","activeUsers"], "sessions")
