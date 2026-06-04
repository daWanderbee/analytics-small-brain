import streamlit as st
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
from requests.auth import HTTPBasicAuth

st.set_page_config(
    page_title="CHUK Orders Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auth ──────────────────────────────────────────────────────────────────────
WC_BASE = "https://chuk.in/wp-json/wc/v3"
AUTH     = HTTPBasicAuth(
    st.secrets["woocommerce"]["user"],
    st.secrets["woocommerce"]["app_key"],
)

def make_session():
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

SESSION = make_session()

STATE_MAP = {
    "AP":"Andhra Pradesh","AR":"Arunachal Pradesh","AS":"Assam","BR":"Bihar",
    "CT":"Chhattisgarh","GA":"Goa","GJ":"Gujarat","HR":"Haryana","HP":"Himachal Pradesh",
    "JH":"Jharkhand","KA":"Karnataka","KL":"Kerala","MP":"Madhya Pradesh","MH":"Maharashtra",
    "MN":"Manipur","ML":"Meghalaya","MZ":"Mizoram","NL":"Nagaland","OD":"Odisha",
    "PB":"Punjab","RJ":"Rajasthan","SK":"Sikkim","TN":"Tamil Nadu","TS":"Telangana",
    "TR":"Tripura","UP":"Uttar Pradesh","UK":"Uttarakhand","WB":"West Bengal",
    "AN":"Andaman & Nicobar","CH":"Chandigarh","DN":"Dadra & Nagar Haveli","DD":"Daman & Diu",
    "DL":"Delhi","JK":"Jammu & Kashmir","LA":"Ladakh","LD":"Lakshadweep","PY":"Puducherry",
}

STATUS_COLOR = {
    "pending":    "#F59E0B",
    "processing": "#3B82F6",
    "on-hold":    "#8B5CF6",
    "completed":  "#10B981",
    "cancelled":  "#EF4444",
    "refunded":   "#F97316",
    "failed":     "#6B7280",
}

# ── Data fetch ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=180)
def fetch_orders(days_back: int, status_filter: str) -> pd.DataFrame:
    after = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00")
    params = {
        "per_page": 100,
        "orderby": "date",
        "order": "desc",
        "after": after,
    }
    if status_filter != "all":
        params["status"] = status_filter

    all_orders = []
    page = 1
    while True:
        params["page"] = page
        try:
            r = SESSION.get(f"{WC_BASE}/orders", params=params, auth=AUTH, timeout=30)
        except requests.exceptions.Timeout:
            st.warning(f"Page {page} timed out — showing {len(all_orders)} orders fetched so far.")
            break
        except requests.exceptions.RequestException as e:
            st.error(f"API error: {e}")
            break
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        all_orders.extend(batch)
        total_pages = int(r.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages or len(batch) < 100:
            break
        page += 1

    if not all_orders:
        return pd.DataFrame()

    rows = []
    for o in all_orders:
        items = o.get("line_items", [])
        is_sample = all("sample kit" in i["name"].lower() for i in items) if items else False
        product_names = "; ".join(f"{i['name']} x{i['quantity']}" for i in items)
        state_code = o["billing"].get("state", "")
        rows.append({
            "Order ID":    o["number"],
            "Date":        pd.to_datetime(o["date_created"]),
            "Status":      o["status"],
            "Type":        "Sample Kit" if is_sample else "Website Order",
            "Customer":    f"{o['billing'].get('first_name','')} {o['billing'].get('last_name','')}".strip(),
            "Email":       o["billing"].get("email", ""),
            "Phone":       o["billing"].get("phone", ""),
            "City":        o["billing"].get("city", "").title(),
            "State":       STATE_MAP.get(state_code, state_code),
            "State Code":  state_code,
            "Products":    product_names,
            "Subtotal":    float(o.get("subtotal", 0) or 0),
            "Tax":         float(o.get("total_tax", 0) or 0),
            "Shipping":    float(o.get("shipping_total", 0) or 0),
            "Total":       float(o.get("total", 0) or 0),
            "Payment":     o.get("payment_method_title", ""),
            "WC ID":       o["id"],
        })

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    df["Day"] = df["Date"].dt.date
    return df


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://chuk.in/wp-content/uploads/2023/10/CHUK-Logo.png", width=140)
    st.markdown("### Filters")

    days_back = st.selectbox("Date range", [7, 14, 30, 60, 90, 180, 365], index=2,
                              format_func=lambda x: f"Last {x} days")

    status_opts = ["all", "pending", "processing", "on-hold", "completed",
                   "cancelled", "refunded", "failed"]
    status_filter = st.selectbox("Status", status_opts)

    order_type = st.selectbox("Order type", ["All", "Sample Kit", "Website Order"])

    st.markdown("---")
    auto_refresh = st.toggle("Auto-refresh (3 min)", value=False)
    if st.button("🔄 Refresh now"):
        st.cache_data.clear()
        st.rerun()
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = time.time()
    st.caption(f"Last loaded: {datetime.fromtimestamp(st.session_state.last_refresh).strftime('%H:%M:%S')}")

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Fetching orders from chuk.in..."):
    df = fetch_orders(days_back, status_filter)

if df.empty:
    st.warning("No orders found for this filter.")
    st.stop()

if order_type != "All":
    df = df[df["Type"] == order_type]

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## 📦 CHUK Orders Dashboard")
st.caption(f"chuk.in  ·  Last {days_back} days  ·  {len(df)} orders")

# ── KPI row ───────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5, k6 = st.columns(6)

total_rev      = df["Total"].sum()
completed_rev  = df[df["Status"] == "completed"]["Total"].sum()
processing_cnt = (df["Status"] == "processing").sum()
pending_cnt    = (df["Status"] == "pending").sum()
sample_cnt     = (df["Type"] == "Sample Kit").sum()
website_cnt    = (df["Type"] == "Website Order").sum()

k1.metric("Total Orders",     len(df))
k2.metric("Total Revenue",    f"₹{total_rev:,.0f}")
k3.metric("Completed Rev",    f"₹{completed_rev:,.0f}")
k4.metric("Processing",       processing_cnt)
k5.metric("Pending",          pending_cnt)
k6.metric("Sample Kits",      sample_cnt)

st.markdown("---")

# ── Row 1: Orders over time + Status breakdown ────────────────────────────────
col_a, col_b = st.columns([2, 1])

with col_a:
    daily = df.groupby(["Day", "Status"]).size().reset_index(name="Count")
    fig_line = px.bar(
        daily, x="Day", y="Count", color="Status",
        color_discrete_map=STATUS_COLOR,
        title="Orders per Day",
        labels={"Day": "", "Count": "Orders"},
        height=320,
    )
    fig_line.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_line, use_container_width=True)

with col_b:
    status_counts = df["Status"].value_counts().reset_index()
    status_counts.columns = ["Status", "Count"]
    fig_pie = px.pie(
        status_counts, names="Status", values="Count",
        color="Status", color_discrete_map=STATUS_COLOR,
        title="By Status",
        height=320, hole=0.4,
    )
    fig_pie.update_layout(
        showlegend=True,
        legend=dict(orientation="v"),
        margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig_pie, use_container_width=True)

# ── Row 2: Revenue by state + Order type split ────────────────────────────────
col_c, col_d = st.columns([2, 1])

with col_c:
    state_rev = (
        df.groupby("State")["Total"]
        .sum()
        .sort_values(ascending=False)
        .head(15)
        .reset_index()
    )
    fig_state = px.bar(
        state_rev, x="Total", y="State", orientation="h",
        title="Top 15 States by Revenue (₹)",
        labels={"Total": "Revenue (₹)", "State": ""},
        height=380,
        color="Total",
        color_continuous_scale="Greens",
    )
    fig_state.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        coloraxis_showscale=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_state, use_container_width=True)

with col_d:
    type_data = df.groupby("Type").agg(
        Orders=("WC ID", "count"),
        Revenue=("Total", "sum")
    ).reset_index()
    fig_type = px.bar(
        type_data, x="Type", y="Revenue", color="Type",
        color_discrete_map={"Sample Kit": "#10B981", "Website Order": "#3B82F6"},
        title="Revenue by Order Type (₹)",
        labels={"Revenue": "₹", "Type": ""},
        height=380,
        text="Orders",
    )
    fig_type.update_traces(texttemplate="%{text} orders", textposition="outside")
    fig_type.update_layout(
        showlegend=False,
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_type, use_container_width=True)

# ── Row 3: Top cities ─────────────────────────────────────────────────────────
col_e, col_f = st.columns(2)

with col_e:
    city_orders = df.groupby("City").size().sort_values(ascending=False).head(12).reset_index()
    city_orders.columns = ["City", "Orders"]
    fig_city = px.bar(
        city_orders, x="Orders", y="City", orientation="h",
        title="Top Cities by Order Count",
        labels={"Orders": "Orders", "City": ""},
        height=340,
        color="Orders",
        color_continuous_scale="Blues",
    )
    fig_city.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        coloraxis_showscale=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_city, use_container_width=True)

with col_f:
    pay_data = df.groupby("Payment").agg(
        Orders=("WC ID", "count"),
        Revenue=("Total", "sum")
    ).sort_values("Orders", ascending=False).reset_index()
    fig_pay = px.bar(
        pay_data, x="Payment", y="Orders",
        title="Orders by Payment Method",
        labels={"Payment": "", "Orders": "Orders"},
        height=340,
        color="Orders",
        color_continuous_scale="Purples",
        text="Orders",
    )
    fig_pay.update_traces(textposition="outside")
    fig_pay.update_layout(
        showlegend=False,
        margin=dict(l=0, r=0, t=40, b=0),
        coloraxis_showscale=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_pay, use_container_width=True)

# ── Orders table ──────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### All Orders")

col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
with col_s1:
    search = st.text_input("Search customer / city / product", placeholder="Type to filter...")
with col_s2:
    state_list = ["All"] + sorted(df["State"].dropna().unique().tolist())
    state_sel = st.selectbox("Filter by state", state_list)
with col_s3:
    st.markdown("<br>", unsafe_allow_html=True)
    show_cols = st.checkbox("Show contact info", value=False)

display = df.copy()
if search:
    mask = (
        display["Customer"].str.contains(search, case=False, na=False) |
        display["City"].str.contains(search, case=False, na=False) |
        display["Products"].str.contains(search, case=False, na=False) |
        display["Order ID"].astype(str).str.contains(search, na=False)
    )
    display = display[mask]

if state_sel != "All":
    display = display[display["State"] == state_sel]

display["Date"] = display["Date"].dt.strftime("%Y-%m-%d %H:%M")
display["Total"] = display["Total"].apply(lambda x: f"₹{x:,.0f}")

base_cols = ["Order ID", "Date", "Status", "Type", "Customer",
             "City", "State", "Products", "Total", "Payment"]
if show_cols:
    base_cols = ["Order ID", "Date", "Status", "Type", "Customer",
                 "Email", "Phone", "City", "State", "Products", "Total", "Payment"]

def color_status(val):
    color = STATUS_COLOR.get(val, "#6B7280")
    return f"color: {color}; font-weight: bold"

styled = display[base_cols].style.map(color_status, subset=["Status"])
st.dataframe(styled, use_container_width=True, height=450, hide_index=True)

st.caption(f"Showing {len(display)} of {len(df)} orders")

# ── Export ────────────────────────────────────────────────────────────────────
st.markdown("---")
col_dl1, col_dl2 = st.columns([1, 5])
with col_dl1:
    csv = df.drop(columns=["Day", "WC ID", "State Code"]).to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇ Download CSV",
        data=csv,
        file_name=f"chuk_orders_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

# ── Auto-refresh (non-blocking) ───────────────────────────────────────────────
st.session_state.last_refresh = time.time()
if auto_refresh:
    refresh_interval = 180  # seconds
    elapsed = time.time() - st.session_state.get("_auto_ts", 0)
    if elapsed > refresh_interval:
        st.session_state["_auto_ts"] = time.time()
        st.cache_data.clear()
        time.sleep(0.5)
        st.rerun()
    else:
        remaining = int(refresh_interval - elapsed)
        st.caption(f"Auto-refresh in {remaining}s")
