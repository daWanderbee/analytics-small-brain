import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import json, math, os
from datetime import date
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, DateRange, Metric, Dimension, OrderBy,
    FilterExpression, FilterExpressionList, Filter
)
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import streamlit.components.v1 as components

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
    return data

# ── HELPERS ───────────────────────────────────────────────────────────
def v(row, mi):   return row.metric_values[mi].value
def d(row, di):   return row.dimension_values[di].value
def fmt_dur(sec): s=int(float(sec)); return f"{s//60}m {s%60}s"
def pct(a, b):    return round(int(float(a))/b*100, 1) if b else 0

# ── SIDEBAR ───────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🧠 GA4 Brain")
    mode      = st.radio("Mode", ["Single Property", "Compare: CHUK vs Pakka"])
    if mode == "Single Property":
        prop_name = st.selectbox("Property", list(PROPERTIES.keys()))
        prop_id   = PROPERTIES[prop_name]
    days_opt  = st.selectbox("Period", ["7daysAgo","30daysAgo","90daysAgo"], index=1)
    view      = st.radio("View", ["Dashboard","Graph Network","Channels","Pages","Sources","Geographic","Funnel Analysis","Recommendations"])
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

# ── DASHBOARD ─────────────────────────────────────────────────────────
if view == "Dashboard":
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
