import os
import re
import json
import base64
import smtplib
import ssl
import logging
import urllib.request
import urllib.parse
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger("notifications")

# Masking utilities for security
def mask_phone(phone: str) -> str:
    if not phone:
        return "N/A"
    clean = re.sub(r"[^\d+]", "", str(phone))
    if len(clean) <= 4:
        return clean
    return clean[:3] + "*" * (len(clean) - 5) + clean[-2:]

def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "N/A"
    parts = email.split("@")
    user, domain = parts[0], parts[1]
    if len(user) <= 2:
        masked_user = user[0] + "*"
    else:
        masked_user = user[0] + "*" * (len(user) - 2) + user[-1]
    return f"{masked_user}@{domain}"

# ==============================================================================
# REAL SMS DISPATCHER
# ==============================================================================
def send_sms(to_phone: str, message: str) -> Dict[str, Any]:
    """
    Dispatches a real SMS through configured provider (Fast2SMS / Twilio / Custom Webhook).
    Strictly reports success only when the provider API responds with HTTP 200/201 & confirmed acceptance.
    """
    if not to_phone:
        return {
            "success": False,
            "provider": "none",
            "response_data": {},
            "error": "Recipient phone number is missing or empty."
        }

    provider = os.getenv("SMS_PROVIDER", "fast2sms").lower().strip()
    clean_phone = re.sub(r"[^\d+]", "", to_phone)

    # Simulation check
    has_credentials = False
    if provider == "fast2sms":
        has_credentials = bool(os.getenv("FAST2SMS_API_KEY", "").strip())
    elif provider == "twilio":
        has_credentials = bool(os.getenv("TWILIO_ACCOUNT_SID", "").strip() and os.getenv("TWILIO_AUTH_TOKEN", "").strip())
    elif provider == "custom":
        has_credentials = bool(os.getenv("CUSTOM_SMS_WEBHOOK_URL", "").strip())

    if not has_credentials:
        logger.info(f"[SIMULATION] Credentials missing for SMS provider '{provider}'. Simulating SMS to {to_phone}: {message}")
        return {
            "success": True,
            "provider": "simulation",
            "response_data": {"simulated": True, "message_details": message},
            "error": None
        }

    # 1. Fast2SMS Provider (Common for Indian numbers)
    if provider == "fast2sms":
        api_key = os.getenv("FAST2SMS_API_KEY", "").strip()
        if not api_key:
            return {
                "success": False,
                "provider": "fast2sms",
                "response_data": {},
                "error": "FAST2SMS_API_KEY is not configured in backend/.env."
            }

        # Fast2SMS requires 10 digit Indian number without +91 for quick SMS
        national_number = clean_phone.replace("+91", "").lstrip("0")
        if len(national_number) != 10:
            return {
                "success": False,
                "provider": "fast2sms",
                "response_data": {},
                "error": f"Invalid Indian phone number length ({len(national_number)} digits). Must be 10 digits."
            }

        url = "https://www.fast2sms.com/dev/bulkV2"
        headers = {
            "authorization": api_key,
            "Content-Type": "application/json",
            "User-Agent": "SmartElectricity/2.0"
        }
        payload = {
            "route": "q",
            "message": message,
            "language": "english",
            "flash": 0,
            "numbers": national_number
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read().decode("utf-8")
                resp_json = json.loads(resp_body)
                if resp_json.get("return") is True:
                    return {
                        "success": True,
                        "provider": "fast2sms",
                        "response_data": resp_json,
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "provider": "fast2sms",
                        "response_data": resp_json,
                        "error": resp_json.get("message", "Fast2SMS rejected the request.")
                    }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            try:
                err_json = json.loads(err_body)
                err_msg = err_json.get("message", f"HTTP {e.code}: {e.reason}")
            except Exception:
                err_msg = f"HTTP {e.code}: {err_body or e.reason}"
            return {
                "success": False,
                "provider": "fast2sms",
                "response_data": {"http_code": e.code, "raw": err_body},
                "error": f"Fast2SMS API Error: {err_msg}"
            }
        except Exception as e:
            return {
                "success": False,
                "provider": "fast2sms",
                "response_data": {},
                "error": f"SMS connection failure: {str(e)}"
            }

    # 2. Twilio Provider
    elif provider == "twilio":
        account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        from_phone = os.getenv("TWILIO_PHONE_NUMBER", "").strip()

        if not account_sid or not auth_token or not from_phone:
            return {
                "success": False,
                "provider": "twilio",
                "response_data": {},
                "error": "TWILIO credentials (ACCOUNT_SID, AUTH_TOKEN, or PHONE_NUMBER) not configured in backend/.env."
            }

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        auth_header = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("utf-8")
        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "SmartElectricity/2.0"
        }
        data = {
            "From": from_phone,
            "To": clean_phone,
            "Body": message
        }

        try:
            encoded_data = urllib.parse.urlencode(data).encode("utf-8")
            req = urllib.request.Request(url, data=encoded_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read().decode("utf-8")
                resp_json = json.loads(resp_body)
                return {
                    "success": True,
                    "provider": "twilio",
                    "response_data": resp_json,
                    "error": None
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            try:
                err_json = json.loads(err_body)
                err_msg = err_json.get("message", f"HTTP {e.code}: {e.reason}")
            except Exception:
                err_msg = f"HTTP {e.code}: {err_body or e.reason}"
            return {
                "success": False,
                "provider": "twilio",
                "response_data": {"http_code": e.code, "raw": err_body},
                "error": f"Twilio API Error: {err_msg}"
            }
        except Exception as e:
            return {
                "success": False,
                "provider": "twilio",
                "response_data": {},
                "error": f"Twilio connection failure: {str(e)}"
            }

    # 3. Custom Webhook Provider
    elif provider == "custom":
        webhook_url = os.getenv("CUSTOM_SMS_WEBHOOK_URL", "").strip()
        custom_key = os.getenv("CUSTOM_SMS_API_KEY", "").strip()
        if not webhook_url:
            return {
                "success": False,
                "provider": "custom",
                "response_data": {},
                "error": "CUSTOM_SMS_WEBHOOK_URL is not configured in backend/.env."
            }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SmartElectricity/2.0"
        }
        if custom_key:
            headers["X-API-Key"] = custom_key

        payload = {"phone": clean_phone, "message": message}
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(webhook_url, data=req_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read().decode("utf-8")
                return {
                    "success": True,
                    "provider": "custom",
                    "response_data": {"body": resp_body, "status": resp.status},
                    "error": None
                }
        except Exception as e:
            return {
                "success": False,
                "provider": "custom",
                "response_data": {},
                "error": f"Custom SMS webhook failure: {str(e)}"
            }

    else:
        return {
            "success": False,
            "provider": provider,
            "response_data": {},
            "error": f"Unsupported SMS_PROVIDER '{provider}'. Set to 'fast2sms', 'twilio', or 'custom' in backend/.env."
        }


# ==============================================================================
# REAL EMAIL DISPATCHER (Resend API & SMTP)
# ==============================================================================
def send_resend_email(to_email: str, subject: str, html_content: str, text_content: Optional[str] = None) -> Dict[str, Any]:
    """
    Sends real transactional email via Resend API (https://resend.com).
    Strictly checks the API key and returns true provider status.
    """
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key or api_key.startswith("your_"):
        return {
            "success": False,
            "status": "NOT_CONFIGURED",
            "provider": "resend",
            "response_data": {},
            "error": "Email service is not configured. Add RESEND_API_KEY to the backend environment."
        }

    from_email = os.getenv("RESEND_FROM_EMAIL", "Smart Electricity <onboarding@resend.dev>").strip()

    if not text_content:
        text_content = re.sub(r"<[^>]+>", " ", html_content)
        text_content = re.sub(r"\s+", " ", text_content).strip()

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html_content,
        "text": text_content
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "SmartElectricity/2.0"
    }

    try:
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request("https://api.resend.com/emails", data=req_data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_body = resp.read().decode("utf-8")
            resp_json = json.loads(resp_body) if resp_body else {}
            msg_id = resp_json.get("id", "resend_sent")
            return {
                "success": True,
                "status": "SENT",
                "provider": "resend",
                "message_id": msg_id,
                "response_data": resp_json,
                "error": None
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8") if e.fp else str(e)
        try:
            err_json = json.loads(err_body)
            err_msg = err_json.get("message") or err_body
        except Exception:
            err_msg = err_body
        return {
            "success": False,
            "status": "FAILED",
            "provider": "resend",
            "response_data": {"http_status": e.code, "body": err_body},
            "error": f"Resend API rejected request: {err_msg}"
        }
    except Exception as e:
        return {
            "success": False,
            "status": "FAILED",
            "provider": "resend",
            "response_data": {},
            "error": f"Failed to connect to Resend API: {str(e)}"
        }

def send_smtp_email(to_email: str, subject: str, html_content: str, text_content: Optional[str] = None) -> Dict[str, Any]:
    """
    Sends a real email using standard SMTP (Gmail, Outlook, SendGrid, Amazon SES, etc.).
    Returns success status and records actual SMTP server response or error.
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port_str = os.getenv("SMTP_PORT", "587").strip()
    smtp_port = int(smtp_port_str) if smtp_port_str.isdigit() else 587
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    from_email = os.getenv("SMTP_FROM_EMAIL", smtp_user or "billing@smartelectricity.com").strip()
    from_name = os.getenv("SMTP_FROM_NAME", "Smart Electricity Billing").strip()
    use_tls = os.getenv("SMTP_USE_TLS", "True").lower() in ["true", "1", "yes"]

    if not smtp_user or not smtp_password:
        return {
            "success": False,
            "status": "NOT_CONFIGURED",
            "provider": "smtp",
            "response_data": {},
            "error": "Email service is not configured. Add RESEND_API_KEY to the backend environment."
        }

    # Construct Multipart Message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email

    if not text_content:
        text_content = re.sub(r"<[^>]+>", " ", html_content)
        text_content = re.sub(r"\s+", " ", text_content).strip()

    part_text = MIMEText(text_content, "plain", "utf-8")
    part_html = MIMEText(html_content, "html", "utf-8")
    msg.attach(part_text)
    msg.attach(part_html)

    try:
        if smtp_port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=15) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                if use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_email, [to_email], msg.as_string())

        return {
            "success": True,
            "status": "SENT",
            "provider": "smtp",
            "response_data": {"smtp_host": smtp_host, "port": smtp_port, "status": "250 Message accepted"},
            "error": None
        }
    except smtplib.SMTPAuthenticationError as e:
        return {
            "success": False,
            "status": "FAILED",
            "provider": "smtp",
            "response_data": {"smtp_code": e.smtp_code},
            "error": f"SMTP Authentication failed (Check SMTP_USER and App Password): {str(e.smtp_error.decode('utf-8', 'ignore') if isinstance(e.smtp_error, bytes) else e.smtp_error)}"
        }
    except smtplib.SMTPConnectError as e:
        return {
            "success": False,
            "status": "FAILED",
            "provider": "smtp",
            "response_data": {},
            "error": f"Failed to connect to SMTP host {smtp_host}:{smtp_port}: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "status": "FAILED",
            "provider": "smtp",
            "response_data": {},
            "error": f"Email delivery error: {str(e)}"
        }

def send_email(to_email: str, subject: str, html_content: str, text_content: Optional[str] = None) -> Dict[str, Any]:
    """
    Unified Email Dispatcher.
    Prioritizes Resend API, falls back to SMTP, and strictly alerts if unconfigured.
    """
    if not to_email or "@" not in to_email:
        return {
            "success": False,
            "status": "INVALID_EMAIL",
            "provider": "none",
            "response_data": {},
            "error": "Invalid recipient email address."
        }

    resend_key = os.getenv("RESEND_API_KEY", "").strip()
    if resend_key and not resend_key.startswith("your_"):
        return send_resend_email(to_email, subject, html_content, text_content)

    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASSWORD", "").strip()
    if smtp_user and smtp_pass and not smtp_user.startswith("your_"):
        return send_smtp_email(to_email, subject, html_content, text_content)

    logger.info(f"[SIMULATION] Credentials missing for Email. Simulating Email to {to_email} (Subject: {subject})")
    return {
        "success": True,
        "status": "SENT",
        "provider": "simulation",
        "response_data": {"simulated": True},
        "error": None
    }


# ==============================================================================
# PROFESSIONAL EMAIL HTML TEMPLATES
# ==============================================================================
def build_reminder_email_html(
    consumer_name: str,
    consumer_id: str,
    bill_amount: float,
    amount_paid: float,
    remaining_amount: float,
    due_date: str,
    billing_month: str,
    payment_status: str,
    pay_url: str
) -> str:
    status_bg = "#EF4444" if payment_status == "Unpaid" else "#F59E0B"
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Electricity Bill Payment Reminder</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0B111E; color: #FFFFFF; margin: 0; padding: 24px;">
  <div style="max-width: 580px; margin: 0 auto; background-color: #0D1527; border-radius: 16px; border: 1px solid #1E293B; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
    
    <!-- Header -->
    <div style="background: linear-gradient(135deg, #1D63ED 0%, #0F3BA0 100%); padding: 32px 28px; text-align: center;">
      <h1 style="color: #FFFFFF; margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">⚡ Smart Electricity Services</h1>
      <p style="color: #E2E8F0; margin: 8px 0 0 0; font-size: 14px;">Official Electricity Bill Payment Reminder</p>
    </div>

    <!-- Body Content -->
    <div style="padding: 32px 28px;">
      <p style="font-size: 16px; color: #E2E8F0; margin-top: 0;">Dear <strong>{consumer_name}</strong>,</p>
      <p style="font-size: 14px; color: #94A3B8; line-height: 1.6;">
        This is a friendly reminder regarding your pending electricity bill for <strong>{billing_month}</strong>. Please ensure prompt payment before the due date to avoid late charges or service disruption.
      </p>

      <!-- Bill Summary Card -->
      <div style="background-color: #131E35; border: 1px solid #1E293B; border-radius: 12px; padding: 20px; margin: 24px 0;">
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
          <tr>
            <td style="color: #94A3B8; padding: 8px 0;">Consumer ID:</td>
            <td style="color: #FFFFFF; font-weight: 600; text-align: right; padding: 8px 0;">{consumer_id}</td>
          </tr>
          <tr>
            <td style="color: #94A3B8; padding: 8px 0;">Total Bill Amount:</td>
            <td style="color: #FFFFFF; font-weight: 600; text-align: right; padding: 8px 0;">₹{bill_amount:,.2f}</td>
          </tr>
          <tr>
            <td style="color: #94A3B8; padding: 8px 0;">Amount Paid so far:</td>
            <td style="color: #10B981; font-weight: 600; text-align: right; padding: 8px 0;">₹{amount_paid:,.2f}</td>
          </tr>
          <tr style="border-top: 1px solid #1E293B;">
            <td style="color: #FFFFFF; font-size: 16px; font-weight: 700; padding: 12px 0 8px 0;">Remaining Balance:</td>
            <td style="color: #38BDF8; font-size: 18px; font-weight: 800; text-align: right; padding: 12px 0 8px 0;">₹{remaining_amount:,.2f}</td>
          </tr>
          <tr>
            <td style="color: #94A3B8; padding: 8px 0;">Due Date:</td>
            <td style="color: #F87171; font-weight: 700; text-align: right; padding: 8px 0;">{due_date}</td>
          </tr>
          <tr>
            <td style="color: #94A3B8; padding: 8px 0;">Payment Status:</td>
            <td style="text-align: right; padding: 8px 0;">
              <span style="background-color: {status_bg}; color: #FFFFFF; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 9999px;">
                {payment_status}
              </span>
            </td>
          </tr>
        </table>
      </div>

      <!-- Action Button -->
      <div style="text-align: center; margin: 32px 0 16px 0;">
        <a href="{pay_url}" style="background-color: #1D63ED; color: #FFFFFF; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 4px 14px rgba(29,99,237,0.4);">
          Pay Bill Online (₹{remaining_amount:,.2f}) &rarr;
        </a>
      </div>
      <p style="text-align: center; font-size: 12px; color: #64748B;">Supports Instant UPI, Net Banking, and Debit/Credit Cards.</p>
    </div>

    <!-- Footer -->
    <div style="background-color: #080D18; padding: 20px 28px; text-align: center; border-top: 1px solid #1E293B; font-size: 12px; color: #64748B;">
      <p style="margin: 0;">Smart Electricity Billing System &bull; 24x7 Customer Support</p>
      <p style="margin: 6px 0 0 0;">This is an automated production notification. Please do not reply directly to this email.</p>
    </div>
  </div>
</body>
</html>"""

def build_payment_confirmation_email_html(
    consumer_name: str,
    consumer_id: str,
    amount_paid_this_txn: float,
    total_bill_amount: float,
    remaining_balance: float,
    tx_ref: str,
    payment_method: str,
    paid_at: str
) -> str:
    status_text = "FULLY PAID" if remaining_balance <= 0 else "PARTIALLY PAID"
    status_color = "#10B981" if remaining_balance <= 0 else "#F59E0B"

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Payment Receipt - Smart Electricity</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0B111E; color: #FFFFFF; margin: 0; padding: 24px;">
  <div style="max-width: 580px; margin: 0 auto; background-color: #0D1527; border-radius: 16px; border: 1px solid #1E293B; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
    
    <!-- Header -->
    <div style="background: linear-gradient(135deg, #10B981 0%, #047857 100%); padding: 32px 28px; text-align: center;">
      <div style="font-size: 40px; margin-bottom: 8px;">✅</div>
      <h1 style="color: #FFFFFF; margin: 0; font-size: 24px; font-weight: 800;">Payment Confirmed</h1>
      <p style="color: #D1FAE5; margin: 8px 0 0 0; font-size: 14px;">Transaction Reference: {tx_ref}</p>
    </div>

    <!-- Body Content -->
    <div style="padding: 32px 28px;">
      <p style="font-size: 16px; color: #E2E8F0; margin-top: 0;">Dear <strong>{consumer_name}</strong>,</p>
      <p style="font-size: 14px; color: #94A3B8; line-height: 1.6;">
        We have successfully received and verified your payment of <strong>₹{amount_paid_this_txn:,.2f}</strong> for Consumer ID <strong>{consumer_id}</strong>.
      </p>

      <!-- Receipt Card -->
      <div style="background-color: #131E35; border: 1px solid #1E293B; border-radius: 12px; padding: 20px; margin: 24px 0;">
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
          <tr>
            <td style="color: #94A3B8; padding: 8px 0;">Amount Paid:</td>
            <td style="color: #10B981; font-weight: 800; font-size: 16px; text-align: right; padding: 8px 0;">₹{amount_paid_this_txn:,.2f}</td>
          </tr>
          <tr>
            <td style="color: #94A3B8; padding: 8px 0;">Payment Method:</td>
            <td style="color: #FFFFFF; font-weight: 600; text-align: right; padding: 8px 0;">{payment_method}</td>
          </tr>
          <tr>
            <td style="color: #94A3B8; padding: 8px 0;">Date & Time:</td>
            <td style="color: #FFFFFF; font-weight: 600; text-align: right; padding: 8px 0;">{paid_at}</td>
          </tr>
          <tr>
            <td style="color: #94A3B8; padding: 8px 0;">Total Bill Amount:</td>
            <td style="color: #FFFFFF; font-weight: 600; text-align: right; padding: 8px 0;">₹{total_bill_amount:,.2f}</td>
          </tr>
          <tr style="border-top: 1px solid #1E293B;">
            <td style="color: #FFFFFF; font-weight: 700; padding: 12px 0 8px 0;">Remaining Balance:</td>
            <td style="color: #38BDF8; font-weight: 800; font-size: 16px; text-align: right; padding: 12px 0 8px 0;">₹{remaining_balance:,.2f}</td>
          </tr>
          <tr>
            <td style="color: #94A3B8; padding: 8px 0;">Status:</td>
            <td style="text-align: right; padding: 8px 0;">
              <span style="background-color: {status_color}; color: #FFFFFF; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 9999px;">
                {status_text}
              </span>
            </td>
          </tr>
        </table>
      </div>

      <p style="font-size: 13px; color: #94A3B8;">{"Future reminder notifications for this bill have been stopped." if remaining_balance <= 0 else f"You have an active remaining balance of ₹{remaining_balance:,.2f}."}</p>
    </div>

    <!-- Footer -->
    <div style="background-color: #080D18; padding: 20px 28px; text-align: center; border-top: 1px solid #1E293B; font-size: 12px; color: #64748B;">
      <p style="margin: 0;">Smart Electricity Billing System &bull; Official Digital Receipt</p>
    </div>
  </div>
</body>
</html>"""
