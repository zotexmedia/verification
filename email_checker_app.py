import streamlit as st
import pandas as pd
import time
from email_validator import validate_email, EmailNotValidError
import dns.resolver
import smtplib
import socket
import random
import string

# ────────── helpers ──────────
checked_domains = {}                                   # cache for unique domain results
DISPOSABLE_DOMAINS = {'mailinator.com', '10minutemail.com',
                      'tempmail.com', 'yopmail.com'}
TYPO_DOMAINS = {'gamil.com', 'yaho.com', 'hotnail.com'}


def is_catch_all(domain):
    if domain in checked_domains:
        return checked_domains[domain]
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        if not mx_records:
            checked_domains[domain] = False
            return False
        mail_server = str(mx_records[0].exchange).strip('.')
        server = smtplib.SMTP(timeout=10)
        server.connect(mail_server)
        server.helo("test.local")
        server.mail("test@" + domain)
        fake_user = ''.join(random.choices(string.ascii_lowercase + string.digits, k=24))
        code, _ = server.rcpt(f"{fake_user}@{domain}")
        server.quit()
        return 'maybe' if code == 250 else False
    except Exception:
        return False


def status_icon(status):
    return {
        "Okay to Send": "🟢 " + status,
        "Do Not Send":  "🔴 " + status,
        "Maybe Send":   "🟠 " + status,
        "Checking...":  "🕐 " + status,
    }.get(status, status)


def has_mx_record(domain):
    try:
        dns.resolver.resolve(domain, 'MX')
        return True
    except Exception:
        return False


def check_email(email):
    """Return dict with email, validation_status, validation_analysis."""
    email = email.strip().replace(';', '')
    result = {"email": email, "validation_status": "", "validation_analysis": ""}

    try:
        valid = validate_email(email, check_deliverability=False)
        domain = valid["domain"].lower()
    except EmailNotValidError:
        result.update(validation_status="Do Not Send", validation_analysis="Invalid Syntax")
        return result

    if not has_mx_record(domain):
        result.update(validation_status="Do Not Send", validation_analysis="No MX")
    elif domain in DISPOSABLE_DOMAINS:
        result.update(validation_status="Do Not Send", validation_analysis="Disposable")
    elif is_catch_all(domain) == "maybe" or is_catch_all(domain):
        result.update(validation_status="Do Not Send", validation_analysis="Catch-All")
    else:
        result.update(validation_status="Okay to Send", validation_analysis="Accepted")
    return result
# ────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Local Email Checker", layout="centered")

with st.sidebar:
    st.title("📬 Email Validator")
    menu = st.radio("Navigation", ["Main", "How it works"])

# ─────────────────── MAIN PAGE ────────────────────────────────
if menu == "Main":
    st.title("📧 Local Email Health Checker")

    input_method = st.radio("Choose input method:", ["Upload CSV", "Paste Emails"])
    emails = []
    original_df = None

    # --------- INPUT ------------
    if input_method == "Upload CSV":
        uploaded_file = st.file_uploader(
            "Upload a CSV file containing an 'email' column", type="csv"
        )
        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            if "email" not in df.columns:
                st.error("CSV must have a column named 'email'.")
                st.stop()
            original_df = df.copy()                       # keep ALL columns intact
            emails = (
                df["email"]
                  .astype(str)
                  .str.replace(";", "", regex=False)
                  .str.strip()
                  .tolist()
            )
    else:  # Paste Emails
        pasted = st.text_area("Paste e-mails (one per line)")
        if pasted.strip():
            emails = [line.strip() for line in pasted.splitlines() if line.strip()]
            original_df = pd.DataFrame({"email": emails})  # minimal DF so we can add cols later

    # --------- VALIDATION BUTTON ------------
    if emails and st.button("Check Emails"):
        checked_results = []
        progress_bar = st.progress(0)
        status_placeholder = st.empty()

        for idx, email in enumerate(emails):
            progress_bar.progress(int((idx + 1) / len(emails) * 100))

            # show live table with “Checking…” row
            live_df = pd.DataFrame(
                checked_results
                + [{"email": email,
                    "validation_status": "Checking...",
                    "validation_analysis": ""}]
            )
            live_df["validation_status"] = live_df["validation_status"].apply(status_icon)
            status_placeholder.dataframe(live_df)

            checked_results.append(check_email(email))
            time.sleep(1)  # simulate network latency / DNS delay

        st.success("✅ Done!")

        results_df = pd.DataFrame(checked_results).set_index("email")

        # --------- ADD COLUMNS WITHOUT DROPPING ANYTHING ----------
        final_df = original_df.copy()
        final_df["validation_status"]   = final_df["email"].map(results_df["validation_status"])
        final_df["validation_analysis"] = final_df["email"].map(results_df["validation_analysis"])
        final_df["validation_status"]   = final_df["validation_status"].apply(status_icon)

        st.dataframe(final_df)

        csv = final_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download Results CSV",
            data=csv,
            file_name="checked_emails.csv",
            mime="text/csv",
        )

# ─────────────────── HOW-IT-WORKS PAGE ───────────────────────
elif menu == "How it works":
    st.subheader("📘 How This App Works")
    st.markdown("### ✅ Features")
    st.markdown("""
    – No signup or installation needed  
    – Fast and local e-mail validation  
    – Syntax, MX-record, disposable-domain, and catch-all checks  
    – Status legend: 🟢 Okay to Send · 🔴 Do Not Send · 🟠 Catch-All
    """)
    st.markdown("### 📄 CSV Format")
    st.markdown("""
    Your file **must** include a column named `email`.

    **Example**

    ```csv
    email
    john@example.com
    test@domain.com
    ```
    """)
    st.markdown("### 🔐 Privacy")
    st.info("Nothing is uploaded or stored; everything runs locally in your browser.")
    st.markdown("### ☕ Support")
    st.markdown("[Buy me a coffee](https://buymeacoffee.com/nimaa)")
