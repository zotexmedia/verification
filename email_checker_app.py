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


def is_catch_all(domain):
    """Return 'maybe' if server replies 250 to a random address, else False."""
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
        result = 'maybe' if code == 250 else False
    except Exception:
        result = False
    checked_domains[domain] = result
    return result


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


def validate_one_email(email: str) -> tuple[str, str]:
    """
    Returns (status, analysis) for a single address.
    Status is one of: Okay to Send, Do Not Send.
    Analysis explains the reason.
    """
    email = email.strip().replace(';', '')
    try:
        valid = validate_email(email, check_deliverability=False)
        domain = valid["domain"].lower()
    except EmailNotValidError:
        return "Do Not Send", "Invalid Syntax"

    if not has_mx_record(domain):
        return "Do Not Send", "No MX"
    elif domain in DISPOSABLE_DOMAINS:
        return "Do Not Send", "Disposable"
    elif is_catch_all(domain) == "maybe" or is_catch_all(domain):
        return "Do Not Send", "Catch-All"
    else:
        return "Okay to Send", "Accepted"
# ────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Local Email Checker", layout="centered")

with st.sidebar:
    st.title("📬 Email Validator")
    menu = st.radio("Navigation", ["Main", "How it works"])

# ─────────────────── MAIN PAGE ────────────────────────────────
if menu == "Main":
    st.title("📧 Local Email Health Checker")

    input_method = st.radio("Choose input method:", ["Upload CSV", "Paste Emails"])
    emails: list[str] = []
    df: pd.DataFrame | None = None            # will hold the full, original data

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
            # quick preview
            st.caption("Preview of uploaded data (first 5 rows):")
            st.dataframe(df.head())

            emails = (
                df["email"]
                .astype(str)
                .str.replace(";", "", regex=False)
                .str.strip()
                .tolist()
            )
    else:  # Paste Emails
        pasted = st.text_area("Paste e-mail addresses (one per line)")
        if pasted.strip():
            emails = [line.strip() for line in pasted.splitlines() if line.strip()]
            df = pd.DataFrame({"email": emails})
            st.caption("You pasted these addresses:")
            st.dataframe(df)

    # --------- VALIDATION BUTTON ------------
    if emails and st.button("Check Emails"):
        progress_bar = st.progress(0)
        status_placeholder = st.empty()

        status_map: dict[str, str]   = {}
        analysis_map: dict[str, str] = {}

        # Validate UNIQUE addresses only:
        unique_emails = list(dict.fromkeys(emails))     # preserves order
        for idx, email in enumerate(unique_emails):
            progress_bar.progress(int((idx + 1) / len(unique_emails) * 100))

            status_placeholder.info(f"Checking {email} …")
            status, analysis = validate_one_email(email)

            status_map[email]   = status
            analysis_map[email] = analysis
            time.sleep(0.1)     # tiny pause so UI feels responsive

        st.success("✅ Validation complete!")

        # --------- ADD COLUMNS WITHOUT DROPPING ANYTHING ----------
        final_df = df.copy()
        final_df["validation_status"]   = final_df["email"].map(status_map)
        final_df["validation_analysis"] = final_df["email"].map(analysis_map)
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
    – Fast, local e-mail validation  
    – Checks: syntax · MX record · disposable-domain · catch-all  
    – Status legend: 🟢 Okay to Send · 🔴 Do Not Send · 🟠 Catch-All
    """)
    st.markdown("### 📄 CSV Format")
    st.markdown("""
    Your file **must** include a column named `email`.

    **Example**

    ```csv
    email,first_name,last_name
    john@example.com,John,Doe
    jane@domain.com,Jane,Smith
    ```
    """)
    st.markdown("### 🔐 Privacy")
    st.info("Everything runs locally in your browser; nothing is uploaded.")
    st.markdown("### ☕ Support")
    st.markdown("[Buy me a coffee](https://buymeacoffee.com/nimaa)")
