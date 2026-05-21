import csv

BASE = "https://chuk.in"

links = [
    # label, page, source, medium, campaign, content
    # WHATSAPP
    ("WhatsApp | Homepage", "/", "whatsapp", "chat", "broadcast", "homepage"),
    ("WhatsApp | Products", "/products/", "whatsapp", "chat", "broadcast", "products"),
    ("WhatsApp | Buy Sample Box", "/buy-sample-boxes/", "whatsapp", "chat", "broadcast", "sample-box"),
    ("WhatsApp | Disposable Plates", "/products/disposable-plates/", "whatsapp", "chat", "product-share", "plates"),
    ("WhatsApp | Meal Plates", "/products/disposable-meal-plates/", "whatsapp", "chat", "product-share", "meal-plates"),
    ("WhatsApp | Bowls", "/products/disposable-bowls/", "whatsapp", "chat", "product-share", "bowls"),
    ("WhatsApp | Delivery Containers", "/products/delivery-containers/", "whatsapp", "chat", "product-share", "delivery-containers"),
    ("WhatsApp | Distributors", "/distributors-2/", "whatsapp", "chat", "b2b-outreach", "distributors"),

    # INSTAGRAM
    ("Instagram | Bio Link → Homepage", "/", "instagram", "social", "bio", "bio-link"),
    ("Instagram | Bio Link → Products", "/products/", "instagram", "social", "bio", "products"),
    ("Instagram | Bio Link → Sample Box", "/buy-sample-boxes/", "instagram", "social", "bio", "sample-box"),
    ("Instagram | Story → Products", "/products/", "instagram", "social", "story", "products"),
    ("Instagram | Story → Meal Plates", "/products/disposable-meal-plates/", "instagram", "social", "story", "meal-plates"),
    ("Instagram | Reel → Homepage", "/", "instagram", "social", "reel", "homepage"),
    ("Instagram | Post → Distributors", "/distributors-2/", "instagram", "social", "post", "distributors"),

    # FACEBOOK
    ("Facebook | Post → Homepage", "/", "facebook", "social", "post", "homepage"),
    ("Facebook | Post → Products", "/products/", "facebook", "social", "post", "products"),
    ("Facebook | Post → Sample Box", "/buy-sample-boxes/", "facebook", "social", "post", "sample-box"),
    ("Facebook | Ad → Homepage", "/", "facebook", "paid-social", "awareness", "homepage"),
    ("Facebook | Ad → Sample Box", "/buy-sample-boxes/", "facebook", "paid-social", "conversion", "sample-box"),

    # LINKEDIN
    ("LinkedIn | Bio → Homepage", "/", "linkedin", "social", "bio", "homepage"),
    ("LinkedIn | Post → Distributors", "/distributors-2/", "linkedin", "social", "post", "distributors"),
    ("LinkedIn | Post → Products", "/products/", "linkedin", "social", "post", "products"),
    ("LinkedIn | Post → About", "/about-us/", "linkedin", "social", "post", "about"),
    ("LinkedIn | B2B Outreach → Distributors", "/distributors-2/", "linkedin", "social", "b2b-outreach", "distributors"),

    # EMAIL
    ("Email | Newsletter → Homepage", "/", "newsletter", "email", "monthly-newsletter", "homepage"),
    ("Email | Newsletter → Products", "/products/", "newsletter", "email", "monthly-newsletter", "products"),
    ("Email | Newsletter → Sample Box", "/buy-sample-boxes/", "newsletter", "email", "monthly-newsletter", "sample-box"),
    ("Email | Promo → Meal Plates", "/products/disposable-meal-plates/", "newsletter", "email", "promo", "meal-plates"),
    ("Email | Promo → Bowls", "/products/disposable-bowls/", "newsletter", "email", "promo", "bowls"),
    ("Email | Transactional → Homepage", "/", "zoho-crm", "email", "transactional", "homepage"),
    ("Email | B2B Outreach → Distributors", "/distributors-2/", "zoho-crm", "email", "b2b-outreach", "distributors"),

    # YOUTUBE
    ("YouTube | Description → Homepage", "/", "youtube", "video", "product-demo", "homepage"),
    ("YouTube | Description → Products", "/products/", "youtube", "video", "product-demo", "products"),
    ("YouTube | Description → Sample Box", "/buy-sample-boxes/", "youtube", "video", "product-demo", "sample-box"),
    ("YouTube | Description → Distributors", "/distributors-2/", "youtube", "video", "b2b", "distributors"),

    # GOOGLE ADS (manual tagging fallback)
    ("Google Ads | Search → Homepage", "/", "google", "cpc", "brand-search", "homepage"),
    ("Google Ads | Search → Products", "/products/", "google", "cpc", "product-search", "products"),
    ("Google Ads | Search → Sample Box", "/buy-sample-boxes/", "google", "cpc", "conversion", "sample-box"),
    ("Google Ads | Shopping → Plates", "/products/disposable-plates/", "google", "cpc", "shopping", "plates"),

    # QR CODES (offline)
    ("QR Code | Packaging → Homepage", "/", "qr-code", "offline", "packaging", "homepage"),
    ("QR Code | Packaging → Products", "/products/", "qr-code", "offline", "packaging", "products"),
    ("QR Code | Event → Sample Box", "/buy-sample-boxes/", "qr-code", "offline", "event", "sample-box"),
    ("QR Code | Distributor Kit → Distributors", "/distributors-2/", "qr-code", "offline", "distributor-kit", "distributors"),
]

def build_url(page, source, medium, campaign, content):
    return f"{BASE}{page}?utm_source={source}&utm_medium={medium}&utm_campaign={campaign}&utm_content={content}"

rows = []
for label, page, source, medium, campaign, content in links:
    url = build_url(page, source, medium, campaign, content)
    rows.append([label, url, source, medium, campaign, content])

with open("chuk_utm_links.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Label", "Full UTM URL", "Source", "Medium", "Campaign", "Content"])
    writer.writerows(rows)

print(f"Generated {len(rows)} UTM links -> chuk_utm_links.csv")
print()
for row in rows:
    print(f"{row[0]}")
    print(f"  {row[1]}")
    print()
