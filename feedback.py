#!/usr/bin/env python3
# SBM
# Save MIsoTEx feedback, create a PDF, and email the notification.
# Credentials are stored outside the web root in /etc/misotex-feedback/config.py.

import sys, os, re, html, ssl, smtplib, textwrap, traceback
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import parse_qs

sys.path.insert(0, "/etc/misotex-feedback")
try:
    import config
    import mysql.connector
except Exception:
    print("Status: 500 Internal Server Error\nContent-Type: text/plain; charset=utf-8\n")
    print("Feedback service is not configured. Contact the website administrator.")
    raise SystemExit

def response(status, title, message):
    print("Status: " + status)
    print("Content-Type: text/html; charset=utf-8")
    print("X-Content-Type-Options: nosniff")
    print("Cache-Control: no-store\n")
    print("""<!doctype html><html><head><meta charset="utf-8"><title>{}</title>
    <style>body{{font-family:Arial;max-width:680px;margin:48px auto;padding:0 18px;color:#202b36}}</style>
    </head><body><h1>{}</h1><p>{}</p><p><a href="/Mammalian_tissue_catalogoue/feedback/feedback.html">Return to feedback form</a></p></body></html>""".format(html.escape(title), html.escape(title), message))

def get_form():
    try:
        length = int(os.environ.get("CONTENT_LENGTH", "0"))
    except ValueError:
        raise ValueError("Invalid request size.")
    if length < 0 or length > 20000:
        raise ValueError("The submission is too large.")
    raw = sys.stdin.buffer.read(length).decode("utf-8", errors="replace")
    values = parse_qs(raw, keep_blank_values=True, max_num_fields=30)
    return {k: (v[0].strip() if v else "") for k, v in values.items()}

def clean(value, limit):
    value = value.replace("\x00", "").strip()
    if len(value) > limit:
        raise ValueError("One of the fields is too long.")
    return value

def pdf_escape(value):
    value = str(value).encode("latin-1", "replace").decode("latin-1")
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

def make_pdf(fields):
    lines = ["MIsoTEx Feedback Submission", "", "Submitted: " + fields["Submitted at"]]
    for key in ["Feedback ID", "Name", "Designation / Role", "Rating", "Country", "Institution / University", "Email"]:
        lines.append(key + ": " + (fields.get(key) or "Not provided"))
    lines.extend(["", "Feedback:"])
    for para in (fields.get("Feedback") or "").splitlines() or [""]:
        lines.extend(textwrap.wrap(para, width=88, break_long_words=True) or [""])
    pages = [lines[i:i+52] for i in range(0, len(lines), 52)] or [[]]
    objects = [None, None, None]
    page_ids = []
    for page_lines in pages:
        page_id, content_id = len(objects)+1, len(objects)+2
        page_ids.append(page_id)
        content = ["BT", "/F1 9 Tf", "50 790 Td", "13 TL"]
        for i, line in enumerate(page_lines):
            if i: content.append("T*")
            content.append("(" + pdf_escape(line) + ") Tj")
        content.append("ET")
        stream = "\n".join(content).encode("latin-1", "replace")
        page = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>").encode("latin-1")
        stream_obj = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        objects.extend([page, stream_obj])
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(str(i)+' 0 R' for i in page_ids)}] /Count {len(page_ids)} >>".encode()
    objects[2] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    pdf, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), [0]
    for n, obj in enumerate(objects, 1):
        offsets.append(len(pdf)); pdf.extend(f"{n} 0 obj\n".encode()); pdf.extend(obj); pdf.extend(b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects)+1}\n".encode()); pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]: pdf.extend(f"{off:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(pdf)

def send_notification(fields, pdf_bytes):
    for name in ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "NOTIFY_EMAIL"]:
        if not getattr(config, name, None):
            raise RuntimeError("Missing email setting: " + name)
    msg = EmailMessage()
    msg["Subject"] = f"[MIsoTEx Feedback] New submission #{fields['Feedback ID']}"
    msg["From"], msg["To"] = config.SMTP_USER, config.NOTIFY_EMAIL
    msg.set_content("A new MIsoTEx feedback submission has been saved.\n\n"
                    f"Feedback ID: {fields['Feedback ID']}\nSubmitted: {fields['Submitted at']}\n\n"
                    "The full submission is attached as a PDF.")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf",
                       filename=f"MIsoTEx_feedback_{fields['Feedback ID']}.pdf")
    with smtplib.SMTP(config.SMTP_HOST, int(config.SMTP_PORT), timeout=30) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)

if os.environ.get("REQUEST_METHOD", "GET").upper() != "POST":
    response("405 Method Not Allowed", "Submit feedback", "Please use the feedback form to submit your response.")
    raise SystemExit

try:
    form = get_form()
    if form.get("website", "").strip():
        response("200 OK", "Thank you", "Thank you for your feedback.")
        raise SystemExit
    comments = clean(form.get("comments", ""), 5000)
    name = clean(form.get("researcher_name", ""), 150)
    designation = clean(form.get("designation", ""), 150)
    country = clean(form.get("country", ""), 100)
    institution = clean(form.get("institution", ""), 255)
    email = clean(form.get("contact_email", ""), 254)
    rating_text = clean(form.get("rating", ""), 2)
    if not comments: raise ValueError("Please describe your feedback before submitting.")
    if rating_text and rating_text not in {"1", "2", "3", "4", "5"}:
        raise ValueError("Please select a rating from 1 to 5.")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Please enter a valid email address or leave it blank.")
    rating = int(rating_text) if rating_text else None

    # Legacy fields remain populated compatibly with the existing database schema.
    conn = mysql.connector.connect(host=config.DB_HOST, database=config.DB_NAME,
                                  user=config.DB_USER, password=config.DB_PASSWORD,
                                  connection_timeout=5)
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO user_feedback
          (rating, ease_of_use, feedback_type, module, comments, researcher_name,
           designation, country, institution, contact_email)
          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
          (rating, None, "General comment", None, comments, name or None,
           designation or None, country or None, institution or None, email or None))
        conn.commit()
        feedback_id = cur.lastrowid
        cur.close()
    finally:
        conn.close()

    fields = {"Feedback ID": str(feedback_id),
              "Submitted at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
              "Name": name, "Designation / Role": designation, "Rating": rating_text,
              "Country": country, "Institution / University": institution,
              "Email": email, "Feedback": comments}
    try:
        send_notification(fields, make_pdf(fields))
    except Exception:
        print("MIsoTEx feedback saved, but notification email failed:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    response("200 OK", "Thank you for your feedback",
             "Your feedback has been saved successfully. Thank you for helping us improve MIsoTEx.")
except ValueError as exc:
    response("400 Bad Request", "Please check your submission", html.escape(str(exc)))
except Exception:
    print("MIsoTEx feedback submission failed:", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    response("500 Internal Server Error", "Submission could not be completed",
             "Your feedback could not be saved at this time. Please try again later or contact the website administrator.")
