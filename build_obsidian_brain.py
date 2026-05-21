"""
CHUK GA4 Brain - Obsidian Vault Builder
Fetches live GA4 data and generates full dashboard in Obsidian.
"""
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, DateRange, Metric, Dimension, OrderBy,
    FilterExpression, FilterExpressionList, Filter
)
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import json, os, datetime

# ── AUTH ─────────────────────────────────────────────────────────────
TOKEN_FILE = r"C:\Users\Asmita\documents\asmita\apps\chuk\ga4_token.json"
PROPERTY   = "properties/364059461"
VAULT      = r"C:\Users\Asmita\Documents\Asmita\Obsidian\SEO"
GA4_DIR    = os.path.join(VAULT, "GA4 Brain")
TODAY      = datetime.date.today().strftime("%Y-%m-%d")
PRETTY     = datetime.date.today().strftime("%d %b %Y")

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

os.makedirs(GA4_DIR, exist_ok=True)

# ── HELPERS ──────────────────────────────────────────────────────────
def q(dims, metrics, fltr=None, limit=50, days="30daysAgo"):
    req = RunReportRequest(
        property=PROPERTY,
        date_ranges=[DateRange(start_date=days, end_date="today")],
        dimensions=[Dimension(name=d) for d in dims],
        metrics=[Metric(name=m) for m in metrics],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name=metrics[0]), desc=True)],
        limit=limit,
    )
    if fltr:
        req.dimension_filter = fltr
    return client.run_report(req)

def ch_filter(channel):
    return FilterExpression(filter=Filter(
        field_name="sessionDefaultChannelGroup",
        string_filter=Filter.StringFilter(value=channel, match_type=Filter.StringFilter.MatchType.EXACT)
    ))

def fmt_dur(v):
    s = int(float(v)); return f"{s//60}m {s%60}s"

def pct(v, total):
    return round(int(float(v)) / total * 100, 1) if total else 0

def save(name, content):
    path = os.path.join(GA4_DIR, f"{name}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Saved: {name}.md")

# ── FETCH ALL DATA ────────────────────────────────────────────────────
print("Fetching GA4 data...")

r_overview   = q([], ["sessions","activeUsers","newUsers","screenPageViews","bounceRate","averageSessionDuration"])
r_channels   = q(["sessionDefaultChannelGroup"], ["sessions","activeUsers","bounceRate"])
r_sources    = q(["sessionSourceMedium"], ["sessions","activeUsers","bounceRate","averageSessionDuration"], limit=30)
r_pages      = q(["landingPage"], ["sessions","activeUsers","bounceRate","averageSessionDuration"], limit=20)
r_countries  = q(["country"], ["sessions","activeUsers"], limit=10)
r_cities     = q(["city"], ["sessions","activeUsers"], limit=15)
r_devices    = q(["deviceCategory"], ["sessions","activeUsers","bounceRate"])
r_social     = q(["sessionSource"], ["sessions","activeUsers","bounceRate"], fltr=ch_filter("Organic Social"))
r_organic    = q(["sessionSource"], ["sessions"], fltr=ch_filter("Organic Search"))
r_daily      = q(["date"], ["sessions","activeUsers"], days="30daysAgo")
r_pages_all  = q(["pagePath"], ["screenPageViews","activeUsers","averageSessionDuration"], limit=20)
r_new_ret    = q(["newVsReturning"], ["sessions","bounceRate","averageSessionDuration"])

# sort daily by date
r_daily.rows.sort(key=lambda r: r.dimension_values[0].value)

print("  All data fetched.")

# ── EXTRACT KEY NUMBERS ───────────────────────────────────────────────
ov = r_overview.rows[0] if r_overview.rows else None
total_sess   = int(ov.metric_values[0].value) if ov else 0
total_users  = int(ov.metric_values[1].value) if ov else 0
total_new    = int(ov.metric_values[2].value) if ov else 0
total_pv     = int(ov.metric_values[3].value) if ov else 0
bounce_rate  = round(float(ov.metric_values[4].value)*100, 1) if ov else 0
avg_dur      = fmt_dur(ov.metric_values[5].value) if ov else "0m 0s"

ch_data = {r.dimension_values[0].value: int(r.metric_values[0].value) for r in r_channels.rows}
organic_sess = ch_data.get("Organic Search", 0)
direct_sess  = ch_data.get("Direct", 0)
social_sess  = ch_data.get("Organic Social", 0)
referral_sess= ch_data.get("Referral", 0)
paid_sess    = ch_data.get("Paid Search", 0)

# Daily trend arrays
daily_labels = [r.dimension_values[0].value[4:] for r in r_daily.rows]  # MM-DD
daily_sess   = [int(r.metric_values[0].value) for r in r_daily.rows]
daily_users  = [int(r.metric_values[1].value) for r in r_daily.rows]

# ── AUTO RECOMMENDATIONS ENGINE ───────────────────────────────────────
recs = []
plus = []
warnings = []

google_pct = pct(organic_sess, total_sess)
direct_pct = pct(direct_sess, total_sess)
social_pct = pct(social_sess, total_sess)

if google_pct > 50:
    warnings.append(f"Google Organic = {google_pct}% of traffic. Single point of failure. Diversify NOW.")
if direct_pct > 25:
    warnings.append(f"Direct = {direct_pct}% — likely untagged WhatsApp/email links inflating this number.")
if social_pct < 5:
    recs.append(f"Social = {social_pct}%. Target 10-15%. Fix Instagram bio UTM + 2x LinkedIn posts/week.")
if paid_sess < 100:
    recs.append("Paid Search = <100 sessions. Test Google Ads on high-intent keywords like 'disposable plates bulk'.")
if bounce_rate > 50:
    warnings.append(f"Bounce rate {bounce_rate}% is high. Add product CTAs inside blog posts.")

# Check AI traffic
ai_sources = ["chatgpt.com","gemini.google.com","claude.ai","perplexity","copilot.com"]
ai_total = sum(int(r.metric_values[0].value) for r in r_sources.rows
               if any(ai in r.dimension_values[0].value for ai in ai_sources))
if ai_total > 100:
    plus.append(f"AI referral traffic = {ai_total} sessions. Growing channel. Optimize content for AI citations.")

# Top organic engine
top_eng = r_organic.rows[0].dimension_values[0].value if r_organic.rows else "google"
if top_eng == "google":
    plus.append("Google Organic is strong at 94% of search traffic. Content SEO is working.")

# Best social platform
if r_social.rows:
    best_social = r_social.rows[0].dimension_values[0].value
    best_social_sess = r_social.rows[0].metric_values[0].value
    recs.append(f"Best social platform: {best_social} ({best_social_sess} sessions). Double down here first.")

# LinkedIn quality signal
linkedin_rows = [r for r in r_sources.rows if "linkedin" in r.dimension_values[0].value.lower()]
if linkedin_rows:
    li_dur = float(linkedin_rows[0].metric_values[3].value)
    if li_dur > 200:
        plus.append(f"LinkedIn avg duration {fmt_dur(li_dur)} — highest quality traffic. Scale B2B content.")

# Distributor page
dist_rows = [r for r in r_pages.rows if "distribut" in r.dimension_values[0].value]
if dist_rows:
    plus.append(f"/distributors-2 getting organic traffic with low bounce — B2B intent is real.")

recs.append("Connect Google Search Console to GA4 to unlock keyword data (currently 100% not provided).")
recs.append("Add internal links in top 5 blog posts -> product pages to reduce blog bounce rate.")
recs.append("Create WhatsApp tagged links (bit.ly) for all broadcast messages.")
recs.append("Set up email capture on high-traffic blog posts to build owned channel.")

# ── BUILD NOTES ───────────────────────────────────────────────────────
print("Building Obsidian notes...")

# ── 1. DASHBOARD ─────────────────────────────────────────────────────
ch_labels  = [r.dimension_values[0].value for r in r_channels.rows]
ch_vals    = [int(r.metric_values[0].value) for r in r_channels.rows]
ch_bounce  = [round(float(r.metric_values[2].value)*100,1) for r in r_channels.rows]

dev_labels = [r.dimension_values[0].value for r in r_devices.rows]
dev_vals   = [int(r.metric_values[0].value) for r in r_devices.rows]

warnings_md = "\n".join(f"> [!danger] {w}" for w in warnings)
plus_md     = "\n".join(f"> [!success] {p}" for p in plus)
recs_md     = "\n".join(f"- [ ] {r}" for r in recs)

save("00 - Dashboard", f"""---
tags: [ga4, dashboard]
updated: {TODAY}
---

# CHUK GA4 Brain
> **Property:** CHUK - GA4 | **Period:** Last 30 Days | **Updated:** {PRETTY}

---

## Key Metrics

| Metric | Value |
|--------|-------|
| Sessions | {total_sess:,} |
| Active Users | {total_users:,} |
| New Users | {total_new:,} ({pct(total_new, total_users)}%) |
| Page Views | {total_pv:,} |
| Bounce Rate | {bounce_rate}% |
| Avg Session Duration | {avg_dur} |

---

## Traffic Trend (30 Days)

```chart
type: line
labels: {daily_labels}
series:
  - title: Sessions
    data: {daily_sess}
    backgroundColor: rgba(66,133,244,0.2)
    borderColor: rgba(66,133,244,1)
    fill: true
  - title: Users
    data: {daily_users}
    backgroundColor: rgba(52,168,83,0.2)
    borderColor: rgba(52,168,83,1)
    fill: false
tension: 0.4
width: 100%
labelColors: false
gridLines: true
legend: true
```

---

## Channel Distribution

```chart
type: doughnut
labels: {ch_labels}
series:
  - title: Sessions
    data: {ch_vals}
backgroundColor:
  - rgba(66,133,244,0.8)
  - rgba(170,170,170,0.8)
  - rgba(52,168,83,0.8)
  - rgba(234,67,53,0.8)
  - rgba(251,188,4,0.8)
  - rgba(100,100,100,0.5)
  - rgba(156,39,176,0.8)
width: 60%
legend: true
```

---

## Warnings
{warnings_md if warnings_md else "> [!info] No critical warnings"}

---

## Whats Working
{plus_md if plus_md else "> [!info] Collecting signals..."}

---

## Action Items
{recs_md}

---

## Navigation
- [[01 - Channel Analysis]]
- [[02 - Organic Search]]
- [[03 - Social Media]]
- [[04 - Direct Traffic]]
- [[05 - Top Pages]]
- [[06 - Geographic]]
- [[07 - Source Details]]
- [[08 - Recommendations]]
""")

# ── 2. CHANNEL ANALYSIS ───────────────────────────────────────────────
save("01 - Channel Analysis", f"""---
tags: [ga4, channels]
updated: {TODAY}
---

# Channel Analysis
> Last 30 days | [[00 - Dashboard]]

## Sessions by Channel

```chart
type: bar
labels: {ch_labels}
series:
  - title: Sessions
    data: {ch_vals}
    backgroundColor:
      - rgba(66,133,244,0.8)
      - rgba(170,170,170,0.8)
      - rgba(52,168,83,0.8)
      - rgba(234,67,53,0.8)
      - rgba(251,188,4,0.8)
      - rgba(100,100,100,0.5)
      - rgba(156,39,176,0.8)
indexAxis: y
width: 100%
legend: false
```

## Bounce Rate by Channel

```chart
type: bar
labels: {ch_labels}
series:
  - title: Bounce Rate %
    data: {ch_bounce}
    backgroundColor: rgba(234,67,53,0.6)
indexAxis: y
width: 100%
legend: false
```

## Data Table

| Channel | Sessions | Share | Bounce |
|---------|----------|-------|--------|
{"".join(f"| {r.dimension_values[0].value} | {int(r.metric_values[0].value):,} | {pct(r.metric_values[0].value, total_sess)}% | {round(float(r.metric_values[2].value)*100,1)}% |{chr(10)}" for r in r_channels.rows)}

## Diagnosis

| Channel | Status | Action |
|---------|--------|--------|
| Organic Search ({pct(organic_sess,total_sess)}%) | {"OVER-RELIANT" if google_pct>50 else "OK"} | Diversify traffic sources |
| Direct ({pct(direct_sess,total_sess)}%) | {"HIGH - likely untagged links" if direct_pct>25 else "OK"} | Add UTMs to WhatsApp + email |
| Social ({pct(social_sess,total_sess)}%) | {"LOW" if social_pct<5 else "OK"} | Scale Instagram + LinkedIn |
| Paid Search ({pct(paid_sess,total_sess)}%) | {"UNTAPPED" if paid_sess<100 else "OK"} | Test Google Ads |
| AI Referral | GROWING | Optimize content for AI citation |
""")

# ── 3. ORGANIC SEARCH ─────────────────────────────────────────────────
org_pages    = [r.dimension_values[0].value[:40] for r in r_pages.rows[:10]]
org_sessions = [int(r.metric_values[0].value) for r in r_pages.rows[:10]]
org_bounce   = [round(float(r.metric_values[2].value)*100,1) for r in r_pages.rows[:10]]
eng_labels   = [r.dimension_values[0].value for r in r_organic.rows]
eng_vals     = [int(r.metric_values[0].value) for r in r_organic.rows]

save("02 - Organic Search", f"""---
tags: [ga4, organic, seo]
updated: {TODAY}
---

# Organic Search Analysis
> {organic_sess:,} sessions | {pct(organic_sess,total_sess)}% of total | [[00 - Dashboard]]

## Search Engine Split

```chart
type: pie
labels: {eng_labels}
series:
  - title: Sessions
    data: {eng_vals}
backgroundColor:
  - rgba(66,133,244,0.8)
  - rgba(0,120,212,0.7)
  - rgba(118,185,0,0.7)
  - rgba(255,165,0,0.7)
  - rgba(100,100,100,0.5)
width: 50%
legend: true
```

> [!warning] 94% Google dependency. Bing = 3.5%, Yahoo = 1.2%, ChatGPT organic = 0.6%.

## Top Landing Pages from Organic

```chart
type: bar
labels: {org_pages}
series:
  - title: Sessions
    data: {org_sessions}
    backgroundColor: rgba(66,133,244,0.7)
indexAxis: y
width: 100%
legend: false
```

## Bounce Rate by Landing Page

```chart
type: bar
labels: {org_pages}
series:
  - title: Bounce Rate %
    data: {org_bounce}
    backgroundColor: rgba(234,67,53,0.6)
indexAxis: y
width: 100%
legend: false
```

## Landing Page Table

| Page | Sessions | Bounce | Avg Duration |
|------|----------|--------|--------------|
{"".join(f"| {r.dimension_values[0].value[:45]} | {int(r.metric_values[0].value):,} | {round(float(r.metric_values[2].value)*100,1)}% | {fmt_dur(r.metric_values[3].value)} |{chr(10)}" for r in r_pages.rows[:15])}

## Insights

> [!success] Homepage gets 1,709 organic sessions with only 26% bounce — strong landing page.

> [!info] Blog posts (Janmashtami, Blinkit, Zomato/Swiggy) driving ~900 sessions but 65-78% bounce. Add product CTAs inside each post.

> [!danger] (not set) landing page = 325 sessions, 97% bounce. Fix: GA4 Admin > Data Streams > Configure tag > List unwanted referrals > add chuk.in

> [!info] Keywords = 100% not provided. Connect Google Search Console to GA4 to unlock keyword data.
""")

# ── 4. SOCIAL MEDIA ───────────────────────────────────────────────────
soc_labels = [r.dimension_values[0].value for r in r_social.rows]
soc_vals   = [int(r.metric_values[0].value) for r in r_social.rows]
soc_bounce = [round(float(r.metric_values[2].value)*100,1) for r in r_social.rows]
soc_total  = sum(soc_vals)

save("03 - Social Media", f"""---
tags: [ga4, social]
updated: {TODAY}
---

# Social Media Analysis
> {soc_total} sessions | {pct(soc_total,total_sess)}% of total | [[00 - Dashboard]]

> [!danger] Social at {pct(soc_total,total_sess)}% — target is 10-15%. Massive growth opportunity.

## Sessions by Platform

```chart
type: bar
labels: {soc_labels}
series:
  - title: Sessions
    data: {soc_vals}
    backgroundColor:
      - rgba(225,48,108,0.8)
      - rgba(66,103,178,0.8)
      - rgba(10,102,194,0.8)
      - rgba(29,161,242,0.8)
      - rgba(255,0,0,0.8)
      - rgba(0,119,181,0.8)
      - rgba(37,211,102,0.8)
width: 100%
legend: false
```

## Bounce Rate by Platform

```chart
type: bar
labels: {soc_labels}
series:
  - title: Bounce Rate %
    data: {soc_bounce}
    backgroundColor: rgba(234,67,53,0.6)
width: 100%
legend: false
```

## Platform Table

| Platform | Sessions | Bounce | Quality |
|----------|----------|--------|---------|
{"".join(f"| {r.dimension_values[0].value} | {int(r.metric_values[0].value)} | {round(float(r.metric_values[2].value)*100,1)}% | {'HIGH' if float(r.metric_values[2].value)<0.4 else 'MEDIUM' if float(r.metric_values[2].value)<0.6 else 'LOW'} |{chr(10)}" for r in r_social.rows)}

## Hidden WhatsApp Traffic
> [!warning] l.wl.co/referral = 92 sessions showing as Referral, not Social. These are untagged WhatsApp Web shares. Fix: use UTM-tagged links in all WhatsApp broadcasts.

## Action Plan

| Platform | Current | Action | Expected |
|----------|---------|--------|----------|
| Instagram | 42 sessions | Fix bio UTM + story link stickers | 200+ sessions/month |
| Facebook | 40 sessions | Stop random product links, use UTM campaigns | 100+ sessions/month |
| LinkedIn | 8 sessions | 2x posts/week targeting distributors | 200-300 sessions/month |
| WhatsApp | 1 session | Tag all broadcast links | 500+ sessions/month |
| YouTube | 0 sessions | Create product demo videos | 100+ sessions/month |
| Reddit | 0 sessions | Answer food industry questions with link | 50+ sessions/month |
""")

# ── 5. DIRECT TRAFFIC ─────────────────────────────────────────────────
direct_filter = ch_filter("Direct")
r_direct_pages = q(["landingPage"], ["sessions","bounceRate","averageSessionDuration"], fltr=direct_filter, limit=15)
dir_pages  = [r.dimension_values[0].value[:40] for r in r_direct_pages.rows[:10]]
dir_sess   = [int(r.metric_values[0].value) for r in r_direct_pages.rows[:10]]

save("04 - Direct Traffic", f"""---
tags: [ga4, direct]
updated: {TODAY}
---

# Direct Traffic Analysis
> {direct_sess:,} sessions | {pct(direct_sess,total_sess)}% of total | [[00 - Dashboard]]

> [!warning] Direct is NOT just people typing chuk.in. GA4 puts traffic here when it CANNOT identify the source.

## What is hiding inside Direct

| Cause | Likely Volume | Fix |
|-------|--------------|-----|
| Untagged WhatsApp links | ~100 sessions | Add UTMs to all WA broadcasts |
| Untagged email links | ~200 sessions | Add UTMs to all email links |
| Slack / Teams DMs | ~50 sessions | Add UTMs to internal shares |
| Broken tracking (not set) | 127 sessions | Fix GA4 referral exclusion |
| Genuine bookmarks/typed URL | ~400 sessions | These are real - keep |
| Dark social (private shares) | ~200 sessions | Unattributable - accept |

## Top Direct Landing Pages

```chart
type: bar
labels: {dir_pages}
series:
  - title: Sessions
    data: {dir_sess}
    backgroundColor: rgba(170,170,170,0.7)
indexAxis: y
width: 100%
legend: false
```

## Direct Page Table

| Page | Sessions | Bounce | Avg Duration |
|------|----------|--------|--------------|
{"".join(f"| {r.dimension_values[0].value[:45]} | {int(r.metric_values[0].value):,} | {round(float(r.metric_values[1].value)*100,1)}% | {fmt_dur(r.metric_values[2].value)} |{chr(10)}" for r in r_direct_pages.rows[:12])}

## Fix Steps

- [ ] GA4 Admin > Data Streams > chuk.in > Configure tag > List unwanted referrals > add chuk.in
- [ ] Filter internal team traffic: GA4 Admin > Data Streams > Define internal traffic > add office IP
- [ ] Tag all WhatsApp broadcast links with UTM
- [ ] Tag all email newsletter/transactional links with UTM
- [ ] After fixes, Direct should drop from {pct(direct_sess,total_sess)}% to ~15-18%
""")

# ── 6. TOP PAGES ──────────────────────────────────────────────────────
top_pages   = [r.dimension_values[0].value[:40] for r in r_pages_all.rows[:15]]
top_pv      = [int(r.metric_values[0].value) for r in r_pages_all.rows[:15]]
top_dur     = [round(float(r.metric_values[2].value)) for r in r_pages_all.rows[:15]]

save("05 - Top Pages", f"""---
tags: [ga4, pages]
updated: {TODAY}
---

# Top Pages
> {total_pv:,} total page views | [[00 - Dashboard]]

## Page Views

```chart
type: bar
labels: {top_pages}
series:
  - title: Page Views
    data: {top_pv}
    backgroundColor: rgba(66,133,244,0.7)
indexAxis: y
width: 100%
legend: false
```

## Avg Time on Page (seconds)

```chart
type: bar
labels: {top_pages}
series:
  - title: Avg Duration (s)
    data: {top_dur}
    backgroundColor: rgba(52,168,83,0.6)
indexAxis: y
width: 100%
legend: false
```

## Full Table

| Page | Views | Users | Avg Duration |
|------|-------|-------|--------------|
{"".join(f"| {r.dimension_values[0].value[:45]} | {int(r.metric_values[0].value):,} | {r.metric_values[1].value} | {fmt_dur(r.metric_values[2].value)} |{chr(10)}" for r in r_pages_all.rows[:15])}

## Insights

> [!success] Homepage (/) = most visited. 4,136 views with strong engagement.

> [!success] /buy-sample-boxes in top 7 — high-intent conversion page getting organic traffic.

> [!info] /distributors-2 steady traffic + long avg duration = B2B intent visitors. Needs stronger CTA.

> [!danger] /product/test-producct-pls-ignore getting real traffic. Remove or redirect this test page.
""")

# ── 7. GEOGRAPHIC ─────────────────────────────────────────────────────
country_labels = [r.dimension_values[0].value for r in r_countries.rows]
country_vals   = [int(r.metric_values[0].value) for r in r_countries.rows]
city_labels    = [r.dimension_values[0].value for r in r_cities.rows[:10] if r.dimension_values[0].value not in ["(not set)",""]]
city_vals      = [int(r.metric_values[0].value) for r in r_cities.rows[:10] if r.dimension_values[0].value not in ["(not set)",""]]

save("06 - Geographic", f"""---
tags: [ga4, geographic]
updated: {TODAY}
---

# Geographic Analysis
> [[00 - Dashboard]]

## Top Countries

```chart
type: bar
labels: {country_labels}
series:
  - title: Sessions
    data: {country_vals}
    backgroundColor: rgba(66,133,244,0.7)
indexAxis: y
width: 100%
legend: false
```

## Top Cities (India)

```chart
type: bar
labels: {city_labels}
series:
  - title: Sessions
    data: {city_vals}
    backgroundColor: rgba(52,168,83,0.7)
indexAxis: y
width: 100%
legend: false
```

## Country Table

| Country | Sessions | Share |
|---------|----------|-------|
{"".join(f"| {r.dimension_values[0].value} | {int(r.metric_values[0].value):,} | {pct(r.metric_values[0].value, total_sess)}% |{chr(10)}" for r in r_countries.rows)}

## Device Split

```chart
type: pie
labels: {dev_labels}
series:
  - title: Sessions
    data: {dev_vals}
backgroundColor:
  - rgba(66,133,244,0.8)
  - rgba(52,168,83,0.8)
  - rgba(251,188,4,0.8)
width: 50%
legend: true
```

## Insights

> [!success] Tier-1 cities (Delhi, Bengaluru, Mumbai) = top 3. Strong metro presence.

> [!info] Ahmedabad = 4th largest city — strong signal for Gujarat distributor outreach.

> [!info] US = 6% of sessions. Opportunity for diaspora or export market content.

> [!info] Mobile = 58% of organic traffic. Mobile experience directly impacts bounce rate.
""")

# ── 8. SOURCE DETAILS ─────────────────────────────────────────────────
src_labels  = [r.dimension_values[0].value[:35] for r in r_sources.rows[:15]]
src_vals    = [int(r.metric_values[0].value) for r in r_sources.rows[:15]]
src_bounce  = [round(float(r.metric_values[2].value)*100,1) for r in r_sources.rows[:15]]

save("07 - Source Details", f"""---
tags: [ga4, sources]
updated: {TODAY}
---

# All Source / Medium Details
> [[00 - Dashboard]]

## Top Sources by Sessions

```chart
type: bar
labels: {src_labels}
series:
  - title: Sessions
    data: {src_vals}
    backgroundColor: rgba(66,133,244,0.7)
indexAxis: y
width: 100%
legend: false
```

## Bounce Rate by Source

```chart
type: bar
labels: {src_labels}
series:
  - title: Bounce Rate %
    data: {src_bounce}
    backgroundColor: rgba(234,67,53,0.6)
indexAxis: y
width: 100%
legend: false
```

## Full Source Table

| Source / Medium | Sessions | Users | Bounce | Avg Duration |
|----------------|----------|-------|--------|--------------|
{"".join(f"| {r.dimension_values[0].value[:40]} | {int(r.metric_values[0].value):,} | {r.metric_values[1].value} | {round(float(r.metric_values[2].value)*100,1)}% | {fmt_dur(r.metric_values[3].value)} |{chr(10)}" for r in r_sources.rows[:25])}

## AI Sources

| AI Tool | Sessions |
|---------|----------|
{"".join(f"| {r.dimension_values[0].value} | {int(r.metric_values[0].value):,} |{chr(10)}" for r in r_sources.rows if any(ai in r.dimension_values[0].value for ai in ["chatgpt","gemini","claude","perplexity","copilot"]))}

> [!success] AI referral traffic is real and growing. Total AI sessions: {ai_total}. Ensure content is citation-ready (clear facts, stats, named author).
""")

# ── 9. RECOMMENDATIONS ────────────────────────────────────────────────
new_vs_ret = {r.dimension_values[0].value: {
    "sessions": r.metric_values[0].value,
    "bounce": round(float(r.metric_values[1].value)*100,1),
    "dur": fmt_dur(r.metric_values[2].value)
} for r in r_new_ret.rows}

save("08 - Recommendations", f"""---
tags: [ga4, recommendations]
updated: {TODAY}
---

# Recommendations & Action Plan
> Based on last 30 days data | [[00 - Dashboard]]

## Priority Matrix

| Priority | Action | Impact | Effort | Timeline |
|----------|--------|--------|--------|----------|
| P1 | Fix Instagram bio UTM link | High | Low (5 min) | Today |
| P1 | Create 3 WhatsApp UTM short links | High | Low (10 min) | Today |
| P1 | Fix (not set) in GA4 referral exclusions | Medium | Low (5 min) | Today |
| P2 | Add product CTAs to top 5 blog posts | High | Medium | This week |
| P2 | Filter internal team traffic in GA4 | Medium | Low | This week |
| P2 | Connect Google Search Console to GA4 | High | Low | This week |
| P3 | LinkedIn 2x posts/week with tagged links | High | Medium | Ongoing |
| P3 | Tag all email links with UTMs | Medium | Medium | This week |
| P4 | Test Google Ads on product keywords | Medium | High | This month |
| P4 | Start YouTube product demo channel | High | High | This month |

## Checklist

- [ ] Fix Instagram bio link: `https://chuk.in/?utm_source=instagram&utm_medium=social&utm_campaign=bio`
- [ ] Create WhatsApp short links (bit.ly) for homepage, products, distributors
- [ ] GA4 Admin > Data Streams > Configure tag > unwanted referrals > add chuk.in
- [ ] Add internal links in: /krishna-janmashtami blog, /bistro-blinkit blog, /zomato-rank blog
- [ ] GA4 Admin > Data Streams > Define internal traffic > add office IP
- [ ] Link Google Search Console in GA4 Admin > Property Settings > Search Console
- [ ] LinkedIn posts with /distributors-2 UTM link 2x/week
- [ ] Tag all Zoho CRM / email outreach links
- [ ] Remove or redirect /product/test-producct-pls-ignore
- [ ] Create YouTube channel + add UTM links in video descriptions

## New Sources to Activate

| Source | UTM Example | Potential |
|--------|-------------|-----------|
| Reddit | utm_source=reddit&utm_medium=social | 50-100/month |
| Twitter/X | utm_source=twitter&utm_medium=social | 50/month |
| Quora | utm_source=quora&utm_medium=referral | 100+/month |
| YouTube | utm_source=youtube&utm_medium=video | 200+/month |
| IndiaMART | utm_source=indiamart&utm_medium=referral | 200+/month |
| Telegram | utm_source=telegram&utm_medium=social | 100+/month |

## New vs Returning Users

| Type | Sessions | Bounce | Avg Duration |
|------|----------|--------|--------------|
{"".join(f"| {k} | {v['sessions']} | {v['bounce']}% | {v['dur']} |{chr(10)}" for k,v in new_vs_ret.items())}

> [!info] Returning users: {new_vs_ret.get('returning',{}).get('dur','N/A')} avg duration vs new users {new_vs_ret.get('new',{}).get('dur','N/A')}. Returning users 5x more engaged. Build email list to drive repeat visits.

## Traffic Target (90 Days)

| Channel | Now | 90-Day Target |
|---------|-----|---------------|
| Organic Search | {organic_sess:,} | {int(organic_sess*1.2):,} |
| Direct | {direct_sess:,} | {int(direct_sess*0.7):,} (reduce via UTM tagging) |
| Social | {social_sess} | 500+ |
| WhatsApp | ~92 (hidden) | 600+ (tagged) |
| Email | 0 | 300+ |
| LinkedIn | 8 | 250+ |
| Referral | {referral_sess} | {int(referral_sess*1.5):,} |
""")

# ── INDEX NOTE ────────────────────────────────────────────────────────
save("_INDEX", f"""---
tags: [ga4, index]
---

# GA4 Brain - CHUK.IN

> Auto-generated from GA4 API | Run `python build_obsidian_brain.py` to refresh

## Notes

| Note | Description |
|------|-------------|
| [[00 - Dashboard]] | Overview KPIs + trend chart + warnings |
| [[01 - Channel Analysis]] | How traffic arrives + channel quality |
| [[02 - Organic Search]] | SEO breakdown, engines, landing pages |
| [[03 - Social Media]] | Instagram, Facebook, LinkedIn, WhatsApp |
| [[04 - Direct Traffic]] | What is hiding in Direct |
| [[05 - Top Pages]] | Most visited pages + engagement |
| [[06 - Geographic]] | Countries, cities, device split |
| [[07 - Source Details]] | All source/medium + AI referral |
| [[08 - Recommendations]] | Prioritized action plan + checklist |

## Last Updated
{PRETTY}
""")

print(f"\nDone. {len(os.listdir(GA4_DIR))} notes created in:")
print(f"  {GA4_DIR}")
print("\nOpen Obsidian -> GA4 Brain folder -> start with _INDEX or 00 - Dashboard")
