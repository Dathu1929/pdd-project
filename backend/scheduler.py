import os
import asyncio
import supabase_sqlite_mock as sqlite3
import datetime
import logging
from typing import Dict, Any, List, Optional
from notifications import (
    send_sms,
    send_email,
    mask_phone,
    mask_email,
    build_reminder_email_html
)

logger = logging.getLogger("scheduler")

def get_due_date_difference(due_date_str: str) -> Optional[int]:
    """Returns (due_date - today) in days. Negative means overdue."""
    try:
        due_date = datetime.datetime.strptime(due_date_str.strip(), "%Y-%m-%d").date()
        today = datetime.date.today()
        return (due_date - today).days
    except Exception as e:
        logger.error(f"Error parsing due date '{due_date_str}': {e}")
        return None

def get_next_scheduled_reminder_text(due_date_str: str) -> str:
    """Calculates the upcoming reminder milestone for display on dashboard."""
    diff = get_due_date_difference(due_date_str)
    if diff is None:
        return "N/A"
    
    if diff > 7:
        rem_date = datetime.date.today() + datetime.timedelta(days=(diff - 7))
        return f"7 days before ({rem_date.strftime('%d-%b-%Y')})"
    elif diff > 3:
        rem_date = datetime.date.today() + datetime.timedelta(days=(diff - 3))
        return f"3 days before ({rem_date.strftime('%d-%b-%Y')})"
    elif diff > 1:
        rem_date = datetime.date.today() + datetime.timedelta(days=(diff - 1))
        return f"1 day before ({rem_date.strftime('%d-%b-%Y')})"
    elif diff == 1:
        return "Due Tomorrow (1 day before)"
    elif diff == 0:
        return "Due Today (Immediate Alert)"
    else:
        return f"Overdue by {abs(diff)} day(s) - Immediate Reminder"


def evaluate_and_send_reminders(get_db_func, force_send: bool = False) -> Dict[str, Any]:
    """
    Scans all unpaid/partially paid bills and sends real SMS & Email reminders according to schedule:
    - 7 days before due date
    - 3 days before due date
    - 1 day before due date
    - On due date (0 days)
    - After due date if still unpaid (overdue reminder)
    """
    conn = get_db_func()
    cursor = conn.cursor()
    
    # Select all unpaid/partially paid bills with meter and user contact details
    cursor.execute("""
        SELECT 
            b.id as bill_id,
            b.billing_month,
            b.bill_amount,
            b.amount_paid,
            b.remaining_amount,
            b.due_date,
            b.bill_issue_date,
            b.payment_status,
            b.consumer_name as bill_consumer_name,
            b.mobile_number as bill_mobile,
            b.email_address as bill_email,
            m.id as meter_id,
            m.service_number,
            m.board_name,
            m.consumer_name as meter_consumer_name,
            u.id as user_id,
            u.name as user_name,
            u.email as user_email,
            u.phone as user_phone,
            COALESCE(u.sms_recipient_phone, b.mobile_number, u.phone) as target_mobile,
            COALESCE(u.email_recipient_email, b.email_address, u.email) as target_email,
            COALESCE(u.sms_reminders, 1) as sms_enabled,
            COALESCE(u.email_reminders, 1) as email_enabled
        FROM bills b
        JOIN meters m ON b.meter_id = m.id
        JOIN users u ON m.user_id = u.id
        WHERE b.payment_status != 'Paid' AND b.remaining_amount > 0
    """)
    
    unpaid_bills = [dict(row) for row in cursor.fetchall()]
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    app_base_url = os.getenv("APP_BASE_URL", "http://localhost:8000")
    
    results = {
        "evaluated_bills": len(unpaid_bills),
        "sms_sent": 0,
        "sms_failed": 0,
        "email_sent": 0,
        "email_failed": 0,
        "skipped": 0,
        "logs": []
    }
    
    for bill in unpaid_bills:
        due_date_str = bill["due_date"]
        diff = get_due_date_difference(due_date_str)
        if diff is None:
            continue
            
        # Determine milestone
        trigger_milestone = None
        if diff == 7:
            trigger_milestone = "7_DAYS_BEFORE"
        elif diff == 3:
            trigger_milestone = "3_DAYS_BEFORE"
        elif diff == 1:
            trigger_milestone = "1_DAY_BEFORE"
        elif diff == 0:
            trigger_milestone = "ON_DUE_DATE"
        elif diff < 0:
            trigger_milestone = f"OVERDUE_{abs(diff)}_DAYS"
        elif force_send:
            trigger_milestone = f"MANUAL_TRIGGER_{diff}_DAYS"
            
        if not trigger_milestone and not force_send:
            results["skipped"] += 1
            continue
            
        consumer_name = bill["bill_consumer_name"] or bill["meter_consumer_name"] or bill["user_name"]
        # Collect distinct target phone numbers (bill mobile, user registration mobile, and settings target mobile)
        sms_recipients = []
        if bill.get("bill_mobile") and bill["bill_mobile"].strip():
            sms_recipients.append(bill["bill_mobile"].strip())
        if bill.get("user_phone") and bill["user_phone"].strip() and bill["user_phone"].strip() not in sms_recipients:
            sms_recipients.append(bill["user_phone"].strip())
        if bill.get("target_mobile") and bill["target_mobile"].strip() and bill["target_mobile"].strip() not in sms_recipients:
            sms_recipients.append(bill["target_mobile"].strip())

        # Collect distinct target email addresses (bill email, user registration email, and settings target email)
        email_recipients = []
        if bill.get("bill_email") and bill["bill_email"].strip():
            email_recipients.append(bill["bill_email"].strip())
        if bill.get("user_email") and bill["user_email"].strip() and bill["user_email"].strip() not in email_recipients:
            email_recipients.append(bill["user_email"].strip())
        if bill.get("target_email") and bill["target_email"].strip() and bill["target_email"].strip() not in email_recipients:
            email_recipients.append(bill["target_email"].strip())

        consumer_id = bill["service_number"] or f"CN{bill['meter_id']:08d}"
        
        bill_amount = float(bill["bill_amount"])
        amount_paid = float(bill["amount_paid"] or 0.0)
        remaining_amount = float(bill["remaining_amount"] if bill["remaining_amount"] is not None else bill_amount - amount_paid)
        
        # Check if reminder already dispatched today for this bill & milestone
        if not force_send:
            cursor.execute("""
                SELECT COUNT(*) as count FROM notification_history
                WHERE bill_id = ? AND DATE(sent_at) = ? AND title LIKE ?
            """, (bill["bill_id"], today_str, f"%{trigger_milestone}%"))
            if cursor.fetchone()["count"] > 0:
                results["skipped"] += 1
                continue

        # Format Dynamic Notification Content
        formatted_due_date = datetime.datetime.strptime(due_date_str, "%Y-%m-%d").strftime("%d-%b-%Y")
        sms_body = (
            f"Electricity Bill Reminder: Hello {consumer_name}, your bill for {bill['billing_month']} "
            f"has a pending balance of Rs {remaining_amount:.2f} (Total: Rs {bill_amount:.2f}). "
            f"Due date is {formatted_due_date}. Please pay before the due date to avoid disconnection."
        )
        
        email_subject = f"⚡ Electricity Bill Reminder: ₹{remaining_amount:.2f} Due on {formatted_due_date}"
        email_html = build_reminder_email_html(
            consumer_name=consumer_name,
            consumer_id=consumer_id,
            bill_amount=bill_amount,
            amount_paid=amount_paid,
            remaining_amount=remaining_amount,
            due_date=formatted_due_date,
            billing_month=bill["billing_month"],
            payment_status=bill["payment_status"],
            pay_url=f"{app_base_url}/#pay?bill_id={bill['bill_id']}"
        )
        
        # 1. Dispatch Real SMS
        if bill["sms_enabled"]:
            for target_phone in sms_recipients:
                if not target_phone:
                    continue
                sms_res = send_sms(target_phone, sms_body)
                status = "SENT" if sms_res["success"] else "FAILED"
                err_msg = sms_res.get("error")
                provider_resp_str = str(sms_res.get("response_data", {}))
                
                cursor.execute("""
                    INSERT INTO notification_history 
                    (user_id, bill_id, type, recipient, title, message, status, provider_response, error_message, sent_at)
                    VALUES (?, ?, 'SMS', ?, ?, ?, ?, ?, ?, ?)
                """, (
                    bill["user_id"],
                    bill["bill_id"],
                    mask_phone(target_phone),
                    f"Reminder [{trigger_milestone}]",
                    sms_body,
                    status,
                    provider_resp_str,
                    err_msg,
                    now_str
                ))
                
                if sms_res["success"]:
                    results["sms_sent"] += 1
                else:
                    results["sms_failed"] += 1
                    
                results["logs"].append({
                    "type": "SMS",
                    "recipient": mask_phone(target_phone),
                    "status": status,
                    "error": err_msg
                })
            
        # 2. Dispatch Real Email
        if bill["email_enabled"]:
            for target_email in email_recipients:
                if not target_email:
                    continue
                email_res = send_email(target_email, email_subject, email_html, sms_body)
                status = "SENT" if email_res["success"] else "FAILED"
                err_msg = email_res.get("error")
                provider_resp_str = str(email_res.get("response_data", {}))
                
                cursor.execute("""
                    INSERT INTO notification_history 
                    (user_id, bill_id, type, recipient, title, message, status, provider_response, error_message, sent_at)
                    VALUES (?, ?, 'Email', ?, ?, ?, ?, ?, ?, ?)
                """, (
                    bill["user_id"],
                    bill["bill_id"],
                    mask_email(target_email),
                    email_subject,
                    f"Email notification for {bill['billing_month']} bill of ₹{remaining_amount:.2f}",
                    status,
                    provider_resp_str,
                    err_msg,
                    now_str
                ))
                
                if email_res["success"]:
                    results["email_sent"] += 1
                else:
                    results["email_failed"] += 1
                    
                results["logs"].append({
                    "type": "Email",
                    "recipient": mask_email(target_email),
                    "status": status,
                    "error": err_msg
                })
            
        # Also create in-app notification
        cursor.execute("""
            INSERT INTO notifications (user_id, title, message, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            bill["user_id"],
            f"Bill Reminder ({bill['billing_month']})",
            f"₹{remaining_amount:.2f} is due on {formatted_due_date}.",
            now_str
        ))
        
        conn.commit()
        
    # 3. Evaluate Next Bill Predictions & Smart Reminders
    cursor.execute("""
        SELECT m.id as meter_id, m.service_number, m.board_name, m.prediction_reminder_enabled,
               u.id as user_id, u.name as user_name, u.email as user_email, u.phone as user_phone
        FROM meters m
        JOIN users u ON m.user_id = u.id
    """)
    meters = [dict(row) for row in cursor.fetchall()]
    
    for m in meters:
        if not m["prediction_reminder_enabled"]:
            continue
            
        pred_date_str = "2026-09-05"
        pred_dt = datetime.date(2026, 9, 5)
        
        # Calculate days difference relative to current date (e.g. 2026-08-28 as current date in demo)
        today = datetime.date.today()
        diff = (pred_dt - today).days
        
        # Trigger on milestone days (7, 3, 1, 0) or manual trigger
        if diff in [7, 3, 1, 0] or force_send:
            # Check if a new bill for September 2026 has already been added to the database
            cursor.execute("""
                SELECT COUNT(*) as count FROM bills
                WHERE meter_id = ? AND billing_month LIKE '%September%'
            """, (m["meter_id"],))
            new_bill_exists = cursor.fetchone()["count"] > 0
            
            # Prevent double notification today
            cursor.execute("""
                SELECT COUNT(*) as count FROM notification_history
                WHERE user_id = ? AND title LIKE '%NEXT BILL%' AND DATE(sent_at) = ?
            """, (m["user_id"], today_str))
            already_notified = cursor.fetchone()["count"] > 0
            
            if not already_notified:
                if new_bill_exists:
                    # New bill is detected!
                    cursor.execute("""
                        INSERT INTO notifications (user_id, title, message, created_at)
                        VALUES (?, '✅ New Electricity Bill Available', ?, ?)
                    """, (m["user_id"], f"A new bill has been auto-detected for Service Number {m['service_number']}. Amount due is ready.", now_str))
                    # Turn off prediction reminder for this cycle
                    cursor.execute("UPDATE meters SET prediction_reminder_enabled = 0 WHERE id = ?", (m["meter_id"],))
                else:
                    # Expected date alert
                    msg = f"Your next electricity bill is expected around {pred_dt.strftime('%d-%b-%Y')}."
                    
                    cursor.execute("""
                        INSERT INTO notifications (user_id, title, message, created_at)
                        VALUES (?, '🔮 NEXT BILL REMINDER', ?, ?)
                    """, (m["user_id"], msg, now_str))
                    
                    send_email(m["user_email"], "🔮 NEXT BILL REMINDER", f"<h3>Prediction Alert</h3><p>{msg}</p>")
                    send_sms(m["user_phone"], f"NEXT BILL REMINDER: {msg}")
                    
                    cursor.execute("""
                        INSERT INTO notification_history (user_id, bill_id, type, recipient, title, message, status, provider_response, error_message, sent_at)
                        VALUES (?, NULL, 'In-App', 'System', '🔮 NEXT BILL REMINDER', ?, 'SENT', '{}', NULL, ?)
                    """, (m["user_id"], msg, now_str))
                    
                conn.commit()

    conn.close()
    return results


async def periodic_reminder_checker(get_db_func):
    """Asynchronous background loop that runs periodically to trigger scheduled reminders."""
    interval = int(os.getenv("REMINDER_CHECK_INTERVAL_SECONDS", "3600"))
    logger.info(f"Background reminder scheduler started. Interval: {interval}s")
    while True:
        try:
            logger.info("Executing scheduled reminder check...")
            res = evaluate_and_send_reminders(get_db_func, force_send=False)
            logger.info(f"Reminder check completed: {res['sms_sent']} SMS sent, {res['email_sent']} Email sent, {res['sms_failed']} SMS failed, {res['email_failed']} Email failed.")
        except Exception as e:
            logger.error(f"Error during periodic reminder check: {e}", exc_info=True)
        await asyncio.sleep(interval)
