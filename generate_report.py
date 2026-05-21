from fpdf import FPDF
import csv
import datetime

class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(30, 30, 30)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, "CHUK.IN - GA4 Traffic Analysis & Action Plan", fill=True, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Generated {datetime.date.today()} | chuk.in", align="C")

    def section(self, title):
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(240, 240, 240)
        self.set_text_color(20, 20, 20)
        self.ln(4)
        self.cell(0, 8, title, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def sub(self, title):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(50, 50, 150)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def body(self, text):
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def bullet(self, items):
        self.set_font("Helvetica", "", 9)
        for item in items:
            self.set_x(self.l_margin + 4)
            self.multi_cell(self.epw - 4, 5, f"- {item}")
        self.ln(1)

    def table(self, headers, rows, col_widths=None):
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(60, 60, 60)
        self.set_text_color(255, 255, 255)
        if not col_widths:
            w = int(190 / len(headers))
            col_widths = [w] * len(headers)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 6, h, fill=True, border=1)
        self.ln()
        self.set_font("Helvetica", "", 8)
        self.set_text_color(0, 0, 0)
        for ri, row in enumerate(rows):
            self.set_fill_color(248, 248, 248) if ri % 2 == 0 else self.set_fill_color(255, 255, 255)
            for i, cell in enumerate(row):
                self.cell(col_widths[i], 5, str(cell)[:40], fill=True, border=1)
            self.ln()
        self.ln(3)

pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=15)
pdf.add_page()

# ── SECTION 1: OVERVIEW ──────────────────────────────────────────────
pdf.section("1. TRAFFIC OVERVIEW - Last 30 Days")
pdf.table(
    ["Metric", "Value"],
    [["Sessions","7,345"],["Active Users","5,088"],["New Users","4,808 (94.5%)"],
     ["Page Views","13,683"],["Bounce Rate","51.4%"],["Avg Session Duration","2m 57s"]],
    [80, 110]
)

# ── SECTION 2: CHANNEL BREAKDOWN ─────────────────────────────────────
pdf.section("2. CHANNEL BREAKDOWN")
pdf.table(
    ["Channel","Sessions","Share","Bounce"],
    [["Organic Search","4,410","58.8%","48%"],
     ["Direct","2,378","31.7%","60%"],
     ["Referral","395","5.3%","49%"],
     ["Unassigned","169","2.3%","89%"],
     ["Organic Social","92","1.2%","45%"],
     ["Paid Search","48","0.6%","37%"],
     ["AI Sources (ChatGPT/Gemini/Claude)","183","2.4%","~55%"]],
    [65, 35, 30, 60]
)
pdf.body("KEY ISSUE: Google Organic (56%) + Direct (32%) = 88% of all traffic. One Google algorithm change = significant traffic loss.")

# ── SECTION 3: SOURCE DIVERSITY ANALYSIS ─────────────────────────────
pdf.section("3. SOURCE DIVERSITY - Current vs Target")
pdf.table(
    ["Channel","Current","Target","Gap"],
    [["Organic Search","56%","40-45%","Over-reliant"],
     ["Direct","32%","15-20%","Reduce dependency"],
     ["Email / WhatsApp","0%","10-15%","MISSING - biggest gap"],
     ["Organic Social","1.2%","10-15%","Under-invested"],
     ["Referral","5.3%","8-10%","Close"],
     ["Paid Search","0.6%","5-8%","Under-invested"],
     ["AI Search","2.4%","3-5%","Growing naturally"],
     ["YouTube","0%","3-5%","MISSING"]],
    [50, 28, 28, 84]
)

# ── SECTION 4: SOCIAL MEDIA BREAKDOWN ────────────────────────────────
pdf.section("4. SOCIAL MEDIA BREAKDOWN (92 sessions)")
pdf.table(
    ["Platform","Sessions","Bounce","Avg Duration","Quality"],
    [["Instagram (all)","42","45%","~100s","Medium"],
     ["Facebook (all)","40","55%","~15s","Low"],
     ["LinkedIn (all)","8","42%","285s","HIGH"],
     ["WhatsApp (tagged)","1","0%","111s","High"],
     ["WhatsApp (hidden via l.wl.co)","92","67%","-","Untracked"]],
    [45, 25, 20, 35, 65]
)
pdf.body("NOTE: l.wl.co/referral = 92 sessions are WhatsApp Web shares with no UTM tags. Real WhatsApp traffic = ~184 sessions, not 1.")

# ── SECTION 5: ORGANIC SEARCH BREAKDOWN ──────────────────────────────
pdf.section("5. ORGANIC SEARCH BREAKDOWN (4,432 sessions)")
pdf.sub("By Search Engine")
pdf.table(
    ["Engine","Sessions","Share","Bounce"],
    [["Google","4,186","94.4%","49%"],
     ["Bing","157","3.5%","43%"],
     ["Yahoo","55","1.2%","37%"],
     ["ChatGPT (organic)","26","0.6%","38%"],
     ["DuckDuckGo","2","0.04%","0%"]],
    [60, 35, 30, 65]
)
pdf.sub("Top Landing Pages from Organic")
pdf.table(
    ["Page","Sessions","Bounce","Avg Duration"],
    [["/ (homepage)","1,709","26%","299s"],
     ["(not set) - BROKEN","325","97%","5s"],
     ["/krishna-janmashtami-2025 blog","302","78%","72s"],
     ["/what-is-bistro-by-blinkit blog","284","66%","99s"],
     ["/products","159","51%","200s"],
     ["/distributors-2","104","45%","164s"],
     ["Blog posts (zomato/swiggy/fssai)","~400","60-78%","80-190s"]],
    [80, 28, 25, 57]
)
pdf.sub("By City (Organic)")
pdf.table(
    ["City","Sessions"],
    [["Delhi","337"],["Bengaluru","333"],["Mumbai","313"],
     ["Ahmedabad","228"],["Pune","183"],["Hyderabad","139"],
     ["Chennai","133"],["Noida","121"],["Kolkata","84"]],
    [95, 95]
)

# ── SECTION 6: TRACKING FIXES ────────────────────────────────────────
pdf.section("6. TRACKING FIXES (Do First)")
pdf.sub("Fix 1 - Instagram Bio Link (Today)")
pdf.body("Replace bio link with:\nhttps://chuk.in/?utm_source=instagram&utm_medium=social&utm_campaign=bio\n\nFor stories, use:\nhttps://chuk.in/products/?utm_source=instagram&utm_medium=social&utm_campaign=story&utm_content=YYYYMMDD")

pdf.sub("Fix 2 - WhatsApp Broadcast Links (Today)")
pdf.table(
    ["Use Case","UTM Link"],
    [["Homepage broadcast","chuk.in/?utm_source=whatsapp&utm_medium=broadcast&utm_campaign=general"],
     ["Product promo","chuk.in/products/?utm_source=whatsapp&utm_medium=broadcast&utm_campaign=promo"],
     ["Distributor outreach","chuk.in/distributors-2/?utm_source=whatsapp&utm_medium=broadcast&utm_campaign=b2b"]],
    [40, 150]
)

pdf.sub("Fix 3 - (not set) 101 Sessions at 100% Bounce")
pdf.bullet([
    "Go to GA4 Admin > Data Streams > chuk.in > Configure tag settings",
    "Add 'List unwanted referrals' > add chuk.in",
    "Check if AMP pages or server-side redirects strip query parameters"
])

pdf.sub("Fix 4 - Facebook Random Product Links")
pdf.body("27 sessions across 20 product pages = someone copy-pasting raw links. Always use UTM-tagged links when sharing products on Facebook:\nhttps://chuk.in/products/?utm_source=facebook&utm_medium=social&utm_campaign=product-post")

# ── SECTION 7: ACTION PLAN ───────────────────────────────────────────
pdf.section("7. GROWTH ACTION PLAN (Prioritized)")
pdf.sub("Priority 1 - WhatsApp (Biggest Gap, Easiest Win)")
pdf.bullet([
    "Every order confirmation: WhatsApp message with tagged link to related products",
    "Weekly broadcast: 1 product highlight + tagged UTM link",
    "Use 3 permanent short links (bit.ly) from the UTM sheet",
    "Expected: 500+ sessions/month from WhatsApp within 60 days"
])

pdf.sub("Priority 2 - Blog Internal Links (Free, Immediate)")
pdf.bullet([
    "Top blogs getting 900+ organic sessions but 70% bounce",
    "Add 1 product CTA inside each blog post",
    "Example: 'Serving food at an event? See our disposable plates'",
    "Target blog posts: krishna-janmashtami, bistro-blinkit, zomato/swiggy rank posts",
    "Expected: 90-130 extra product page visits/month, zero new traffic needed"
])

pdf.sub("Priority 3 - LinkedIn (Best Quality Traffic)")
pdf.bullet([
    "Only 8 sessions but 285s avg duration, 0% bounce = highest quality",
    "Post 2x/week: distributor stories, sustainability, food industry stats",
    "Always end posts with tagged link to /distributors-2/",
    "Target audience: restaurants, cloud kitchens, catering businesses",
    "Expected: 200-300 sessions/month within 90 days"
])

pdf.sub("Priority 4 - Instagram (Fix Quality Before Volume)")
pdf.bullet([
    "Fix bio link first (Fix 1 above) - do today",
    "Add link sticker to every reel/story with dated UTM",
    "Track which content type converts before boosting spend",
    "Do NOT run paid Instagram until UTMs are in place"
])

# ── SECTION 8: NEW SOURCE MAPPING ────────────────────────────────────
pdf.section("8. NEW SOURCE MAPPING - Reddit, Twitter/X, Wikipedia & More")
pdf.body("UTM parameters to use when posting or getting linked from these platforms:")

new_sources = [
    # Reddit
    ("Reddit | Post comment link", "reddit", "social", "post", "comment-link"),
    ("Reddit | r/india food thread", "reddit", "social", "community", "food-thread"),
    ("Reddit | r/entrepreneur post", "reddit", "social", "community", "entrepreneur"),
    ("Reddit | r/zomato discussion", "reddit", "social", "community", "zomato-thread"),
    ("Reddit | r/IndianFood post", "reddit", "social", "community", "indian-food"),
    # Twitter / X
    ("Twitter/X | Organic tweet", "twitter", "social", "tweet", "organic"),
    ("Twitter/X | Thread post", "twitter", "social", "thread", "product-thread"),
    ("Twitter/X | Reply with link", "twitter", "social", "reply", "mention"),
    ("Twitter/X | Bio link", "twitter", "social", "bio", "bio-link"),
    # Pinterest
    ("Pinterest | Product pin", "pinterest", "social", "pin", "product"),
    ("Pinterest | Blog pin", "pinterest", "social", "pin", "blog"),
    # Quora
    ("Quora | Answer link", "quora", "referral", "answer", "question-link"),
    ("Quora | Space post", "quora", "referral", "space", "food-space"),
    # YouTube
    ("YouTube | Video description", "youtube", "video", "product-demo", "description"),
    ("YouTube | Community post", "youtube", "social", "community", "community-post"),
    ("YouTube | Shorts description", "youtube", "video", "shorts", "description"),
    # Wikipedia (outreach for citation)
    ("Wikipedia | Citation link (outreach)", "wikipedia", "referral", "citation", "eco-packaging"),
    # Indiamart / B2B
    ("IndiaMART | Profile link", "indiamart", "referral", "b2b-profile", "homepage"),
    ("IndiaMart | Product listing", "indiamart", "referral", "b2b-listing", "products"),
    ("TradeIndia | Profile", "tradeindia", "referral", "b2b-profile", "homepage"),
    # Food industry platforms
    ("Swiggy Partner Blog", "swiggy-partner", "referral", "partner-blog", "article"),
    ("Zomato Blog mention", "zomato-blog", "referral", "partner-blog", "article"),
    ("FSSAI website link", "fssai.gov.in", "referral", "government", "compliance"),
    # News / PR
    ("YourStory article", "yourstory.com", "referral", "pr-article", "brand-story"),
    ("Inc42 article", "inc42.com", "referral", "pr-article", "brand-story"),
    ("Economic Times mention", "economic-times", "referral", "pr-mention", "article"),
    # Newsletters
    ("Substack newsletter mention", "substack", "email", "newsletter-mention", "article"),
    ("The Ken mention", "the-ken", "referral", "pr-mention", "article"),
    # Telegram
    ("Telegram | Channel broadcast", "telegram", "social", "channel", "broadcast"),
    ("Telegram | Group share", "telegram", "social", "group", "share"),
    # ShareChat / Moj (India-specific)
    ("ShareChat | Post link", "sharechat", "social", "post", "product"),
    ("Moj | Video description", "moj", "video", "short-video", "product"),
    # Offline / Events
    ("Trade show | QR code", "trade-show", "offline", "event", "qr-scan"),
    ("Packaging QR code", "packaging", "offline", "product", "qr-scan"),
    ("Business card QR", "business-card", "offline", "networking", "qr-scan"),
]

BASE = "https://chuk.in"
table_rows = []
for label, source, medium, campaign, content in new_sources:
    url = f"{BASE}/?utm_source={source}&utm_medium={medium}&utm_campaign={campaign}&utm_content={content}"
    table_rows.append([label, source, medium, url])

pdf.table(
    ["Label", "Source", "Medium", "Full UTM URL"],
    table_rows,
    [55, 28, 22, 85]
)

# ── SECTION 9: 30-DAY CHECKLIST ──────────────────────────────────────
pdf.section("9. 30-DAY TRACKING CHECKLIST")
pdf.table(
    ["#", "Action", "When", "Impact"],
    [["1","Fix Instagram bio link","Today","Consolidates 5 fragmented sources"],
     ["2","Create 3 WhatsApp short links (bit.ly)","Today","Tracks 92 hidden sessions"],
     ["3","Add internal links to top 5 blog posts","This week","90-130 extra product visits/month"],
     ["4","Post on LinkedIn 2x/week with tagged links","Ongoing","200-300 sessions/month in 90 days"],
     ["5","Fix (not set) in GA4 unwanted referrals","This week","Eliminates 100% bounce phantom sessions"],
     ["6","Connect Google Search Console to GA4","This week","Keyword visibility restored"],
     ["7","Set up custom GA4 report (social + other)","This week","Weekly tracking dashboard"],
     ["8","Tag all Facebook shares with UTMs","Immediately","Identify which posts drive traffic"],
     ["9","Add UTMs to email signatures","This week","Track B2B email-driven visits"],
     ["10","Check GA4 weekly: new UTM sources appearing?","Weekly","Confirm tracking is working"]],
    [8, 65, 28, 89]
)

# ── SECTION 10: UTM QUICK REFERENCE ──────────────────────────────────
pdf.section("10. UTM PARAMETER QUICK REFERENCE")
pdf.table(
    ["Parameter","Purpose","Examples"],
    [["utm_source","Where traffic comes from","instagram, whatsapp, linkedin, reddit"],
     ["utm_medium","How it arrives","social, email, video, broadcast, offline"],
     ["utm_campaign","Which campaign","bio, promo, b2b-outreach, newsletter-may"],
     ["utm_content","Which specific piece","bio-link, story-20260521, post-plates"]],
    [35, 55, 100]
)
pdf.bullet([
    "ALWAYS use lowercase - GA4 is case-sensitive (Instagram != instagram)",
    "NEVER add UTMs to internal links - breaks session attribution",
    "Use bit.ly or uqr.to to shorten tagged URLs for WhatsApp/Instagram",
    "Change utm_content per post/date to identify best-performing content"
])

# Save
out = r"C:\Users\Asmita\documents\asmita\apps\chuk\CHUK_GA4_Report.pdf"
pdf.output(out)
print(f"PDF saved: {out}")
