import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import json, math, os, urllib.request, csv, io
from datetime import date, timedelta
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, RunRealtimeReportRequest, DateRange, Metric, Dimension, OrderBy,
    FilterExpression, FilterExpressionList, Filter
)
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import streamlit.components.v1 as components
import meta as meta_api
import platform_api

st.set_page_config(
    page_title="CHUK GA4 Brain",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── STYLES ────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .main { background: #0e1117; }
  .metric-card { background: #1e2130; border-radius: 10px; padding: 16px 20px; margin: 6px 0; }
  .metric-val { font-size: 2rem; font-weight: 700; color: #fff; }
  .metric-label { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 1px; }
  .metric-delta { font-size: 0.8rem; }
  .warn { background: #2a1a1a; border-left: 3px solid #f44; padding: 10px 14px; border-radius: 4px; margin: 6px 0; }
  .ok   { background: #1a2a1a; border-left: 3px solid #4f4; padding: 10px 14px; border-radius: 4px; margin: 6px 0; }
  .info { background: #1a1a2a; border-left: 3px solid #44f; padding: 10px 14px; border-radius: 4px; margin: 6px 0; }
</style>
""", unsafe_allow_html=True)

# ── AUTH ─────────────────────────────────────────────────────────────
def get_client():
    if "ga4_token" in st.secrets:
        t = dict(st.secrets["ga4_token"])
    else:
        token_path = os.path.join(os.path.dirname(__file__), "..", "ga4_token.json")
        with open(token_path) as f:
            t = json.load(f)
    # Always start with empty token — force refresh using refresh_token
    creds = Credentials(
        token=None,
        refresh_token=t["refresh_token"],
        token_uri=t["token_uri"],
        client_id=t["client_id"],
        client_secret=t["client_secret"]
    )
    creds.refresh(Request())
    return BetaAnalyticsDataClient(credentials=creds)

# ── DATA ──────────────────────────────────────────────────────────────
PROPERTIES = {
    "CHUK - GA4 (chuk.in)":   "properties/364059461",
    "CHUK USA":                "properties/487670609",
    "Pakka (pakka.com)":       "properties/488074493",
    "Pakka Maitri":            "properties/518174699",
}

@st.cache_data(ttl=3600)
def fetch(_client, prop, days="30daysAgo"):
    def q(dims, metrics, fltr=None, limit=50):
        req = RunReportRequest(
            property=prop,
            date_ranges=[DateRange(start_date=days, end_date="today")],
            dimensions=[Dimension(name=d) for d in dims],
            metrics=[Metric(name=m) for m in metrics],
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name=metrics[0]), desc=True)],
            limit=limit,
        )
        if fltr:
            req.dimension_filter = fltr
        return _client.run_report(req)

    def ch_f(ch):
        return FilterExpression(filter=Filter(
            field_name="sessionDefaultChannelGroup",
            string_filter=Filter.StringFilter(value=ch, match_type=Filter.StringFilter.MatchType.EXACT)
        ))

    data = {}
    data["overview"]  = q([], ["sessions","activeUsers","newUsers","screenPageViews","bounceRate","averageSessionDuration"])
    data["channels"]  = q(["sessionDefaultChannelGroup"], ["sessions","activeUsers","bounceRate"])
    data["sources"]   = q(["sessionSourceMedium"], ["sessions","activeUsers","bounceRate","averageSessionDuration"], limit=40)
    data["pages"]     = q(["pagePath"], ["screenPageViews","activeUsers","averageSessionDuration"], limit=20)
    data["landing"]   = q(["landingPage"], ["sessions","activeUsers","bounceRate","averageSessionDuration"], limit=20)
    data["countries"] = q(["country"], ["sessions","activeUsers"], limit=10)
    data["cities"]    = q(["city"], ["sessions","activeUsers"], limit=15)
    data["devices"]   = q(["deviceCategory"], ["sessions","activeUsers","bounceRate"])
    data["social"]    = q(["sessionSource"], ["sessions","activeUsers","bounceRate"], fltr=ch_f("Organic Social"))
    data["organic"]   = q(["sessionSource"], ["sessions"], fltr=ch_f("Organic Search"))
    data["daily"]     = q(["date"], ["sessions","activeUsers"])
    data["new_ret"]   = q(["newVsReturning"], ["sessions","bounceRate","averageSessionDuration"])
    data["daily"].rows.sort(key=lambda r: r.dimension_values[0].value)

    # UTM-tagged traffic: campaign + source + medium + content + term
    data["utm"] = q(
        ["sessionCampaignName", "sessionSource", "sessionMedium"],
        ["sessions", "activeUsers", "newUsers", "bounceRate", "averageSessionDuration", "conversions"],
        limit=100,
    )
    data["utm_campaign"] = q(
        ["sessionCampaignName"],
        ["sessions", "activeUsers", "conversions", "bounceRate"],
        limit=50,
    )
    data["utm_content"] = q(
        ["sessionManualAdContent", "sessionCampaignName"],
        ["sessions", "activeUsers", "conversions"],
        limit=50,
    )
    data["utm_daily"] = q(["date", "sessionMedium"], ["sessions"], limit=500)

    # Funnel: all landing pages with exit/bounce data
    data["funnel_pages"] = q(
        ["pagePath"],
        ["sessions","activeUsers","bounceRate","averageSessionDuration","screenPageViews"],
        limit=50
    )
    # Referral from CCAvenue = completed checkouts proxy
    data["checkout_ref"] = q(
        ["sessionSourceMedium"],
        ["sessions","activeUsers"],
        fltr=FilterExpression(filter=Filter(
            field_name="sessionSourceMedium",
            string_filter=Filter.StringFilter(
                value="secure.ccavenue.com / referral",
                match_type=Filter.StringFilter.MatchType.EXACT
            )
        )),
        limit=5
    )

    # ── Prior period (same length, immediately before) for WoW deltas ──
    n = int("".join(c for c in days if c.isdigit()) or 30)
    prev_start, prev_end = f"{2*n}daysAgo", f"{n+1}daysAgo"
    def qp(dims, metrics, limit=50):
        req = RunReportRequest(
            property=prop,
            date_ranges=[DateRange(start_date=prev_start, end_date=prev_end)],
            dimensions=[Dimension(name=di) for di in dims],
            metrics=[Metric(name=mi) for mi in metrics],
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name=metrics[0]), desc=True)],
            limit=limit,
        )
        return _client.run_report(req)
    data["overview_prev"] = qp([], ["sessions", "activeUsers", "newUsers", "screenPageViews", "bounceRate", "averageSessionDuration"])
    data["channels_prev"] = qp(["sessionDefaultChannelGroup"], ["sessions"])
    data["sources_prev"]  = qp(["sessionSourceMedium"], ["sessions"], limit=40)
    return data

# ── REALTIME (last 30 min, NOT cached) ────────────────────────────────
def fetch_realtime(_client, prop):
    """GA4 Realtime API. NB: source/medium not available in realtime — Google limit."""
    def rt(dims, metrics, limit=20, minute_ranges=None):
        req = RunRealtimeReportRequest(
            property=prop,
            dimensions=[Dimension(name=d) for d in dims],
            metrics=[Metric(name=m) for m in metrics],
            limit=limit,
        )
        if dims:
            req.order_bys = [OrderBy(metric=OrderBy.MetricOrderBy(metric_name=metrics[0]), desc=True)]
        return _client.run_realtime_report(req)

    rd = {}
    rd["now"]      = rt([], ["activeUsers"])                                    # active users right now
    rd["by_min"]   = rt(["minutesAgo"], ["activeUsers"], limit=30)             # last 30 min trend
    rd["pages"]    = rt(["unifiedScreenName"], ["activeUsers", "screenPageViews"], limit=15)
    rd["country"]  = rt(["country"], ["activeUsers"], limit=10)
    rd["city"]     = rt(["city"], ["activeUsers"], limit=10)
    rd["device"]   = rt(["deviceCategory"], ["activeUsers"], limit=5)
    rd["events"]   = rt(["eventName"], ["eventCount"], limit=15)
    return rd

# ── GSC: striking-distance keywords (pos 5-15) ────────────────────────
@st.cache_data(ttl=3600)
def fetch_gsc(site="sc-domain:chuk.in", days=28):
    """Returns (rows, error). rows=None if token dead → UI shows reconnect."""
    try:
        if "gsc_token" in st.secrets:
            t = dict(st.secrets["gsc_token"])
        else:
            path = os.path.join(os.path.dirname(__file__), "..", "gsc_token.json")
            t = json.load(open(path))
        creds = Credentials(token=None, refresh_token=t["refresh_token"],
            token_uri=t["token_uri"], client_id=t["client_id"],
            client_secret=t["client_secret"], scopes=t.get("scopes"))
        creds.refresh(Request())
    except Exception as e:
        return None, str(e)
    try:
        end = date.today(); start = end - timedelta(days=days)
        body = {"startDate": str(start), "endDate": str(end),
                "dimensions": ["query", "page"], "rowLimit": 250}
        site_enc = urllib.request.quote(site, safe="")
        url = f"https://searchconsole.googleapis.com/webmasters/v3/sites/{site_enc}/searchAnalytics/query"
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + creds.token, "Content-Type": "application/json"})
        rows = json.load(urllib.request.urlopen(req)).get("rows", [])
        return rows, None
    except Exception as e:
        return None, str(e)

# ── CrUX: real-user Core Web Vitals ───────────────────────────────────
@st.cache_data(ttl=21600)
def fetch_crux(origin="https://chuk.in"):
    try:
        if "crux_api_key" in st.secrets:
            k = st.secrets["crux_api_key"]
        else:
            k = json.load(open(r"C:\Users\Asmita\.config\claude-seo\google-api.json"))["api_key"]
        body = json.dumps({"origin": origin}).encode()
        req = urllib.request.Request(
            "https://chromeuxreport.googleapis.com/v1/records:queryRecord?key=" + k,
            data=body, headers={"Content-Type": "application/json"})
        m = json.load(urllib.request.urlopen(req))["record"]["metrics"]
        def p75(x):
            val = m.get(x, {}).get("percentiles", {}).get("p75")
            try: return float(val)
            except (TypeError, ValueError): return None
        return {
            "LCP": p75("largest_contentful_paint"),
            "INP": p75("interaction_to_next_paint"),
            "CLS": p75("cumulative_layout_shift"),
        }, None
    except Exception as e:
        return None, str(e)

# ── GA4: WhatsApp CTA clicks by campaign (UTM) ────────────────────────
@st.cache_data(ttl=3600)
def fetch_wa_clicks(prop_id, days=90):
    """CTA/URL-button clicks land on chuk.in tagged utm_source=whatsapp.
    WhatsApp gives no click webhook, so GA4 UTM is the only source. Returns (rows, error)."""
    try:
        client = get_client()
        req = RunReportRequest(
            property=prop_id,
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
            dimensions=[Dimension(name="sessionCampaignName")],
            metrics=[Metric(name="sessions"), Metric(name="keyEvents")],
            dimension_filter=FilterExpression(filter=Filter(
                field_name="sessionSource",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.CONTAINS, value="whatsapp"))),
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
            limit=50,
        )
        r = client.run_report(req)
        return [{"campaign": row.dimension_values[0].value,
                 "clicks": int(row.metric_values[0].value),
                 "conv": int(row.metric_values[1].value)} for row in r.rows], None
    except Exception as e:
        return None, str(e)

# ── DONE-STATE persistence ────────────────────────────────────────────
DONE_FILE = os.path.join(os.path.dirname(__file__), "_action_done.json")
def load_done():
    try: return set(json.load(open(DONE_FILE)))
    except Exception: return set()
def save_done(done):
    try: json.dump(sorted(done), open(DONE_FILE, "w"))
    except Exception: pass

# ── HELPERS ───────────────────────────────────────────────────────────
def v(row, mi):   return row.metric_values[mi].value
def d(row, di):   return row.dimension_values[di].value
def fmt_dur(sec): s=int(float(sec)); return f"{s//60}m {s%60}s"
def pct(a, b):    return round(int(float(a))/b*100, 1) if b else 0

def _num(x):
    try: return int(float(str(x).replace(",", "").replace("%", "").strip() or 0))
    except (TypeError, ValueError): return 0

def parse_wa_csv(raw_bytes):
    """Parse a WhatsApp Manager template-insights CSV. Flexible column matching.
    Returns list of {name, sent, delivered, read, clicked, failed}."""
    try:
        text = raw_bytes.decode("utf-8-sig")
    except Exception:
        text = raw_bytes.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    def col(*needles):
        for h in reader.fieldnames:
            hl = (h or "").lower()
            if any(n in hl for n in needles):
                return h
        return None
    c_name = col("template", "campaign", "name", "message")
    c_sent = col("sent")
    c_deliv = col("deliver")
    c_read = col("read")
    c_click = col("click", "cta", "tap")
    c_fail = col("fail", "undeliver")
    if not c_name or not (c_deliv or c_sent):
        return []
    out = []
    for r in reader:
        sent = _num(r.get(c_sent)) if c_sent else 0
        deliv = _num(r.get(c_deliv)) if c_deliv else 0
        fail = _num(r.get(c_fail)) if c_fail else max(sent - deliv, 0)
        name = (r.get(c_name) or "").strip()
        if not name:
            continue
        out.append({
            "name": name, "sent": sent, "delivered": deliv,
            "read": _num(r.get(c_read)) if c_read else 0,
            "clicked": _num(r.get(c_click)) if c_click else 0,
            "failed": fail,
        })
    return out

def render_wa_funnel(rows):
    """Render funnel table + best/worst + 'could do better' flags from normalized rows."""
    tot_d = sum(r["delivered"] for r in rows) or 1
    ctrs = [r["clicked"] / (r["delivered"] or 1) for r in rows if r["delivered"] >= 50]
    median_ctr = sorted(ctrs)[len(ctrs)//2] if ctrs else 0
    table = []
    for r in rows:
        d_ = r["delivered"] or 1
        ctr = round(r["clicked"] / d_ * 100, 2)
        flag = ""
        if r["delivered"] >= 50 and r["clicked"] / d_ < median_ctr:
            flag = "⚠️ below median"
        table.append({
            "Template": r["name"],
            "Sent": r["sent"], "Reached": r["delivered"], "Failed": r["failed"],
            "Read %": round(r["read"] / d_ * 100, 1),
            "CTA Clicks": r["clicked"], "CTR %": ctr,
            "Verdict": flag,
        })
    table.sort(key=lambda x: x["CTR %"], reverse=True)
    st.dataframe(table, use_container_width=True)
    if table:
        best, worst = table[0], table[-1]
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Reached", f"{int(tot_d):,}")
        c2.metric("Best CTR", f"{best['CTR %']}%", best["Template"][:18])
        c3.metric("Worst CTR", f"{worst['CTR %']}%", worst["Template"][:18])

# ── SIDEBAR ───────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🧠 GA4 Brain")
    mode      = st.radio("Mode", ["Single Property", "Compare: CHUK vs Pakka"])
    if mode == "Single Property":
        prop_name = st.selectbox("Property", list(PROPERTIES.keys()))
        prop_id   = PROPERTIES[prop_name]
    days_opt  = st.selectbox("Period", ["7daysAgo","30daysAgo","90daysAgo"], index=1)
    view      = st.radio("View", ["⚡ Action Center","🔴 Real-Time","🎯 UTM Campaigns","Dashboard","Graph Network","Channels","Pages","Sources","Geographic","Funnel Analysis","📱 Meta","Recommendations"])
    st.divider()
    st.caption(f"Updated: {date.today()}")
    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()

# ── LOAD ──────────────────────────────────────────────────────────────
try:
    client = get_client()
    if mode == "Compare: CHUK vs Pakka":
        with st.spinner("Fetching CHUK + Pakka data..."):
            data_chuk  = fetch(client, "properties/364059461", days_opt)
            data_pakka = fetch(client, "properties/488074493", days_opt)
        data     = data_chuk
        prop_name = "CHUK - GA4 (chuk.in)"
        prop_id   = "properties/364059461"
    else:
        with st.spinner("Fetching live GA4 data..."):
            data = fetch(client, prop_id, days_opt)
except Exception as e:
    st.error(f"Auth error: {e}")
    st.stop()

def extract_kpis(d):
    ov = d["overview"].rows[0]
    return {
        "sessions":  int(v(ov,0)),
        "users":     int(v(ov,1)),
        "new_users": int(v(ov,2)),
        "pv":        int(v(ov,3)),
        "bounce":    round(float(v(ov,4))*100,1),
        "dur":       fmt_dur(v(ov,5)),
        "ch_dict":   {d_(r,0): int(v(r,0)) for r in d["channels"].rows},
    }

def d_(row, i): return row.dimension_values[i].value  # alias to avoid shadowing

kpis = extract_kpis(data)
total_sess  = kpis["sessions"]
total_users = kpis["users"]
total_new   = kpis["new_users"]
total_pv    = kpis["pv"]
bounce      = kpis["bounce"]
avg_dur     = kpis["dur"]
ch_dict     = kpis["ch_dict"]

# ── COMPARE VIEW ──────────────────────────────────────────────────────
if mode == "Compare: CHUK vs Pakka":
    kpis_c = extract_kpis(data_chuk)
    kpis_p = extract_kpis(data_pakka)

    st.title("📊 CHUK vs Pakka — Side by Side")

    # KPI comparison
    metrics = [("Sessions","sessions"),("Active Users","users"),("New Users","new_users"),
               ("Page Views","pv"),("Bounce Rate","bounce"),("Avg Duration","dur")]
    cols = st.columns(len(metrics))
    for col, (label, key) in zip(cols, metrics):
        vc = kpis_c[key]
        vp = kpis_p[key]
        if isinstance(vc, float):
            delta = f"Pakka: {vp}%"
        elif isinstance(vc, int):
            delta = f"Pakka: {vp:,}"
        else:
            delta = f"Pakka: {vp}"
        col.metric(f"CHUK — {label}", f"{vc:,}" if isinstance(vc,int) else str(vc), delta=delta)

    st.divider()

    # Channel comparison
    c1, c2 = st.columns(2)
    for col, d_data, title in [(c1, data_chuk,"CHUK - chuk.in"),(c2, data_pakka,"Pakka - pakka.com")]:
        with col:
            st.subheader(title)
            ch_r = d_data["channels"].rows
            tot  = sum(int(v(r,0)) for r in ch_r)
            fig = go.Figure(go.Pie(
                labels=[d_(r,0) for r in ch_r],
                values=[int(v(r,0)) for r in ch_r],
                hole=0.5, textinfo="label+percent",
                marker_colors=["#4285f4","#aaa","#34a853","#ea4335","#fbbc04","#666","#9c27b0"][:len(ch_r)]
            ))
            fig.update_layout(paper_bgcolor="#1e2130", font_color="#ccc",
                height=250, showlegend=False, margin=dict(l=0,r=0,t=0,b=0))
            st.plotly_chart(fig, use_container_width=True)

            # Daily trend
            dates_  = [d_(r,0)[4:] for r in d_data["daily"].rows]
            sess_v_ = [int(v(r,0)) for r in d_data["daily"].rows]
            fig2 = go.Figure(go.Scatter(x=dates_, y=sess_v_, fill="tozeroy",
                line=dict(color="#4285f4" if title.startswith("CHUK") else "#34a853", width=2),
                fillcolor="rgba(66,133,244,0.1)" if title.startswith("CHUK") else "rgba(52,168,83,0.1)"))
            fig2.update_layout(paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
                font_color="#ccc", height=180, margin=dict(l=0,r=0,t=0,b=0),
                showlegend=False, xaxis=dict(showgrid=False), yaxis=dict(showgrid=False))
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # Source comparison table
    st.subheader("Top Sources — CHUK vs Pakka")
    chuk_src  = {d_(r,0): int(v(r,0)) for r in data_chuk["sources"].rows}
    pakka_src = {d_(r,0): int(v(r,0)) for r in data_pakka["sources"].rows}
    all_src   = sorted(set(list(chuk_src.keys())[:20] + list(pakka_src.keys())[:20]))
    cmp_rows  = [{"Source/Medium": s,
                  "CHUK Sessions": chuk_src.get(s,0),
                  "Pakka Sessions": pakka_src.get(s,0),
                  "Difference": chuk_src.get(s,0) - pakka_src.get(s,0)}
                 for s in all_src if chuk_src.get(s,0)+pakka_src.get(s,0) > 0]
    cmp_rows.sort(key=lambda x: x["CHUK Sessions"]+x["Pakka Sessions"], reverse=True)
    st.dataframe(cmp_rows[:25], use_container_width=True)

    st.divider()

    # Top pages comparison
    st.subheader("Top Pages Comparison")
    c1, c2 = st.columns(2)
    for col, d_data, title, color in [
        (c1, data_chuk,"CHUK","#4285f4"),
        (c2, data_pakka,"Pakka","#34a853")
    ]:
        with col:
            st.caption(title)
            rows_ = d_data["pages"].rows[:10]
            fig = go.Figure(go.Bar(
                y=[d_(r,0)[:35] for r in rows_],
                x=[int(v(r,0)) for r in rows_],
                orientation="h", marker_color=color
            ))
            fig.update_layout(paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
                font_color="#ccc", height=320, margin=dict(l=0,r=0,t=0,b=0),
                yaxis=dict(autorange="reversed"), xaxis=dict(showgrid=False))
            st.plotly_chart(fig, use_container_width=True)

    st.stop()  # Don't render single-property views below

# ── ACTION CENTER ─────────────────────────────────────────────────────
if view == "⚡ Action Center":
    st.title(f"⚡ Action Center — {prop_name}")
    st.caption(f"Ranked, data-driven actions. Period {days_opt} vs prior {days_opt}. Most impact first.")

    actions = []  # each: dict(id, sev, icon, title, detail, impact, view)
    def add(id, sev, title, detail, impact="", view_jump=""):
        actions.append(dict(id=id, sev=sev, title=title, detail=detail, impact=impact, view=view_jump))

    # prev-period lookups
    prev_sess = int(v(data["overview_prev"].rows[0], 0)) if data["overview_prev"].rows else 0
    src_prev  = {d(r, 0): int(v(r, 0)) for r in data["sources_prev"].rows}

    # RULE 1 — overall traffic WoW
    if prev_sess:
        chg = round((total_sess - prev_sess) / prev_sess * 100, 1)
        if chg <= -15:
            add("traffic_drop", 1, f"Traffic down {abs(chg)}% vs prior period",
                f"{total_sess:,} sessions now vs {prev_sess:,} before. Find which source fell (below) and act.",
                f"{prev_sess-total_sess:,} sessions lost", "Sources")
        elif chg >= 20:
            add("traffic_up", 3, f"Traffic up {chg}% — capitalize",
                f"{total_sess:,} vs {prev_sess:,}. Identify the winning source below and double the activity that drove it.",
                f"+{total_sess-prev_sess:,} sessions", "Sources")

    # RULE 2 — source drops/spikes WoW
    for r in data["sources"].rows[:30]:
        sm = d(r, 0); cur = int(v(r, 0)); prev = src_prev.get(sm, 0)
        if cur < 30 and prev < 30: continue
        if prev >= 30 and cur < prev * 0.7:
            drop = round((1 - cur/prev) * 100, 1)
            add(f"src_drop_{sm}", 2, f"{sm} fell {drop}%",
                f"{prev:,} → {cur:,} sessions. Resume / fix whatever drove this source.",
                f"-{prev-cur:,} sessions", "Sources")
        elif prev >= 20 and cur > prev * 1.6:
            add(f"src_spike_{sm}", 3, f"{sm} surged {round((cur/prev-1)*100)}%",
                f"{prev:,} → {cur:,} sessions. Whatever you did here — do more of it.",
                f"+{cur-prev:,} sessions", "Sources")

    # RULE 3 — bounce leaks (high traffic + high bounce pages)
    leaks = []
    for r in data["funnel_pages"].rows:
        sess = int(v(r, 0)); br = float(v(r, 2))
        if sess >= 50 and br >= 0.70:
            leaks.append((d(r, 0), sess, br, round(sess * br)))
    leaks.sort(key=lambda x: x[3], reverse=True)
    for path, sess, br, lost in leaks[:6]:
        add(f"bounce_{path}", 1 if lost >= 100 else 2,
            f"Bounce leak: {path[:45]}",
            f"{sess:,} sessions, {round(br*100)}% bounce. Add a clear CTA / product link above the fold.",
            f"~{lost:,} users lost", "Funnel Analysis")

    # RULE 4 — paid waste (cpc sources with high bounce)
    for r in data["sources"].rows:
        sm = d(r, 0); sess = int(v(r, 0)); br = float(v(r, 2))
        if "cpc" in sm.lower() and sess >= 30 and br >= 0.70:
            add(f"paid_waste_{sm}", 1, f"Ad spend leaking: {sm}",
                f"{sess:,} paid sessions, {round(br*100)}% bounce — you pay then they leave. Fix landing page or pause keyword.",
                f"~{round(sess*br):,} wasted clicks", "Sources")

    # RULE 5 — UTM gap (untagged direct/referral)
    untagged = ch_dict.get("Direct", 0) + ch_dict.get("Referral", 0) + ch_dict.get("Unassigned", 0)
    if untagged >= 100:
        add("utm_gap", 2, f"{untagged:,} untagged sessions invisible",
            "Direct + Referral + Unassigned = links you shared but didn't tag (WhatsApp, IG bio, email). "
            "Use the UTM builder so you can see what each channel actually drives.",
            f"{round(untagged/total_sess*100)}% of all traffic blind", "🎯 UTM Campaigns")

    # RULE 6 — Core Web Vitals (CrUX)
    crux, crux_err = fetch_crux("https://chuk.in")
    if crux:
        lcp = crux.get("LCP")
        if lcp and lcp > 4000:
            add("cwv_lcp", 1, f"Site slow: LCP {lcp/1000:.1f}s on mobile",
                "Real users wait too long for main content (>4s = poor). Compress hero image, lazy-load below-fold, enable caching. Slow pages lose ~7% conversions per extra second.",
                "Affects every visitor", "")
        elif lcp and lcp > 2500:
            add("cwv_lcp", 2, f"LCP {lcp/1000:.1f}s — needs improvement",
                "Above the 2.5s 'good' threshold. Optimize largest image / server response.", "Affects every visitor", "")
        inp = crux.get("INP")
        if inp and inp > 200:
            add("cwv_inp", 2, f"Sluggish taps: INP {inp}ms",
                "Buttons/menus feel laggy (>200ms). Reduce heavy JS on load.", "Mobile UX", "")
        cls = crux.get("CLS")
        if cls and cls > 0.1:
            add("cwv_cls", 2, f"Layout shifts: CLS {cls}",
                "Page jumps as it loads (>0.1). Set width/height on images & ads.", "Mobile UX", "")

    # RULE 7 — GSC striking-distance keywords (pos 5-15)
    gsc_rows, gsc_err = fetch_gsc()
    if gsc_rows is None:
        add("gsc_reconnect", 2, "Reconnect Search Console for SEO quick-wins",
            f"GSC token expired ({(gsc_err or '')[:60]}). Run in terminal: "
            "`! python ../gsc_reauth.py` — unlocks keyword rankings & striking-distance targets.",
            "Free SEO wins blocked", "")
    elif gsc_rows:
        strikers = [r for r in gsc_rows if 5 <= r["position"] <= 15 and r["impressions"] >= 100]
        strikers.sort(key=lambda r: r["impressions"] * (1 - r.get("ctr", 0)), reverse=True)
        for r in strikers[:6]:
            kw = r["keys"][0]; pos = round(r["position"], 1); impr = int(r["impressions"])
            add(f"gsc_{kw}", 3, f"Page-2 keyword: '{kw[:40]}'",
                f"Ranking #{pos}, {impr:,} impressions, {round(r.get('ctr',0)*100,1)}% CTR. "
                "Improve that page (title/H1/content depth) → page-1 traffic with no new content.",
                f"{impr:,} impressions/mo waiting", "")

    # ── render ──
    done = load_done()
    SEV = {1: ("warn", "🔴", "CRITICAL"), 2: ("info", "🟠", "HIGH"), 3: ("ok", "🟢", "OPPORTUNITY")}
    live = [a for a in actions if a["id"] not in done]
    live.sort(key=lambda a: a["sev"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open Actions", len(live))
    c2.metric("🔴 Critical", len([a for a in live if a["sev"] == 1]))
    c3.metric("🟠 High", len([a for a in live if a["sev"] == 2]))
    c4.metric("🟢 Opportunities", len([a for a in live if a["sev"] == 3]))
    st.divider()

    if not live:
        st.markdown('<div class="ok">✅ <b>No open actions.</b> Either all clear, or you dismissed them — uncheck below to review.</div>', unsafe_allow_html=True)

    for a in live:
        cls, icon, tag = SEV[a["sev"]]
        impact = f" · <b>{a['impact']}</b>" if a["impact"] else ""
        jump = f" · <i>→ {a['view']} tab</i>" if a["view"] else ""
        cc1, cc2 = st.columns([10, 1])
        with cc1:
            st.markdown(
                f'<div class="{cls}">{icon} <b>[{tag}]</b> {a["title"]}{impact}<br>'
                f'<span style="font-size:0.85rem;opacity:0.85">{a["detail"]}{jump}</span></div>',
                unsafe_allow_html=True)
        with cc2:
            if st.checkbox("Done", key=f"done_{a['id']}"):
                done.add(a["id"]); save_done(done); st.rerun()

    if done:
        with st.expander(f"✅ Dismissed ({len(done)}) — click to restore"):
            for did in sorted(done):
                if st.button(f"↩ Restore: {did}", key=f"r_{did}"):
                    done.discard(did); save_done(done); st.rerun()

# ── REAL-TIME ─────────────────────────────────────────────────────────
elif view == "🔴 Real-Time":
    st.title(f"🔴 Live — {prop_name}")
    st.caption("Active users in the last 30 minutes. Auto-refreshes every 30s. "
               "Note: GA4 Realtime API has no source/medium — for UTM/source tracking use the UTM Campaigns view.")

    @st.fragment(run_every="30s")
    def live_panel():
        try:
            rd = fetch_realtime(client, prop_id)
        except Exception as e:
            st.error(f"Realtime fetch error: {e}")
            return

        now_users = int(v(rd["now"].rows[0], 0)) if rd["now"].rows else 0
        ev_total  = sum(int(v(r, 0)) for r in rd["events"].rows)
        from datetime import datetime
        c1, c2, c3 = st.columns(3)
        c1.metric("🟢 Active Users Now", f"{now_users:,}")
        c2.metric("Events (30 min)", f"{ev_total:,}")
        c3.metric("Last refresh", datetime.now().strftime("%H:%M:%S"))

        # Trend by minute (minutesAgo: 0 = now)
        st.subheader("Active Users — Last 30 Minutes")
        mins = {int(d(r, 0)): int(v(r, 0)) for r in rd["by_min"].rows}
        x = list(range(29, -1, -1))                       # 29 min ago → now
        y = [mins.get(m, 0) for m in x]
        xlabels = [f"-{m}m" if m else "now" for m in x]
        fig = go.Figure(go.Bar(x=xlabels, y=y, marker_color="#34a853"))
        fig.update_layout(paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
            font_color="#ccc", height=220, margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(showgrid=False), yaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Live Pages")
            if rd["pages"].rows:
                st.dataframe([{
                    "Page": d(r, 0)[:50], "Active": int(v(r, 0)), "Views": int(v(r, 1))
                } for r in rd["pages"].rows], use_container_width=True, hide_index=True)
            else:
                st.info("No active users right now.")
            st.subheader("Live Events")
            if rd["events"].rows:
                st.dataframe([{
                    "Event": d(r, 0), "Count": int(v(r, 0))
                } for r in rd["events"].rows], use_container_width=True, hide_index=True)
        with col2:
            st.subheader("Live Locations")
            if rd["city"].rows:
                cit = [r for r in rd["city"].rows if d(r, 0) not in ["(not set)", ""]]
                st.dataframe([{
                    "City": d(r, 0), "Country": "", "Active": int(v(r, 0))
                } for r in cit] or [{"City": "—", "Active": 0}],
                    use_container_width=True, hide_index=True)
            st.subheader("Live Devices")
            if rd["device"].rows:
                fig2 = go.Figure(go.Pie(
                    labels=[d(r, 0) for r in rd["device"].rows],
                    values=[int(v(r, 0)) for r in rd["device"].rows],
                    marker_colors=["#4285f4", "#34a853", "#fbbc04"], hole=0.5,
                    textinfo="label+value"))
                fig2.update_layout(paper_bgcolor="#1e2130", font_color="#ccc",
                    height=240, showlegend=False, margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig2, use_container_width=True)

    live_panel()

# ── UTM CAMPAIGNS ─────────────────────────────────────────────────────
elif view == "🎯 UTM Campaigns":
    st.title(f"🎯 UTM Campaign Tracking — {prop_name}")
    st.caption("All UTM-tagged traffic. Excludes untagged organic/direct so you see only links you built and shared.")

    # Untagged buckets to hide so only real campaigns show
    SKIP_CAMP = {"(not set)", "(organic)", "(direct)", "(referral)", "(data deleted)"}

    utm_rows = [r for r in data["utm"].rows if d(r, 0) not in SKIP_CAMP]
    camp_rows = [r for r in data["utm_campaign"].rows if d(r, 0) not in SKIP_CAMP]

    if not utm_rows:
        st.markdown('<div class="warn">⚠️ <b>No UTM-tagged traffic found in this period.</b> '
                    'Your shared links (WhatsApp, Instagram bio, email, LinkedIn) are not tagged — '
                    'they fall into Direct/Referral and are invisible here. Use the link builder below to fix that.</div>',
                    unsafe_allow_html=True)
    else:
        tot_utm = sum(int(v(r, 0)) for r in utm_rows)
        tot_conv = sum(int(float(v(r, 5))) for r in utm_rows)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("UTM Sessions", f"{tot_utm:,}")
        c2.metric("Campaigns", f"{len(camp_rows)}")
        c3.metric("Conversions (UTM)", f"{tot_conv:,}")
        c4.metric("Conv. Rate", f"{round(tot_conv/tot_utm*100,1)}%" if tot_utm else "0%")

        st.divider()
        c1, c2 = st.columns([3, 2])
        with c1:
            st.subheader("Sessions by Campaign")
            fig = go.Figure(go.Bar(
                y=[d(r, 0)[:35] for r in camp_rows[:15]],
                x=[int(v(r, 0)) for r in camp_rows[:15]],
                orientation="h", marker_color="#9c27b0",
                text=[int(v(r, 0)) for r in camp_rows[:15]], textposition="outside"))
            fig.update_layout(paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
                font_color="#ccc", height=400, yaxis=dict(autorange="reversed"),
                xaxis=dict(showgrid=False), margin=dict(l=0, r=40, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("Medium Split")
            med = {}
            for r in utm_rows:
                med[d(r, 2)] = med.get(d(r, 2), 0) + int(v(r, 0))
            fig2 = go.Figure(go.Pie(labels=list(med.keys()), values=list(med.values()),
                hole=0.5, textinfo="label+percent"))
            fig2.update_layout(paper_bgcolor="#1e2130", font_color="#ccc",
                height=400, showlegend=False, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Full UTM Breakdown — Campaign / Source / Medium")
        st.dataframe([{
            "Campaign": d(r, 0), "Source": d(r, 1), "Medium": d(r, 2),
            "Sessions": int(v(r, 0)), "Users": int(v(r, 1)), "New": int(v(r, 2)),
            "Bounce": f"{round(float(v(r,3))*100,1)}%",
            "Avg Dur": fmt_dur(v(r, 4)),
            "Conv": int(float(v(r, 5))),
        } for r in utm_rows], use_container_width=True, hide_index=True)

    # ── UTM LINK BUILDER ──────────────────────────────────────────────
    st.divider()
    st.subheader("🔧 UTM Link Builder")
    st.caption("Build tagged links so future traffic shows up above instead of as Direct.")
    bc1, bc2 = st.columns(2)
    with bc1:
        base = st.text_input("Landing URL", "https://chuk.in/")
        u_src = st.selectbox("Source (utm_source)",
            ["whatsapp", "instagram", "facebook", "linkedin", "youtube", "email", "newsletter", "telegram"])
        u_med = st.selectbox("Medium (utm_medium)",
            ["social", "bio", "story", "post", "email", "cpc", "referral", "qr"])
    with bc2:
        u_camp = st.text_input("Campaign (utm_campaign)", "jun2026_launch")
        u_cont = st.text_input("Content (utm_content) — optional", "")
        u_term = st.text_input("Term (utm_term) — optional", "")
    from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
    params = {"utm_source": u_src, "utm_medium": u_med, "utm_campaign": u_camp}
    if u_cont: params["utm_content"] = u_cont
    if u_term: params["utm_term"] = u_term
    parsed = urlparse(base)
    merged = dict(parse_qsl(parsed.query)); merged.update(params)
    final_url = urlunparse(parsed._replace(query=urlencode(merged)))
    st.code(final_url, language="text")
    st.caption("Copy this link. Use it in your WhatsApp broadcast / IG bio / email. "
               "It will appear in the table above within ~24h of first click.")

# ── DASHBOARD ─────────────────────────────────────────────────────────
elif view == "Dashboard":
    st.title(f"📊 {prop_name}")

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    for col, label, val in [
        (c1,"Sessions",f"{total_sess:,}"),
        (c2,"Active Users",f"{total_users:,}"),
        (c3,"New Users",f"{total_new:,}"),
        (c4,"Page Views",f"{total_pv:,}"),
        (c5,"Bounce Rate",f"{bounce}%"),
        (c6,"Avg Duration",avg_dur),
    ]:
        col.metric(label, val)

    st.divider()
    col1, col2 = st.columns([2,1])

    with col1:
        st.subheader("30-Day Traffic Trend")
        dates  = [d(r,0)[4:] for r in data["daily"].rows]
        sess_v = [int(v(r,0)) for r in data["daily"].rows]
        user_v = [int(v(r,1)) for r in data["daily"].rows]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=sess_v, name="Sessions", fill="tozeroy",
            line=dict(color="#4285f4", width=2), fillcolor="rgba(66,133,244,0.15)"))
        fig.add_trace(go.Scatter(x=dates, y=user_v, name="Users",
            line=dict(color="#34a853", width=2, dash="dot")))
        fig.update_layout(paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
            font_color="#ccc", legend=dict(bgcolor="#1e2130"), height=280,
            margin=dict(l=0,r=0,t=10,b=0))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Channel Split")
        labels = [d(r,0) for r in data["channels"].rows]
        values = [int(v(r,0)) for r in data["channels"].rows]
        colors = ["#4285f4","#aaa","#34a853","#ea4335","#fbbc04","#666","#9c27b0","#00bcd4"]
        fig2 = go.Figure(go.Pie(labels=labels, values=values,
            marker_colors=colors[:len(labels)], hole=0.5,
            textinfo="label+percent"))
        fig2.update_layout(paper_bgcolor="#1e2130", font_color="#ccc",
            height=280, showlegend=False, margin=dict(l=0,r=0,t=10,b=0))
        st.plotly_chart(fig2, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Top Landing Pages")
        lp = data["landing"].rows[:10]
        fig3 = go.Figure(go.Bar(
            y=[d(r,0)[:40] for r in lp],
            x=[int(v(r,0)) for r in lp],
            orientation="h", marker_color="#4285f4",
            text=[f"{pct(v(r,0),total_sess)}%" for r in lp],
        ))
        fig3.update_layout(paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
            font_color="#ccc", height=320, margin=dict(l=0,r=0,t=10,b=0),
            xaxis=dict(showgrid=False), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig3, use_container_width=True)

    with col4:
        st.subheader("Device Split")
        devs = data["devices"].rows
        fig4 = go.Figure(go.Bar(
            x=[d(r,0) for r in devs],
            y=[int(v(r,0)) for r in devs],
            marker_color=["#4285f4","#34a853","#fbbc04"]
        ))
        fig4.update_layout(paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
            font_color="#ccc", height=200, margin=dict(l=0,r=0,t=10,b=0),
            showlegend=False, xaxis=dict(showgrid=False), yaxis=dict(showgrid=False))
        st.plotly_chart(fig4, use_container_width=True)

        st.subheader("Top Countries")
        for r in data["countries"].rows[:5]:
            share = pct(v(r,0), total_sess)
            st.progress(min(100, int(share*2)), text=f"{d(r,0)} — {int(float(v(r,0))):,} ({share}%)")

# ── GRAPH NETWORK ─────────────────────────────────────────────────────
elif view == "Graph Network":
    st.title("🕸️ Traffic Graph Network")
    st.caption("Nodes = traffic sources/channels/pages. Size = session volume. Drag to explore.")

    nodes = []
    edges = []
    node_ids = {}

    def add_node(nid, label, group, size, info=""):
        if nid not in node_ids:
            node_ids[nid] = True
            nodes.append({"id": nid, "label": label[:30], "group": group,
                          "size": max(8, min(size, 60)), "info": info})

    def add_edge(src, tgt, weight=1):
        edges.append({"from": src, "to": tgt, "width": max(1, min(weight/50, 8))})

    # Center: property
    add_node("property", prop_name.split("(")[0].strip(), "property", 50)

    # Channels
    ch_colors = {"Organic Search":"organic","Direct":"direct","Referral":"referral",
                 "Organic Social":"social","Paid Search":"paid","Unassigned":"unassigned"}
    for r in data["channels"].rows:
        ch = d(r, 0)
        sess = int(v(r, 0))
        nid = f"ch_{ch}"
        add_node(nid, ch, ch_colors.get(ch, "other"), sess/80,
                 f"{sess:,} sessions | bounce {round(float(v(r,2))*100,1)}%")
        add_edge("property", nid, sess)

    # Sources -> Channels
    for r in data["sources"].rows[:25]:
        src = d(r, 0)
        sess = int(v(r, 0))
        bounce_v = round(float(v(r, 2))*100, 1)
        nid = f"src_{src}"
        # Determine channel
        if "organic" in src.lower() and "google" in src.lower():
            ch_nid = "ch_Organic Search"
        elif "direct" in src.lower() or "none" in src.lower():
            ch_nid = "ch_Direct"
        elif any(s in src.lower() for s in ["instagram","facebook","linkedin","twitter","youtube","whatsapp","telegram"]):
            ch_nid = "ch_Organic Social"
        elif "cpc" in src.lower():
            ch_nid = "ch_Paid Search"
        else:
            ch_nid = "ch_Referral"
        add_node(nid, src[:30], "source", sess/30,
                 f"{sess:,} sessions | bounce {bounce_v}%")
        if ch_nid in node_ids:
            add_edge(ch_nid, nid, sess)

    # Top landing pages -> sources
    for r in data["landing"].rows[:10]:
        page = d(r, 0)
        sess = int(v(r, 0))
        if page in ["(not set)", ""]: continue
        nid = f"page_{page}"
        add_node(nid, page[:35], "page", sess/60,
                 f"{sess:,} sessions | bounce {round(float(v(r,2))*100,1)}%")
        # Connect page to organic and direct
        for ch_nid in ["ch_Organic Search", "ch_Direct"]:
            if ch_nid in node_ids:
                add_edge(ch_nid, nid, sess//3)

    # Group colors
    group_colors = {
        "property": "#ffffff",
        "organic":  "#4285f4",
        "direct":   "#aaaaaa",
        "referral": "#34a853",
        "social":   "#ea4335",
        "paid":     "#fbbc04",
        "unassigned":"#666666",
        "other":    "#9c27b0",
        "source":   "#00bcd4",
        "page":     "#ff9800",
    }

    nodes_js   = json.dumps(nodes)
    edges_js   = json.dumps(edges)
    colors_js  = json.dumps(group_colors)

    html = f"""
<!DOCTYPE html>
<html>
<head>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  body {{ margin:0; background:#0e1117; }}
  #graph {{ width:100%; height:680px; border:1px solid #333; border-radius:8px; background:#0e1117; }}
  #tooltip {{ position:absolute; background:#1e2130; color:#fff; padding:8px 12px;
               border-radius:6px; font-size:12px; pointer-events:none; display:none;
               border:1px solid #444; max-width:200px; }}
  .legend {{ position:absolute; top:10px; right:10px; background:#1e2130;
             padding:10px; border-radius:6px; font-size:11px; color:#ccc; }}
  .leg-item {{ display:flex; align-items:center; gap:6px; margin:3px 0; }}
  .leg-dot {{ width:10px; height:10px; border-radius:50%; }}
</style>
</head>
<body>
<div id="graph"></div>
<div id="tooltip"></div>
<div class="legend">
  <div class="leg-item"><div class="leg-dot" style="background:#ffffff"></div>Property</div>
  <div class="leg-item"><div class="leg-dot" style="background:#4285f4"></div>Organic Search</div>
  <div class="leg-item"><div class="leg-dot" style="background:#aaaaaa"></div>Direct</div>
  <div class="leg-item"><div class="leg-dot" style="background:#34a853"></div>Referral</div>
  <div class="leg-item"><div class="leg-dot" style="background:#ea4335"></div>Social</div>
  <div class="leg-item"><div class="leg-dot" style="background:#fbbc04"></div>Paid</div>
  <div class="leg-item"><div class="leg-dot" style="background:#00bcd4"></div>Source</div>
  <div class="leg-item"><div class="leg-dot" style="background:#ff9800"></div>Page</div>
</div>
<script>
const rawNodes = {nodes_js};
const rawEdges = {edges_js};
const groupColors = {colors_js};

const nodes = new vis.DataSet(rawNodes.map(n => ({{
  id: n.id, label: n.label,
  title: n.info || n.label,
  size: n.size,
  color: {{ background: groupColors[n.group] || "#666", border: "#0e1117",
            highlight: {{ background: "#fff", border: "#fff" }} }},
  font: {{ color: "#ffffff", size: Math.max(10, n.size/3) }},
  shape: n.group === "property" ? "star" : n.group === "page" ? "diamond" : "dot",
}})));

const edges = new vis.DataSet(rawEdges.map((e,i) => ({{
  id: i, from: e.from, to: e.to,
  width: e.width,
  color: {{ color: "rgba(255,255,255,0.15)", highlight: "rgba(255,255,255,0.6)" }},
  smooth: {{ type: "curvedCW", roundness: 0.2 }},
  arrows: {{ to: {{ enabled: true, scaleFactor: 0.4 }} }},
}})));

const container = document.getElementById("graph");
const network = new vis.Network(container, {{ nodes, edges }}, {{
  physics: {{
    enabled: true,
    forceAtlas2Based: {{
      gravitationalConstant: -80,
      centralGravity: 0.005,
      springLength: 120,
      springConstant: 0.06,
      damping: 0.5,
    }},
    solver: "forceAtlas2Based",
    stabilization: {{ iterations: 200 }},
  }},
  interaction: {{
    hover: true, tooltipDelay: 100,
    navigationButtons: true, keyboard: true,
    zoomView: true,
  }},
  layout: {{ improvedLayout: true }},
}});

const tip = document.getElementById("tooltip");
network.on("hoverNode", function(p) {{
  const n = rawNodes.find(x => x.id === p.node);
  if (n) {{
    tip.innerHTML = "<strong>" + n.label + "</strong><br>" + (n.info || "");
    tip.style.display = "block";
  }}
}});
network.on("blurNode", () => tip.style.display = "none");
document.addEventListener("mousemove", e => {{
  tip.style.left = (e.clientX + 12) + "px";
  tip.style.top  = (e.clientY - 10) + "px";
}});
</script>
</body>
</html>
"""
    components.html(html, height=700, scrolling=False)

    col1, col2, col3 = st.columns(3)
    col1.metric("Nodes", len(nodes))
    col2.metric("Connections", len(edges))
    col3.metric("Sources mapped", len([n for n in nodes if n["group"]=="source"]))

# ── CHANNELS ──────────────────────────────────────────────────────────
elif view == "Channels":
    st.title("📡 Channel Analysis")
    ch_rows = data["channels"].rows
    labels  = [d(r,0) for r in ch_rows]
    sessions= [int(v(r,0)) for r in ch_rows]
    bounces = [round(float(v(r,2))*100,1) for r in ch_rows]
    colors  = ["#4285f4","#aaa","#34a853","#ea4335","#fbbc04","#666","#9c27b0","#00bcd4"]

    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure(go.Bar(y=labels, x=sessions, orientation="h",
            marker_color=colors[:len(labels)], text=sessions, textposition="outside"))
        fig.update_layout(title="Sessions by Channel", paper_bgcolor="#1e2130",
            plot_bgcolor="#1e2130", font_color="#ccc", height=350,
            yaxis=dict(autorange="reversed"), xaxis=dict(showgrid=False),
            margin=dict(l=0,r=60,t=40,b=0))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig2 = go.Figure(go.Bar(y=labels, x=bounces, orientation="h",
            marker_color="rgba(234,67,53,0.7)", text=[f"{b}%" for b in bounces], textposition="outside"))
        fig2.update_layout(title="Bounce Rate by Channel", paper_bgcolor="#1e2130",
            plot_bgcolor="#1e2130", font_color="#ccc", height=350,
            yaxis=dict(autorange="reversed"), xaxis=dict(showgrid=False),
            margin=dict(l=0,r=60,t=40,b=0))
        st.plotly_chart(fig2, use_container_width=True)

    st.dataframe([{
        "Channel": d(r,0), "Sessions": int(v(r,0)),
        "Share": f"{pct(v(r,0),total_sess)}%",
        "Active Users": int(v(r,1)),
        "Bounce Rate": f"{round(float(v(r,2))*100,1)}%"
    } for r in ch_rows], use_container_width=True)

# ── PAGES ─────────────────────────────────────────────────────────────
elif view == "Pages":
    st.title("📄 Top Pages")
    pages = data["pages"].rows[:15]
    c1,c2 = st.columns(2)
    with c1:
        fig = go.Figure(go.Bar(y=[d(r,0)[:40] for r in pages],
            x=[int(v(r,0)) for r in pages], orientation="h",
            marker_color="#4285f4"))
        fig.update_layout(title="Page Views", paper_bgcolor="#1e2130",
            plot_bgcolor="#1e2130", font_color="#ccc", height=400,
            yaxis=dict(autorange="reversed"), xaxis=dict(showgrid=False),
            margin=dict(l=0,r=0,t=40,b=0))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig2 = go.Figure(go.Bar(y=[d(r,0)[:40] for r in pages],
            x=[round(float(v(r,2))) for r in pages], orientation="h",
            marker_color="#34a853"))
        fig2.update_layout(title="Avg Time on Page (s)", paper_bgcolor="#1e2130",
            plot_bgcolor="#1e2130", font_color="#ccc", height=400,
            yaxis=dict(autorange="reversed"), xaxis=dict(showgrid=False),
            margin=dict(l=0,r=0,t=40,b=0))
        st.plotly_chart(fig2, use_container_width=True)

    st.dataframe([{
        "Page": d(r,0), "Views": int(v(r,0)),
        "Users": int(v(r,1)), "Avg Duration": fmt_dur(v(r,2))
    } for r in pages], use_container_width=True)

# ── SOURCES ───────────────────────────────────────────────────────────
elif view == "Sources":
    st.title("🔗 All Sources")
    rows = data["sources"].rows[:25]
    c1,c2 = st.columns(2)
    with c1:
        fig = go.Figure(go.Bar(y=[d(r,0)[:35] for r in rows],
            x=[int(v(r,0)) for r in rows], orientation="h",
            marker_color="#00bcd4"))
        fig.update_layout(title="Sessions by Source/Medium", paper_bgcolor="#1e2130",
            plot_bgcolor="#1e2130", font_color="#ccc", height=500,
            yaxis=dict(autorange="reversed"), xaxis=dict(showgrid=False),
            margin=dict(l=0,r=0,t=40,b=0))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig2 = go.Figure(go.Bar(y=[d(r,0)[:35] for r in rows],
            x=[round(float(v(r,2))*100,1) for r in rows], orientation="h",
            marker_color="rgba(234,67,53,0.7)"))
        fig2.update_layout(title="Bounce Rate by Source", paper_bgcolor="#1e2130",
            plot_bgcolor="#1e2130", font_color="#ccc", height=500,
            yaxis=dict(autorange="reversed"), xaxis=dict(showgrid=False),
            margin=dict(l=0,r=0,t=40,b=0))
        st.plotly_chart(fig2, use_container_width=True)

    ai_rows = [r for r in data["sources"].rows
               if any(x in d(r,0) for x in ["chatgpt","gemini","claude","perplexity","copilot"])]
    if ai_rows:
        st.subheader("AI Sources")
        c1,c2,c3,c4,c5 = st.columns(5)
        for col, r in zip([c1,c2,c3,c4,c5], ai_rows[:5]):
            col.metric(d(r,0).split("/")[0].strip(), f"{int(v(r,0)):,}")

# ── GEOGRAPHIC ────────────────────────────────────────────────────────
elif view == "Geographic":
    st.title("🌍 Geographic")
    c1,c2 = st.columns(2)
    with c1:
        cr = data["countries"].rows
        fig = go.Figure(go.Bar(y=[d(r,0) for r in cr],
            x=[int(v(r,0)) for r in cr], orientation="h",
            marker_color="#4285f4"))
        fig.update_layout(title="Top Countries", paper_bgcolor="#1e2130",
            plot_bgcolor="#1e2130", font_color="#ccc", height=320,
            yaxis=dict(autorange="reversed"), xaxis=dict(showgrid=False),
            margin=dict(l=0,r=0,t=40,b=0))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        cit = [r for r in data["cities"].rows if d(r,0) not in ["(not set)",""]][:12]
        fig2 = go.Figure(go.Bar(y=[d(r,0) for r in cit],
            x=[int(v(r,0)) for r in cit], orientation="h",
            marker_color="#34a853"))
        fig2.update_layout(title="Top Cities", paper_bgcolor="#1e2130",
            plot_bgcolor="#1e2130", font_color="#ccc", height=320,
            yaxis=dict(autorange="reversed"), xaxis=dict(showgrid=False),
            margin=dict(l=0,r=0,t=40,b=0))
        st.plotly_chart(fig2, use_container_width=True)

    devs = data["devices"].rows
    fig3 = go.Figure(go.Pie(
        labels=[d(r,0) for r in devs],
        values=[int(v(r,0)) for r in devs],
        marker_colors=["#4285f4","#34a853","#fbbc04"], hole=0.4))
    fig3.update_layout(title="Device Split", paper_bgcolor="#1e2130",
        font_color="#ccc", height=280, margin=dict(l=0,r=0,t=40,b=0))
    st.plotly_chart(fig3, use_container_width=True)

# ── FUNNEL ANALYSIS ───────────────────────────────────────────────────
elif view == "Funnel Analysis":
    st.title("🔻 Funnel & Drop-off Analysis")
    st.caption("Where customers leave before buying")

    # Page lookup helper
    page_data = {d(r,0): r for r in data["funnel_pages"].rows}

    def get_page(path):
        # Try exact and with/without trailing slash
        for key in [path, path.rstrip("/"), path + "/"]:
            if key in page_data:
                return page_data[key]
        return None

    # ── PRODUCT BUYING FUNNEL ─────────────────────────────────────────
    st.subheader("Product Purchase Funnel")

    product_funnel = [
        ("Homepage", "/"),
        ("Products Listing", "/products"),
        ("Product Page (avg)", "/products/disposable-meal-plates"),
        ("Sample Box Page", "/buy-sample-boxes"),
        ("Payment (CCAvenue)", "ccavenue"),
    ]

    # Get CCAvenue returns
    checkout_sess = 0
    if data["checkout_ref"].rows:
        checkout_sess = int(v(data["checkout_ref"].rows[0], 0))

    funnel_vals = []
    funnel_labels = []
    funnel_bounce = []
    funnel_dur = []

    for label, path in product_funnel:
        if path == "ccavenue":
            funnel_vals.append(checkout_sess)
            funnel_labels.append(label)
            funnel_bounce.append(0)
            funnel_dur.append(0)
        else:
            r = get_page(path)
            if r:
                funnel_vals.append(int(v(r,0)))
                funnel_bounce.append(round(float(v(r,2))*100,1))
                funnel_dur.append(round(float(v(r,3))))
            else:
                funnel_vals.append(0)
                funnel_bounce.append(0)
                funnel_dur.append(0)
            funnel_labels.append(label)

    # Funnel chart
    fig_funnel = go.Figure(go.Funnel(
        y=funnel_labels,
        x=funnel_vals,
        textinfo="value+percent initial",
        marker=dict(color=["#4285f4","#34a853","#fbbc04","#ea4335","#9c27b0"]),
        connector=dict(line=dict(color="#333", width=2)),
    ))
    fig_funnel.update_layout(
        paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
        font_color="#ccc", height=400,
        margin=dict(l=0,r=0,t=10,b=0)
    )
    st.plotly_chart(fig_funnel, use_container_width=True)

    # Drop-off table
    st.subheader("Drop-off at Each Stage")
    cols = st.columns(len(funnel_labels))
    for i, (col, label, val) in enumerate(zip(cols, funnel_labels, funnel_vals)):
        if i > 0 and funnel_vals[i-1] > 0:
            drop = round((1 - val/funnel_vals[i-1])*100, 1)
            col.metric(label, f"{val:,}", delta=f"-{drop}% from prev", delta_color="inverse")
        else:
            col.metric(label, f"{val:,}")

    st.divider()

    # ── ALL PAGES DROP-OFF TABLE ──────────────────────────────────────
    st.subheader("All Pages — Sessions Lost (Bounce)")

    page_rows = data["funnel_pages"].rows
    page_total_sess = sum(int(v(r,0)) for r in page_rows)

    table_data = []
    for r in page_rows[:30]:
        path = d(r,0)
        sess = int(v(r,0))
        bounce_v = round(float(v(r,2))*100,1)
        dur = round(float(v(r,3)))
        pv = int(v(r,4))
        lost = round(sess * float(v(r,2)))
        table_data.append({
            "Page": path[:50],
            "Sessions": sess,
            "Bounced": lost,
            "Bounce %": f"{bounce_v}%",
            "Avg Duration": fmt_dur(v(r,3)),
            "Page Views": pv,
            "Status": "CRITICAL" if bounce_v > 80 else "HIGH" if bounce_v > 60 else "OK" if bounce_v < 40 else "MEDIUM"
        })

    # Sort by sessions lost
    table_data.sort(key=lambda x: x["Bounced"], reverse=True)
    st.dataframe(table_data, use_container_width=True,
                 column_config={
                     "Status": st.column_config.TextColumn("Status"),
                     "Bounce %": st.column_config.TextColumn("Bounce %"),
                 })

    st.divider()

    # ── KEY DROP-OFF INSIGHTS ─────────────────────────────────────────
    st.subheader("Key Drop-off Problems")

    critical = [r for r in table_data if r["Status"] == "CRITICAL" and r["Sessions"] > 20]
    high     = [r for r in table_data if r["Status"] == "HIGH" and r["Sessions"] > 30]

    if critical:
        st.markdown("**CRITICAL — High traffic, very high bounce:**")
        for r in critical[:5]:
            st.markdown(f'<div class="warn">⚠️ <b>{r["Page"]}</b> — {r["Sessions"]:,} sessions, {r["Bounce %"]} bounce, {r["Bounced"]:,} users lost. Avg time: {r["Avg Duration"]}</div>', unsafe_allow_html=True)

    if high:
        st.markdown("**HIGH — Significant drop-off:**")
        for r in high[:5]:
            st.markdown(f'<div class="info">ℹ️ <b>{r["Page"]}</b> — {r["Sessions"]:,} sessions, {r["Bounce %"]} bounce, {r["Bounced"]:,} users lost</div>', unsafe_allow_html=True)

    # ── SPECIFIC FLOW FIX RECOMMENDATIONS ────────────────────────────
    st.divider()
    st.subheader("Fix Recommendations by Page Type")

    fixes = {
        "Blog pages (janmashtami, bistro, zomato)": [
            "Add 'Shop Now' CTA button after first 2 paragraphs",
            "Add product recommendation widget at end of post",
            "Add sticky sidebar with top 3 products",
            "Internal link: mention disposable plates naturally in food context"
        ],
        "/buy-sample-boxes": [
            "Check if CTA button is above the fold on mobile",
            "Add social proof: '500+ businesses ordered sample boxes'",
            "Add urgency: 'Ships within 24 hours'",
            "Reduce form fields if any — every field loses 10% conversion"
        ],
        "/products listing": [
            "Add filter by use-case (events, delivery, catering)",
            "Show price range prominently",
            "Add 'Most Popular' badge on top sellers",
            "Add WhatsApp chat widget for bulk order enquiry"
        ],
        "/distributors-2": [
            "Add lead form above the fold",
            "Add existing distributor logos/testimonials",
            "Show territory map — which areas still open",
            "Add WhatsApp direct link for distributor enquiry"
        ]
    }

    for page, tips in fixes.items():
        with st.expander(f"📄 {page}"):
            for tip in tips:
                st.markdown(f"- {tip}")

# ── RECOMMENDATIONS ───────────────────────────────────────────────────
elif view == "📱 Meta":
    st.title("📱 Meta — WhatsApp · Instagram · Facebook · Ads")
    cfg, cfg_err = meta_api.load_meta()
    if cfg_err:
        st.markdown(f'<div class="warn">⚠️ <b>Meta not connected</b> — {cfg_err}</div>', unsafe_allow_html=True)
        st.stop()

    meta_days = {"7daysAgo": 7, "30daysAgo": 30, "90daysAgo": 90}.get(days_opt, 30)

    def meta_card(err):
        st.markdown(f'<div class="info">ℹ️ {err}</div>', unsafe_allow_html=True)

    # ── WHATSAPP ──
    st.subheader("💬 WhatsApp Business")
    q, q_err = meta_api.wa_quality(cfg)
    if q_err:
        meta_card(q_err)
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Number", q.get("display_phone_number", "—"))
        c2.metric("Name", q.get("verified_name", "—"))
        c3.metric("Quality", q.get("quality_rating", "—"))
        c4.metric("Limit Tier", q.get("messaging_limit_tier", "—"))

    conv, conv_err = meta_api.wa_conversations(cfg, meta_days)
    if conv_err:
        meta_card(conv_err)
    elif conv:
        free = paid = 0
        for bucket in conv:
            for dp in bucket.get("data_points", []):
                cost = dp.get("cost", 0)
                cnt = dp.get("conversation", 0)
                if cost and cost > 0:
                    paid += cnt
                else:
                    free += cnt
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Conversations ({meta_days}d)", f"{free + paid:,}")
        c2.metric("Free", f"{free:,}")
        c3.metric("Paid", f"{paid:,}")

    # ── WHATSAPP CTA CLICKS (GA4 UTM) ──
    st.markdown("**CTA Clicks — from GA4 UTM** (WhatsApp sends no click webhook; this is the only click source)")
    wac, wac_err = fetch_wa_clicks(prop_id, 90)
    if wac_err:
        meta_card(wac_err)
    elif not wac:
        st.markdown('<div class="info">ℹ️ No WhatsApp-tagged sessions in GA4 (90d). Add <code>utm_source=whatsapp</code> to your link buttons.</div>', unsafe_allow_html=True)
    else:
        tot_clicks = sum(r["clicks"] for r in wac)
        c1, c2 = st.columns(2)
        c1.metric("WhatsApp CTA clicks (90d)", f"{tot_clicks:,}")
        c2.metric("Conversions", f"{sum(r['conv'] for r in wac):,}")
        st.dataframe([{"Campaign (UTM)": r["campaign"], "Site Clicks": r["clicks"],
                       "Conversions": r["conv"]} for r in wac], use_container_width=True)
        st.caption("Pair these clicks with each campaign's Delivered (from your platform / CSV below) for true CTR.")

    # ── WHATSAPP CAMPAIGN FUNNEL (platform API × GA4 clicks) ──
    st.markdown("**Campaign Funnel — delivery × CTR** (platform delivery joined to GA4 clicks)")
    pcfg, pcfg_err = platform_api.load_platform()
    if pcfg_err:
        meta_card(pcfg_err + " — CTA clicks above still work from GA4.")
    else:
        funnels, f_err = platform_api.campaign_funnels(pcfg)
        if f_err:
            meta_card("platform: " + f_err)
        elif not funnels:
            st.markdown('<div class="info">ℹ️ No campaigns returned from the platform.</div>', unsafe_allow_html=True)
        else:
            def _norm(s): return "".join(ch for ch in (s or "").lower() if ch.isalnum())
            click_idx = {_norm(r["campaign"]): r["clicks"] for r in (wac or [])}
            ftable = []
            for fn in funnels:
                d_ = fn["delivered"] or 1
                clicks = click_idx.get(_norm(fn["name"]), 0)
                ftable.append({
                    "Campaign": fn["name"], "Sent": fn["sent"], "Delivered": fn["delivered"],
                    "Failed": fn["failed"], "Read %": round(fn["read"] / d_ * 100, 1),
                    "CTA Clicks": clicks, "CTR %": round(clicks / d_ * 100, 2),
                })
            ftable.sort(key=lambda x: x["Delivered"], reverse=True)
            st.dataframe(ftable, use_container_width=True)
            st.caption("CTR = GA4 WhatsApp clicks ÷ platform Delivered. 0 clicks may mean the link wasn't UTM-tagged or names don't match.")

    # ── WHATSAPP TEMPLATES / CTR ──
    st.markdown("**Marketing Templates — CTR**")
    tpls, tpl_err = meta_api.wa_templates(cfg)
    if tpl_err:
        meta_card(tpl_err)
    elif tpls:
        ids = [t["id"] for t in tpls]
        id_name = {t["id"]: t.get("name", t["id"]) for t in tpls}
        pts, pts_err = meta_api.wa_template_analytics(cfg, ids, meta_days)
        if pts_err:
            meta_card(pts_err)
        elif not pts:
            st.markdown(
                '<div class="info">ℹ️ <b>No template CTR data from the API yet</b> '
                '(Meta\'s per-template history isn\'t exposed; the new pipeline takes ~48h). '
                f'{len(tpls)} approved templates. '
                '<b>Export the per-template CSV</b> from WhatsApp Manager → Insights → Download, '
                'and upload it below for the full funnel.</div>',
                unsafe_allow_html=True)
            up = st.file_uploader("Upload WhatsApp template insights CSV", type=["csv"], key="wa_csv")
            if up is not None:
                rows = parse_wa_csv(up.getvalue())
                if not rows:
                    st.markdown('<div class="warn">⚠️ Could not read sent/delivered/read/click columns from that CSV.</div>', unsafe_allow_html=True)
                else:
                    render_wa_funnel(rows)
            else:
                st.dataframe([{"Template": t.get("name"), "Status": t.get("status"),
                               "Category": t.get("category")} for t in tpls],
                             use_container_width=True)
        else:
            agg = {}
            for dp in pts:
                tid = dp.get("template_id") or (ids[0] if len(ids) == 1 else "?")
                a = agg.setdefault(tid, {"sent": 0, "delivered": 0, "read": 0, "clicked": 0})
                a["sent"] += int(dp.get("sent", 0) or 0)
                a["delivered"] += int(dp.get("delivered", 0) or 0)
                a["read"] += int(dp.get("read", 0) or 0)
                clk = dp.get("clicked", 0)
                if isinstance(clk, list):
                    clk = sum(int(c.get("count", 0) or 0) for c in clk)
                a["clicked"] += int(clk or 0)
            table = []
            for tid, a in agg.items():
                deliv = a["delivered"] or 1
                table.append({
                    "Template": id_name.get(tid, tid),
                    "Delivered": a["delivered"],
                    "Read %": round(a["read"] / deliv * 100, 1),
                    "Clicks": a["clicked"],
                    "CTR %": round(a["clicked"] / deliv * 100, 2),
                })
            table.sort(key=lambda r: r["CTR %"], reverse=True)
            st.dataframe(table, use_container_width=True)

    st.divider()

    # ── INSTAGRAM ──
    st.subheader("📸 Instagram")
    prof, prof_err = meta_api.ig_profile(cfg)
    if prof_err:
        meta_card(prof_err)
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("@" + prof.get("username", ""), "")
        c2.metric("Followers", f"{prof.get('followers_count', 0):,}")
        c3.metric("Posts", f"{prof.get('media_count', 0):,}")

        ins, ins_err = meta_api.ig_insights(cfg, meta_days)
        if not ins_err and ins:
            vals = {row.get("name"): (row.get("total_value", {}) or {}).get("value")
                    for row in ins.get("data", [])}
            c1, c2 = st.columns(2)
            c1.metric(f"Reach ({meta_days}d)", f"{vals.get('reach', 0):,}")
            c2.metric("Accounts Engaged", f"{vals.get('accounts_engaged', 0):,}")

        media, media_err = meta_api.ig_top_media(cfg)
        if not media_err and media:
            st.caption("Recent posts")
            rows = media.get("data", [])
            rows.sort(key=lambda m: m.get("like_count", 0), reverse=True)
            st.dataframe([{
                "Type": m.get("media_type", ""),
                "Likes": m.get("like_count", 0),
                "Comments": m.get("comments_count", 0),
                "Caption": (m.get("caption", "") or "")[:60],
                "Link": m.get("permalink", ""),
            } for m in rows[:8]], use_container_width=True)

    st.divider()

    # ── FACEBOOK ──
    st.subheader("👍 Facebook Page")
    fb, fb_err = meta_api.fb_insights(cfg, meta_days)
    if fb_err:
        meta_card(fb_err)
    elif fb:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Followers", f"{fb.get('followers', 0):,}")
        c2.metric(f"Page Views ({meta_days}d)", f"{fb.get('views', 0):,}")
        c3.metric("Post Engagements", f"{fb.get('engagements', 0):,}")
        c4.metric("New Follows", f"{fb.get('new_follows', 0):,}")
        if not (fb.get("views") or fb.get("engagements")):
            st.markdown(f'<div class="warn">⚠️ <b>{fb.get("name","Page")} is dormant</b> — 0 views/engagement in {meta_days}d. Post or retire it.</div>', unsafe_allow_html=True)

    st.divider()

    # ── META ADS ──
    st.subheader("📢 Meta Ads")
    ads_preset = {7: "last_7d", 30: "last_30d", 90: "last_90d"}.get(meta_days, "last_30d")
    ads, ads_err = meta_api.ads_insights(cfg, ads_preset)
    win = f"{meta_days}d"
    if not ads_err and not (ads or {}).get("data"):
        # No recent spend — show lifetime so dormant accounts still reveal history.
        ads, ads_err = meta_api.ads_insights(cfg, "maximum")
        win = "lifetime"
        if not ads_err and (ads or {}).get("data"):
            st.markdown(f'<div class="info">ℹ️ No spend in last {meta_days}d — showing <b>lifetime</b> history.</div>', unsafe_allow_html=True)
    if ads_err:
        meta_card(ads_err)
    elif ads:
        rows = ads.get("data", [])
        if not rows:
            st.markdown('<div class="info">ℹ️ No Meta ad spend on record.</div>', unsafe_allow_html=True)
        else:
            spend = sum(float(r.get("spend", 0) or 0) for r in rows)
            clicks = sum(int(r.get("clicks", 0) or 0) for r in rows)
            impr = sum(int(r.get("impressions", 0) or 0) for r in rows)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(f"Spend ({win})", f"₹{spend:,.0f}")
            c2.metric("Impressions", f"{impr:,}")
            c3.metric("Clicks", f"{clicks:,}")
            c4.metric("Avg CTR", f"{(clicks / impr * 100):.2f}%" if impr else "—")
            st.dataframe([{
                "Campaign": r.get("campaign_name", ""),
                "Spend": round(float(r.get("spend", 0) or 0), 2),
                "Impr.": int(r.get("impressions", 0) or 0),
                "Clicks": int(r.get("clicks", 0) or 0),
                "CTR %": round(float(r.get("ctr", 0) or 0), 2),
                "CPC": round(float(r.get("cpc", 0) or 0), 2),
            } for r in rows], use_container_width=True)

elif view == "Recommendations":
    st.title("💡 Recommendations")

    og_pct  = pct(ch_dict.get("Organic Search",0), total_sess)
    dir_pct = pct(ch_dict.get("Direct",0), total_sess)
    soc_pct = pct(ch_dict.get("Organic Social",0), total_sess)
    paid    = ch_dict.get("Paid Search",0)

    if og_pct > 50:
        st.markdown(f'<div class="warn">⚠️ <b>Google Organic = {og_pct}%</b> — single point of failure. One algorithm update wipes traffic.</div>', unsafe_allow_html=True)
    if dir_pct > 25:
        st.markdown(f'<div class="warn">⚠️ <b>Direct = {dir_pct}%</b> — inflated by untagged WhatsApp/email links. Add UTMs to all outbound links.</div>', unsafe_allow_html=True)
    if soc_pct < 5:
        st.markdown(f'<div class="warn">⚠️ <b>Social = {soc_pct}%</b> — target is 10-15%. Fix Instagram bio UTM. Post on LinkedIn 2x/week.</div>', unsafe_allow_html=True)
    if paid < 100:
        st.markdown('<div class="info">ℹ️ <b>Paid Search < 100 sessions</b> — untapped. Test Google Ads on "disposable plates bulk" and "eco-friendly food containers".</div>', unsafe_allow_html=True)

    if bounce > 50:
        st.markdown(f'<div class="warn">⚠️ <b>Bounce rate {bounce}%</b> — add product CTAs inside top blog posts.</div>', unsafe_allow_html=True)

    st.markdown('<div class="ok">✅ <b>Organic SEO working</b> — strong homepage + product page landing traffic.</div>', unsafe_allow_html=True)
    ai_total = sum(int(v(r,0)) for r in data["sources"].rows
                   if any(x in d(r,0) for x in ["chatgpt","gemini","claude","perplexity"]))
    if ai_total > 50:
        st.markdown(f'<div class="ok">✅ <b>AI referral = {ai_total} sessions</b> — growing channel. Ensure content has clear facts/stats for AI citation.</div>', unsafe_allow_html=True)

    st.divider()
    st.subheader("Priority Checklist")
    tasks = [
        ("P1 — Today","Fix Instagram bio link","chuk.in/?utm_source=instagram&utm_medium=social&utm_campaign=bio"),
        ("P1 — Today","Create 3 WhatsApp UTM links (bit.ly)","homepage + products + distributors"),
        ("P1 — Today","Fix (not set) tracking","GA4 Admin > Data Streams > unwanted referrals > add chuk.in"),
        ("P2 — This week","Add product CTAs to top 5 blog posts","Reduces 70% blog bounce"),
        ("P2 — This week","Connect Google Search Console","Unlocks keyword data"),
        ("P3 — Ongoing","LinkedIn 2x posts/week with UTM links","/distributors-2 target"),
        ("P4 — This month","Test Google Ads","High-intent keywords: disposable plates bulk"),
        ("P4 — This month","Start YouTube channel","Product demos + UTM in description"),
    ]
    for priority, action, detail in tasks:
        st.checkbox(f"**{priority}** — {action}", help=detail)
