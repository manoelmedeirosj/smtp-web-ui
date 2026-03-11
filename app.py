import os, shutil, tempfile
from pathlib import Path
from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
from typing import List

from mailer import build_message, send_email, send_email_with_fallback

app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET_KEY", "dev-secret-key")  # troque em produção

# Limite básico de upload (por requisição) ~25MB
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

def parse_addresses(s: str) -> List[str]:
    if not s:
        return []
    for sep in [",", ";", "\n", "\r", "\t", " "]:
        s = s.replace(sep, ",")
    return [a.strip() for a in s.split(",") if a.strip()]

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    if request.method == "POST":
        smtp_host   = request.form.get("smtp_host", "smtplw.com.br").strip()
        smtp_port   = int(request.form.get("smtp_port", "465").strip())
        security    = request.form.get("security", "ssl")        # "ssl" | "starttls"
        use_ssl     = (security == "ssl")
        use_starttls= (security == "starttls")
        fallback    = (request.form.get("fallback", "off") == "on")

        # Se existir variável de ambiente, ela tem prioridade (boa prática no Render)
        username    = os.getenv("SMTP_USERNAME") or request.form.get("username", "").strip()
        password    = os.getenv("SMTP_PASSWORD") or request.form.get("password", "").strip()

        sender      = request.form.get("sender", "").strip()
        to          = parse_addresses(request.form.get("to", ""))
        cc          = parse_addresses(request.form.get("cc", ""))
        bcc         = parse_addresses(request.form.get("bcc", ""))
        reply_to    = request.form.get("reply_to", "").strip()
        subject     = request.form.get("subject", "").strip()
        text_body   = request.form.get("text_body", "")
        html_body   = request.form.get("html_body", "")
        debug_level = 1 if request.form.get("debug", "on") == "on" else 0

        tmpdir = Path(tempfile.mkdtemp(prefix="smtp_ui_"))
        attachments = []
        try:
            for f in request.files.getlist("attachments"):
                if not f or f.filename == "":
                    continue
                dest = tmpdir / secure_filename(f.filename)
                f.save(dest)
                attachments.append(str(dest))

            msg = build_message(
                sender=sender,
                recipients=to,
                subject=subject,
                text_body=text_body or None,
                html_body=html_body or None,
                cc=cc or None,
                bcc=bcc or None,
                reply_to=(reply_to or None),
                attachments=attachments or None,
            )

            if fallback:
                ok, msg_text, logs = send_email_with_fallback(
                    smtp_host=smtp_host,
                    username=username,
                    password=password,
                    message=msg,
                    timeout=30.0,
                    debug_level=debug_level,
                )
            else:
                ok, msg_text, logs = send_email(
                    smtp_host=smtp_host,
                    smtp_port=smtp_port,
                    username=username,
                    password=password,
                    use_ssl=use_ssl,
                    use_starttls=use_starttls,
                    message=msg,
                    timeout=30.0,
                    debug_level=debug_level,
                )

            result = {"ok": ok, "message": msg_text, "logs": logs}
        finally:
            try: shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception: pass

    return render_template("index.html", result=result)

if __name__ == "__main__":
    # Para testes locais:
    app.run(host="0.0.0.0", port=5000, debug=True)