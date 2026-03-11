import ssl
import smtplib
import mimetypes
import os
from email.message import EmailMessage
from typing import List, Optional, Tuple
import io
import contextlib

def build_message(
    sender: str,
    recipients: List[str],
    subject: str,
    text_body: Optional[str] = None,
    html_body: Optional[str] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
    attachments: Optional[List[str]] = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject

    if html_body:
        msg.set_content(text_body or "Visualize este e-mail em HTML.")
        msg.add_alternative(html_body, subtype="html")
    else:
        msg.set_content(text_body or "")

    if attachments:
        for path in attachments:
            if not path:
                continue
            ctype, encoding = mimetypes.guess_type(path)
            if ctype is None or encoding is not None:
                ctype = "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            with open(path, "rb") as f:
                data = f.read()
            msg.add_attachment(
                data, maintype=maintype, subtype=subtype, filename=os.path.basename(path)
            )

    if bcc:
        msg.__dict__.setdefault("_bcc", bcc)

    return msg

def _collect_recipients(msg: EmailMessage) -> List[str]:
    to_addrs: List[str] = []
    if "To" in msg:
        to_addrs += [a.strip() for a in msg["To"].split(",") if a.strip()]
    if "Cc" in msg:
        to_addrs += [a.strip() for a in msg["Cc"].split(",") if a.strip()]
    bcc = getattr(msg, "_bcc", [])
    if bcc:
        to_addrs += bcc
    return to_addrs

def _send_with(server: smtplib.SMTP, message: EmailMessage) -> None:
    to_addrs = _collect_recipients(message)
    server.send_message(message, from_addr=message["From"], to_addrs=to_addrs)

def _do_login(server: smtplib.SMTP, username: str, password: str) -> Tuple[int, bytes]:
    return server.login(username, password)

def send_email(
    smtp_host: str,
    smtp_port: int,
    username: Optional[str],
    password: Optional[str],
    use_ssl: bool,
    use_starttls: bool,
    message: EmailMessage,
    timeout: float = 30.0,
    debug_level: int = 1,
) -> Tuple[bool, str, str]:
    if use_ssl and use_starttls:
        return False, "Configuração inválida: selecione SSL ou STARTTLS, não ambos.", ""

    context = ssl.create_default_context()
    log_buf = io.StringIO()
    server: Optional[smtplib.SMTP] = None

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host=smtp_host, port=smtp_port, context=context, timeout=timeout)
        else:
            server = smtplib.SMTP(host=smtp_host, port=smtp_port, timeout=timeout)

        with contextlib.redirect_stdout(log_buf):
            server.set_debuglevel(debug_level)
            server.ehlo()
            if use_starttls:
                server.starttls(context=context)
                server.ehlo()

            if username and password:
                _do_login(server, username, password)

            _send_with(server, message)
    except Exception as e:
        try:
            if server is not None:
                server.quit()
        except Exception:
            pass
        return False, f"Falha no envio: {type(e).__name__}: {e}", log_buf.getvalue()

    try:
        server.quit()
    except Exception:
        pass

    return True, "E-mail enviado com sucesso!", log_buf.getvalue()

def send_email_with_fallback(
    smtp_host: str,
    username: Optional[str],
    password: Optional[str],
    message: EmailMessage,
    timeout: float = 30.0,
    debug_level: int = 1,
) -> Tuple[bool, str, str]:
    attempts = [
        {"port": 465, "use_ssl": True,  "use_starttls": False},
        {"port": 587, "use_ssl": False, "use_starttls": True},
    ]
    full_logs = io.StringIO()
    last_msg = ""

    for opt in attempts:
        method = "SSL" if opt["use_ssl"] else "STARTTLS"
        full_logs.write(f"[INFO] Tentando {smtp_host}:{opt['port']} ({method})\n")

        ok, msg, logs = send_email(
            smtp_host=smtp_host,
            smtp_port=opt["port"],
            username=username,
            password=password,
            use_ssl=opt["use_ssl"],
            use_starttls=opt["use_starttls"],
            message=message,
            timeout=timeout,
            debug_level=debug_level,
        )
        full_logs.write(logs)
        if ok:
            return True, msg, full_logs.getvalue()

        last_msg = msg
        full_logs.write(f"[WARN] {msg}\n")

    return False, last_msg or "Falha nas tentativas 465/587.", full_logs.getvalue()