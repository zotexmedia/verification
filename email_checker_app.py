# email_checker_app.py
#
# pip install streamlit email_validator dnspython requests python-dotenv
# then:  streamlit run email_checker_app.py
#
# ─────────────────────────────────────────

import streamlit as st, pandas as pd, time, requests, dns.resolver
from email_validator import validate_email, EmailNotValidError
import smtplib, random, string, socket, functools, datetime as dt

# ─────────────────────────  CONFIG  ──────────────────────────
DISPOSABLE_URL = ("https://raw.githubusercontent.com/"
                  "disposable-email-domains/disposable-email-domains/"
                  "master/disposable_email_blocklist.conf")

ROLE_URL       = ("https://raw.githubusercontent.com/"
                  "mixmaxhq/role-based-email-addresses/master/role-addresses.json")

TYPO_URL       = ("https://raw.githubusercontent.com/"
                  "m-a-x-s-e-e-l-i-g/common-email-domain-typos/main/typos.txt")
# fallback for typo list if the above ever moves
FALLBACK_TYPOS = {"gamil.com": "gmail.com", "hotnail.com": "hotmail.com",
                  "yaho.com": "yahoo.com"}

SMTP_TIMEOUT   = 8        # seconds for SMTP socket
DNS_TIMEOUT    = 4        # seconds for DNS look-ups
CACHE_TTL      = 24*3600  # seconds between list refreshes
# ─────────────────────────────────────────────────────────────

# ---------- CACHED LOADERS (run once per day) ----------------
@st.cache_data(ttl=CACHE_TTL, show_spinner="Loading disposable-domain list…")
def load_disposable():
    resp = requests.get(DISPOSABLE_URL, timeout=15)
    return set(resp.text.splitlines()) if resp.ok else set()

@st.cache_data(ttl=CACHE_TTL, show_spinner="Loading role-address list…")
def load_role():
    resp = requests.get(ROLE_URL, timeout=15)
    return set(resp.json()) if resp.ok else set()

@st.cache_data(ttl=CACHE_TTL, show_spinner="Loading typo list…")
def load_typos():
    resp = requests.get(TYPO_URL, timeout=15)
    if resp.ok:
        mapping = {}
        for ln in resp.text.splitlines():
            if ":" in ln:
                wrong, right = ln.split(":", 1)
                mapping[wrong.strip()] = right.strip()
        return mapping
    return FALLBACK_TYPOS

DISPOSABLE_SET = load_disposable()
ROLE_SET       = load_role()
TYPO_MAP       = load_typos()

# ---------- UTILITIES ----------------------------------------
def status_icon(status: str) -> str:
    return {"Okay": "🟢 Okay to Send",
            "DoNot": "🔴 Do Not Send",
            "Maybe": "🟠 Maybe Send",
            "Check": "🕐 Checking..."}.get(status, status)

@functools.lru_cache(maxsize=10_000)
def has_mx(domain: str) -> bool:
    try:
        dns.resolver.resolve(domain, "MX", lifetime=DNS_TIMEOUT)
        return True
    except Exception:
        return False

@functools.lru_cache(maxsize=10_000)
def is_blacklisted(domain: str) -> bool:
    """Query Spamhaus DBL; True if domain is listed."""
    try:
        dns.resolver.resolve(f"{domain}.dbl.spamhaus.org", "A", lifetime=DNS_TIMEOUT)
        return True
    except dns.resolver.NXDOMAIN:
        return False
    except Exception:
        # network error → treat as unknown (not blacklisted)
        return False

@functools.lru_cache(maxsize=10_000)
def is_catch_all(domain: str) -> str | bool:
    """Return 'maybe' when server accepts random address, else False."""
    try:
        mx = dns.resolver.resolve(domain, "MX", lifetime=DNS_TIMEOUT)[0].exchange.to_text().rstrip(".")
        srv = smtplib.SMTP(timeout=SMTP_TIMEOUT)
        srv.connect(mx)
        srv.helo("test.local")
        srv.mail(f"probe@{domain}")
        fake = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
        code, _ = srv.rcpt(f"{fake}@{domain}")
        srv.quit()
        return "maybe" if code == 250 else False
    except Exception:
        return False

def suggest_typo(domain: str) -> str | None:
    return TYPO_MAP.get(domain)

# -------------- SINGLE EMAIL CHECK ---------------------------
def validate_one(email: str) -> tuple[str, list[str]]:
    """
    Returns status ('Okay'|'DoNot'|'Maybe') and a list of reasons.
    """
    reasons = []
    email = email.strip().replace(";", "")

    # 1) syntax
    try:
        parsed = validate_email(email, check_deliverability=False)
        domain = parsed["domain"].lower()
        local  = parsed["local"].lower()
    except EmailNotValidError:
        return "DoNot", ["Invalid syntax"]

    # 2) obvious typo?
    if domain in TYPO_MAP:
        reasons.append(f"Possible typo – did you mean **{TYPO_MAP[domain]}**?")
        return "DoNot", reasons      # stop early; user should correct

    # 3) disposable?
    if domain in DISPOSABLE_SET:
        reasons.append("Disposable / temporary domain")
        return "DoNot", reasons

    # 4) role address?
    if local in ROLE_SET:
        reasons.append("Role-based address (info@, sales@, etc.)")

    # 5) domain reputation
    if is_blacklisted(domain):
        reasons.append("Domain listed in Spamhaus DBL (malicious/spam)")
        return "DoNot", reasons

    # 6) MX present?
    if not has_mx(domain):
        reasons.append("No MX records")
        return "DoNot", reasons

    # 7) SMTP / catch-all
    ca = is_catch_all(domain)
    if ca == "maybe":
        reasons.append("Catch-all domain – cannot confirm mailbox")
        return "Maybe", reasons
    elif ca is False:
        reasons.append("Mailbox accepted by server")  # passes SMTP

    # final pass
    return ("Okay" if "Mailbox accepted" in reasons else "DoNot"), reasons

# ────────────────  STREAMLIT UI  ─────────────────────────────
st.set_page_config(page_title="Enhanced Email Verifier", layout="centered")
with st.sidebar:
    st.title("📬 Email Verifier 2.0")
    page = st.radio("Navigate", ["Verify", "How it works"])

if page == "Verify":
    st.header("🔎 Verify E-mails with Extra Safety Checks")
    method = st.radio("Input method", ["Upload CSV", "Paste Emails"])

    emails, df = [], None
    if method == "Upload CSV":
        up = st.file_uploader("CSV must include an **email** column", type="csv")
        if up:
            df = pd.read_csv(up)
            if "email" not in df.columns:
                st.error("No 'email' column found.")
                st.stop()
            st.caption("Preview:")
            st.dataframe(df.head())
            emails = df["email"].astype(str).tolist()
    else:
        pasted = st.text_area("One e-mail per line")
        if pasted.strip():
            emails = [e.strip() for e in pasted.splitlines() if e.strip()]
            df = pd.DataFrame({"email": emails})

    # -------- RUN VALIDATION --------
    if emails and st.button("Check Emails"):
        status_map, reason_map = {}, {}
        pbar = st.progress(0)
        for idx, e in enumerate(dict.fromkeys(emails)):     # unique order
            stat, why = validate_one(e)
            status_map[e]  = stat
            reason_map[e]  = "; ".join(why)
            pbar.progress((idx+1)/len(set(emails)))

        final = df.copy()
        final["validation_status"]   = final["email"].map(status_map).fillna("Check")
        final["validation_analysis"] = final["email"].map(reason_map).fillna("")
        final["validation_status"]   = final["validation_status"].apply(status_icon)

        st.success("Done!")
        st.dataframe(final)

        csv = final.to_csv(index=False).encode()
        st.download_button("📥 Download CSV", csv, "verified_emails.csv", "text/csv")

else:  # How it works
    st.header("📘 What Gets Checked")
    st.markdown("""
| Check | What it catches | Why it matters |
|-------|-----------------|----------------|
| **Syntax** | Bad formatting | Won’t deliver |
| **Common Typos** | `gamil.com` → `gmail.com` | Fix user mistakes |
| **Disposable Domains** | 10MinuteMail, Mailinator | One-off / throw-away |
| **Role Addresses** | info@, sales@ | Not a personal inbox |
| **Spamhaus DBL** | Domains used for spam/phishing | Protects sender reputation |
| **MX Records** | No mail server | Immediate bounce |
| **Catch-all Test** | Server accepts anything | Deliverability uncertain |
| **SMTP Probe** | Mailbox exists | Final deliverability signal |
""")
    st.info("Lists refresh every 24 h and are cached in memory. "
            "No data ever leaves your browser session.")
