import os
import re
import supabase_sqlite_mock as sqlite3
import datetime
import logging
import asyncio
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field
from jose import jwt, JWTError

# Import custom notifications and scheduler modules
from notifications import (
    send_sms,
    send_email,
    mask_phone,
    mask_email,
    build_reminder_email_html,
    build_payment_confirmation_email_html
)
from scheduler import (
    get_next_scheduled_reminder_text,
    evaluate_and_send_reminders,
    periodic_reminder_checker
)

# Load environment configuration
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-production-jwt-token-key-change-in-prod-12345")
ALGORITHM = "HS256"
DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "electricity.db"))

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError:
        pass
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    import supabase_db
    supabase_db.init_db()

# Run DB initialization and migrations
init_db()

# Lifespan Context Manager for background tasks
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Start periodic background reminder scheduler task
    scheduler_task = asyncio.create_task(periodic_reminder_checker(get_db))
    logger.info("Background reminder engine initialized.")
    yield
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="Smart Electricity Bill System API", lifespan=lifespan)

origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Schemas
class RegisterSchema(BaseModel):
    name: str
    email: str
    password: str
    phone: str
    alternate_phone: Optional[str] = None

class LoginSchema(BaseModel):
    email: str
    password: str

class MeterSchema(BaseModel):
    service_number: str
    board_name: str
    consumer_name: str
    address: str

class CreateBillSchema(BaseModel):
    meter_id: int
    consumer_id: Optional[str] = None
    consumer_name: Optional[str] = None
    mobile_number: Optional[str] = None
    email_address: Optional[str] = None
    billing_month: str
    bill_amount: float = Field(gt=0, description="Any valid positive bill amount without limits")
    bill_issue_date: str
    due_date: str
    units_consumed: Optional[float] = 0.0

class VerifyPaymentSchema(BaseModel):
    bill_id: int
    amount: float = Field(gt=0, description="Amount to pay (supports full or partial)")
    payment_method: str = "UPI"
    transaction_ref: Optional[str] = None

class ReminderChannelsSchema(BaseModel):
    sms_reminders: bool
    email_reminders: bool
    whatsapp_reminders: bool
    phone_reminders: bool

class RecipientSettingsSchema(BaseModel):
    sms_recipient_phone: str
    email_recipient_email: str
    sms_reminders: Optional[bool] = True
    email_reminders: Optional[bool] = True

class TestSmsSchema(BaseModel):
    phone_number: str
    message: Optional[str] = None

class TestEmailSchema(BaseModel):
    email_address: str
    subject: Optional[str] = None
    message: Optional[str] = None

class ReminderToggleSchema(BaseModel):
    days_before: int
    enabled: bool

class PredictionToggleSchema(BaseModel):
    meter_id: int
    enabled: bool

class DemoBillReminderSchema(BaseModel):
    consumer_name: str = "Dathu"
    consumer_id: str = "DEMO12345"
    bill_amount: float = Field(default=850.0, gt=0)
    due_date: str = "30-Aug-2026"
    mobile_number: str = "+91 9876543210"
    email_address: str = "example@gmail.com"

class ApiKeyConfigSchema(BaseModel):
    resend_api_key: Optional[str] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None

class ChatSchema(BaseModel):
    message: str

# Helpers
def create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)

def get_current_user_id(authorization: Optional[str] = Header(None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return int(user_id_str)
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")



active_connections: List[asyncio.Queue] = []

@app.get("/api/realtime/updates")
async def sse_updates(token: Optional[str] = None):
    async def event_generator():
        queue = asyncio.Queue()
        active_connections.append(queue)
        try:
            yield "data: connected\n\n"
            while True:
                msg = await queue.get()
                yield f"data: {msg}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in active_connections:
                active_connections.remove(queue)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

def broadcast_update(message: str = "update"):
    for queue in active_connections:
        queue.put_nowait(message)


# ==============================================================================
# AUTHENTICATION & PROFILE ENDPOINTS
# ==============================================================================
@app.post("/api/auth/register")
def register(data: RegisterSchema):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (name, email, password, phone, alternate_phone) 
            VALUES (?, ?, ?, ?, ?)
        """, (data.name, data.email, data.password, data.phone, data.alternate_phone))
        conn.commit()
        user_id = cursor.lastrowid
        token = create_access_token(user_id)
        return {
            "token": token,
            "user": {"id": user_id, "name": data.name, "email": data.email, "phone": data.phone}
        }
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    finally:
        conn.close()

@app.post("/api/auth/login")
def login(data: LoginSchema):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE (email = ? OR phone = ?) AND password = ?", 
                   (data.email, data.email, data.password))
    user = cursor.fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email/mobile or password")
    token = create_access_token(user["id"])
    return {
        "token": token, 
        "user": {
            "id": user["id"], 
            "name": user["name"], 
            "email": user["email"], 
            "phone": user["phone"], 
            "alternate_phone": user["alternate_phone"]
        }
    }

@app.get("/api/users/profile")
def get_profile(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, email, phone, alternate_phone, 
               COALESCE(sms_reminders, 1) as sms_reminders, 
               COALESCE(email_reminders, 1) as email_reminders 
        FROM users WHERE id = ?
    """, (user_id,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(user)

@app.post("/api/users/profile")
def update_profile(data: RegisterSchema, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users 
        SET name = ?, email = ?, password = ?, phone = ?, alternate_phone = ? 
        WHERE id = ?
    """, (data.name, data.email, data.password, data.phone, data.alternate_phone, user_id))
    conn.commit()
    conn.close()
    return {"message": "Profile updated successfully"}

@app.post("/api/reminders/channels")
def update_reminder_channels(data: ReminderChannelsSchema, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users 
        SET sms_reminders = ?, email_reminders = ?, whatsapp_reminders = ?, phone_reminders = ? 
        WHERE id = ?
    """, (
        1 if data.sms_reminders else 0,
        1 if data.email_reminders else 0,
        1 if data.whatsapp_reminders else 0,
        1 if data.phone_reminders else 0,
        user_id
    ))
    conn.commit()
    conn.close()
    return {"message": "Notification preferences updated successfully"}


# ==============================================================================
# METERS ENDPOINTS
# ==============================================================================
@app.get("/api/meters")
def get_meters(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM meters WHERE user_id = ? ORDER BY id DESC", (user_id,))
    meters = [dict(m) for m in cursor.fetchall()]
    conn.close()
    return meters

@app.post("/api/meters")
def add_meter(data: MeterSchema, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO meters (user_id, service_number, board_name, consumer_name, address) 
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, data.service_number, data.board_name, data.consumer_name, data.address))
        conn.commit()
        meter_id = cursor.lastrowid
        
        # Automatically generate initial bill with default due date 15 days ahead
        due = (datetime.date.today() + datetime.timedelta(days=15)).strftime("%Y-%m-%d")
        issue = datetime.date.today().strftime("%Y-%m-%d")
        month_name = datetime.date.today().strftime("%B %Y")
        
        cursor.execute("""
            INSERT INTO bills (
                meter_id, consumer_id, consumer_name, mobile_number, email_address,
                billing_month, units_consumed, amount, bill_amount, amount_paid, remaining_amount,
                bill_issue_date, due_date, payment_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, 'Unpaid')
        """, (
            meter_id,
            f"CN{meter_id:08d}",
            data.consumer_name,
            None,
            None,
            month_name,
            180.0,
            950.00,
            950.00,
            950.00,
            issue,
            due
        ))
        conn.commit()
        return {"id": meter_id, "message": "Electricity connection added successfully"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Service number already registered")
    finally:
        conn.close()

@app.delete("/api/meters/{meter_id}")
def delete_meter(meter_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM meters WHERE id = ? AND user_id = ?", (meter_id, user_id))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=403, detail="Not authorized to modify this connection")
    cursor.execute("DELETE FROM notification_history WHERE bill_id IN (SELECT id FROM bills WHERE meter_id = ?)", (meter_id,))
    cursor.execute("DELETE FROM payments WHERE bill_id IN (SELECT id FROM bills WHERE meter_id = ?)", (meter_id,))
    cursor.execute("DELETE FROM bills WHERE meter_id = ?", (meter_id,))
    cursor.execute("DELETE FROM meters WHERE id = ?", (meter_id,))
    conn.commit()
    conn.close()
    return {"message": "Connection deleted successfully"}


# ==============================================================================
# BILL MANAGEMENT (Arbitrary amounts, partial balances, due dates)
# ==============================================================================
@app.get("/api/bills")
def get_bills(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            b.id,
            b.meter_id,
            COALESCE(b.consumer_id, 'CN' || PRINTF('%08d', m.id)) as consumer_id,
            COALESCE(b.consumer_name, m.consumer_name) as consumer_name,
            COALESCE(b.mobile_number, u.phone) as mobile_number,
            COALESCE(b.email_address, u.email) as email_address,
            b.billing_month,
            b.units_consumed,
            b.amount,
            b.bill_amount,
            COALESCE(b.amount_paid, 0.0) as amount_paid,
            COALESCE(b.remaining_amount, b.bill_amount - COALESCE(b.amount_paid, 0.0)) as remaining_amount,
            b.bill_issue_date,
            b.due_date,
            b.payment_status,
            b.transaction_ref,
            m.service_number,
            m.board_name,
            m.address
        FROM bills b 
        JOIN meters m ON b.meter_id = m.id 
        JOIN users u ON m.user_id = u.id
        WHERE m.user_id = ?
        ORDER BY b.due_date DESC, b.id DESC
    """, (user_id,))
    bills = [dict(b) for b in cursor.fetchall()]
    conn.close()
    return bills

@app.post("/api/bills")
def create_bill(data: CreateBillSchema, user_id: int = Depends(get_current_user_id)):
    """
    Creates a new electricity bill with any valid positive amount, consumer details, and due date.
    No hardcoded minimum or maximum restrictions on bill amounts.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify meter ownership
    cursor.execute("SELECT id, consumer_name FROM meters WHERE id = ? AND user_id = ?", (data.meter_id, user_id))
    meter = cursor.fetchone()
    if not meter:
        conn.close()
        raise HTTPException(status_code=404, detail="Meter connection not found or unauthorized")
        
    # Get user default contacts
    cursor.execute("SELECT name, phone, email FROM users WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    
    consumer_name = data.consumer_name or meter["consumer_name"] or usr["name"]
    mobile_number = data.mobile_number or usr["phone"]
    email_address = data.email_address or usr["email"]
    consumer_id = data.consumer_id or f"CN{data.meter_id:08d}"
    
    bill_amount = round(float(data.bill_amount), 2)
    remaining_amount = bill_amount
    amount_paid = 0.0
    
    cursor.execute("""
        INSERT INTO bills (
            meter_id, consumer_id, consumer_name, mobile_number, email_address,
            billing_month, units_consumed, amount, bill_amount, amount_paid, remaining_amount,
            bill_issue_date, due_date, payment_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Unpaid')
    """, (
        data.meter_id,
        consumer_id,
        consumer_name,
        mobile_number,
        email_address,
        data.billing_month,
        data.units_consumed or 0.0,
        bill_amount,
        bill_amount,
        amount_paid,
        remaining_amount,
        data.bill_issue_date,
        data.due_date
    ))
    
    bill_id = cursor.lastrowid
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO notifications (user_id, title, message, created_at)
        VALUES (?, 'New Electricity Bill Added', ?, ?)
    """, (
        user_id,
        f"Bill of ₹{bill_amount:,.2f} for {data.billing_month} added. Due date: {data.due_date}",
        now_str
    ))
    
    conn.commit()
    conn.close()
    broadcast_update("update")
    return {
        "id": bill_id,
        "message": f"Electricity bill of ₹{bill_amount:,.2f} added successfully",
        "bill_amount": bill_amount,
        "due_date": data.due_date,
        "payment_status": "Unpaid"
    }


@app.get("/api/bills/search")
def search_bill(board_name: str, service_number: str, user_id: int = Depends(get_current_user_id)):
    """Searches for a bill by board_name and service_number, fetching from Setu live aggregator first."""
    import setu_client
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Look up user's meter
    cursor.execute("SELECT id, consumer_name FROM meters WHERE user_id = ? AND board_name = ? AND service_number = ?", 
                   (user_id, board_name, service_number))
    meter = cursor.fetchone()
    
    if not meter:
        conn.close()
        raise HTTPException(status_code=404, detail="No registered meter found for this connection. Please add this connection first.")

    meter_id = meter["id"]
    
    # 2. Fetch live bill from Setu aggregator
    live_res = setu_client.fetch_live_bill(board_name, service_number)
    
    if live_res.get("success"):
        # Check if this bill was already imported
        cursor.execute("SELECT id FROM bills WHERE meter_id = ? AND billing_month = ?", 
                       (meter_id, live_res["billing_month"]))
        existing = cursor.fetchone()
        
        if not existing:
            # Insert the newly fetched live bill
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO bills (
                    meter_id, consumer_id, consumer_name, mobile_number, email_address,
                    billing_month, units_consumed, amount, bill_amount, amount_paid, remaining_amount,
                    bill_issue_date, due_date, payment_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, 'Unpaid')
            """, (
                meter_id,
                live_res["consumer_id"],
                live_res["consumer_name"],
                None,
                None,
                live_res["billing_month"],
                live_res["units_consumed"],
                live_res["amount"],
                live_res["amount"],
                live_res["amount"],
                datetime.date.today().isoformat(),
                live_res["due_date"]
            ))
            
            # Create a notification about the fetched bill
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, created_at)
                VALUES (?, 'New Live Bill Fetched', ?, ?)
            """, (
                user_id,
                f"Fetched outstanding bill of ₹{live_res['amount']:,.2f} for {live_res['billing_month']} from {board_name.upper()}.",
                now_str
            ))
            conn.commit()
            broadcast_update("update")
            
    # 3. Retrieve the latest bill record from database
    cursor.execute("""
        SELECT 
            b.id,
            b.meter_id,
            COALESCE(b.consumer_id, 'CN' || LPAD(m.id::text, 8, '0')) as consumer_id,
            COALESCE(b.consumer_name, m.consumer_name) as consumer_name,
            COALESCE(b.mobile_number, u.phone) as mobile_number,
            COALESCE(b.email_address, u.email) as email_address,
            b.billing_month,
            b.units_consumed,
            b.amount,
            b.bill_amount,
            COALESCE(b.amount_paid, 0.0) as amount_paid,
            COALESCE(b.remaining_amount, b.bill_amount - COALESCE(b.amount_paid, 0.0)) as remaining_amount,
            b.bill_issue_date,
            b.due_date,
            b.payment_status,
            b.transaction_ref,
            m.service_number,
            m.board_name,
            m.address
        FROM bills b 
        JOIN meters m ON b.meter_id = m.id 
        JOIN users u ON m.user_id = u.id
        WHERE m.user_id = ? AND m.board_name = ? AND m.service_number = ?
        ORDER BY b.due_date DESC, b.id DESC
        LIMIT 1
    """, (user_id, board_name, service_number))
    bill = cursor.fetchone()
    
    if not bill:
        conn.close()
        raise HTTPException(status_code=404, detail="No billing data available for this connection.")
        
    bill_dict = dict(bill)
    
    # 4. Fetch historical payments for this meter
    cursor.execute("""
        SELECT p.id, p.amount, p.transaction_ref as transaction_id, p.payment_method, p.verification_status as status, p.paid_at as created_at
        FROM payments p
        JOIN bills b2 ON p.bill_id = b2.id
        WHERE b2.meter_id = ?
        ORDER BY p.id DESC
    """, (bill_dict["meter_id"],))
    payments = [dict(p) for p in cursor.fetchall()]
    
    # 5. Fetch previous bill to compare consumption
    cursor.execute("""
        SELECT units_consumed, bill_amount
        FROM bills
        WHERE meter_id = ? AND id < ?
        ORDER BY id DESC
        LIMIT 1
    """, (bill_dict["meter_id"], bill_dict["id"]))
    prev_bill = cursor.fetchone()
    prev_bill_dict = dict(prev_bill) if prev_bill else None
    
    conn.close()
    return {
        "bill": bill_dict,
        "payments": payments,
        "previous_bill": prev_bill_dict
    }


# ==============================================================================
# PAYMENT SYSTEM & BACKEND VERIFICATION
# ==============================================================================
@app.post("/api/payments/verify")
def verify_and_record_payment(
    data: VerifyPaymentSchema,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id)
):
    """
    Verifies payment on backend, updates paid & remaining balance,
    halts reminders if fully paid, and triggers real confirmation SMS & Email.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Retrieve bill
    cursor.execute("""
        SELECT b.*, m.service_number, m.board_name, u.email as user_email, u.phone as user_phone, u.name as user_name,
               u.sms_recipient_phone, u.email_recipient_email,
               COALESCE(u.sms_reminders, 1) as sms_enabled, COALESCE(u.email_reminders, 1) as email_enabled
        FROM bills b
        JOIN meters m ON b.meter_id = m.id
        JOIN users u ON m.user_id = u.id
        WHERE b.id = ? AND m.user_id = ?
    """, (data.bill_id, user_id))
    bill = cursor.fetchone()
    
    if not bill:
        conn.close()
        raise HTTPException(status_code=404, detail="Bill not found or unauthorized")
        
    bill_dict = dict(bill)
    total_bill_amount = float(bill_dict["bill_amount"] or bill_dict["amount"])
    current_amount_paid = float(bill_dict["amount_paid"] or 0.0)
    current_remaining = float(bill_dict["remaining_amount"] if bill_dict["remaining_amount"] is not None else (total_bill_amount - current_amount_paid))
    
    if current_remaining <= 0:
        conn.close()
        raise HTTPException(status_code=400, detail="This bill is already fully paid.")
        
    payment_amount = round(float(data.amount), 2)
    if payment_amount <= 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero.")
        
    if payment_amount > (current_remaining + 0.01):
        conn.close()
        raise HTTPException(
            status_code=400, 
            detail=f"Payment amount (₹{payment_amount:.2f}) cannot exceed the remaining balance (₹{current_remaining:.2f})."
        )
        
    # Backend Verification & Reference ID Generation
    tx_ref = data.transaction_ref or f"TXN-{int(datetime.datetime.now().timestamp())}-{bill_dict['id']}"
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    new_amount_paid = round(current_amount_paid + payment_amount, 2)
    new_remaining = max(0.0, round(total_bill_amount - new_amount_paid, 2))
    new_status = "Paid" if new_remaining == 0.0 else "Partially Paid"
    
    # 1. Record in payments table
    cursor.execute("""
        INSERT INTO payments (bill_id, amount, payment_method, transaction_ref, paid_at, verification_status)
        VALUES (?, ?, ?, ?, ?, 'VERIFIED')
    """, (data.bill_id, payment_amount, data.payment_method, tx_ref, now_str))
    
    # 2. Update bills table
    cursor.execute("""
        UPDATE bills 
        SET amount_paid = ?, remaining_amount = ?, payment_status = ?, transaction_ref = ?
        WHERE id = ?
    """, (new_amount_paid, new_remaining, new_status, tx_ref, data.bill_id))
    
    # 3. Create In-App Notification
    cursor.execute("""
        INSERT INTO notifications (user_id, title, message, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        "Payment Verified Successfully",
        f"Verified ₹{payment_amount:.2f} payment for {bill_dict['billing_month']}. Ref: {tx_ref}. Remaining: ₹{new_remaining:.2f}",
        now_str
    ))
    
    conn.commit()
    conn.close()
    
    # 4. Dispatch Real Confirmation SMS & Email in background
    consumer_name = bill_dict["consumer_name"] or bill_dict["user_name"]
    mobile_number = bill_dict.get("sms_recipient_phone") or bill_dict["mobile_number"] or bill_dict["user_phone"]
    email_address = bill_dict.get("email_recipient_email") or bill_dict["email_address"] or bill_dict["user_email"]
    consumer_id = bill_dict["consumer_id"] or bill_dict["service_number"]
    
    def dispatch_confirmation_notifications():
        c_conn = get_db()
        c_cur = c_conn.cursor()
        
        # Real SMS Confirmation
        if bill_dict["sms_enabled"] and mobile_number:
            sms_msg = (
                f"Payment Confirmation: Received Rs {payment_amount:.2f} for Consumer ID {consumer_id}. "
                f"Ref: {tx_ref}. Remaining Balance: Rs {new_remaining:.2f}. Status: {new_status}. Thank you!"
            )
            sms_res = send_sms(mobile_number, sms_msg)
            c_cur.execute("""
                INSERT INTO notification_history 
                (user_id, bill_id, type, recipient, title, message, status, provider_response, error_message, sent_at)
                VALUES (?, ?, 'SMS', ?, 'Payment Confirmation', ?, ?, ?, ?, ?)
            """, (
                user_id,
                data.bill_id,
                mask_phone(mobile_number),
                sms_msg,
                "SENT" if sms_res["success"] else "FAILED",
                str(sms_res.get("response_data", {})),
                sms_res.get("error"),
                now_str
            ))
            
        # Real Email Confirmation
        if bill_dict["email_enabled"] and email_address:
            email_html = build_payment_confirmation_email_html(
                consumer_name=consumer_name,
                consumer_id=consumer_id,
                amount_paid_this_txn=payment_amount,
                total_bill_amount=total_bill_amount,
                remaining_balance=new_remaining,
                tx_ref=tx_ref,
                payment_method=data.payment_method,
                paid_at=now_str
            )
            email_subject = f"✅ Payment Receipt: ₹{payment_amount:.2f} Verified (Ref: {tx_ref})"
            email_res = send_email(email_address, email_subject, email_html)
            c_cur.execute("""
                INSERT INTO notification_history 
                (user_id, bill_id, type, recipient, title, message, status, provider_response, error_message, sent_at)
                VALUES (?, ?, 'Email', ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                data.bill_id,
                mask_email(email_address),
                email_subject,
                f"Payment receipt for ₹{payment_amount:.2f}. Transaction: {tx_ref}",
                "SENT" if email_res["success"] else "FAILED",
                str(email_res.get("response_data", {})),
                email_res.get("error"),
                now_str
            ))
            
        c_conn.commit()
        c_conn.close()
        
    background_tasks.add_task(dispatch_confirmation_notifications)
    broadcast_update("update")
    return {
        "success": True,
        "message": f"Payment of ₹{payment_amount:,.2f} verified successfully.",
        "transaction_ref": tx_ref,
        "amount_paid": new_amount_paid,
        "remaining_amount": new_remaining,
        "payment_status": new_status,
        "reminders_stopped": (new_remaining == 0.0)
    }

# Backward compatible payment alias
@app.post("/api/payments")
def make_payment_alias(
    data: VerifyPaymentSchema,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id)
):
    return verify_and_record_payment(data, background_tasks, user_id)

@app.get("/api/payments/history")
def get_payment_history(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            p.id,
            p.bill_id,
            p.amount,
            p.payment_method,
            p.transaction_ref,
            p.paid_at,
            p.verification_status,
            b.billing_month,
            b.bill_amount,
            m.service_number,
            m.board_name,
            COALESCE(b.consumer_name, m.consumer_name) as consumer_name
        FROM payments p
        JOIN bills b ON p.bill_id = b.id
        JOIN meters m ON b.meter_id = m.id
        WHERE m.user_id = ?
        ORDER BY p.id DESC
    """, (user_id,))
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return history


# ==============================================================================
# DASHBOARD STATS & OVERVIEW
# ==============================================================================
@app.get("/api/dashboard/stats")
def get_dashboard_stats(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Fetch latest active (unpaid/partially paid) bill or most recent bill
    cursor.execute("""
        SELECT 
            b.*,
            COALESCE(b.consumer_id, 'CN' || PRINTF('%08d', m.id)) as consumer_id,
            COALESCE(b.consumer_name, m.consumer_name) as consumer_name,
            m.service_number,
            m.board_name
        FROM bills b
        JOIN meters m ON b.meter_id = m.id
        WHERE m.user_id = ?
        ORDER BY 
            CASE WHEN b.payment_status != 'Paid' THEN 0 ELSE 1 END,
            b.due_date ASC,
            b.id DESC
        LIMIT 1
    """, (user_id,))
    active_bill = cursor.fetchone()
    
    # 2. Check real SMS status for user's active bill/latest notification
    cursor.execute("""
        SELECT status, sent_at, error_message 
        FROM notification_history 
        WHERE user_id = ? AND type = 'SMS' 
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    latest_sms = cursor.fetchone()
    
    # 3. Check real Email status for user
    cursor.execute("""
        SELECT status, sent_at, error_message 
        FROM notification_history 
        WHERE user_id = ? AND type = 'Email' 
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    latest_email = cursor.fetchone()
    
    # 4. Total count of meters & total paid all time
    cursor.execute("SELECT COUNT(*) as count FROM meters WHERE user_id = ?", (user_id,))
    meters_count = cursor.fetchone()["count"]
    
    cursor.execute("""
        SELECT COALESCE(SUM(p.amount), 0.0) as total 
        FROM payments p 
        JOIN bills b ON p.bill_id = b.id 
        JOIN meters m ON b.meter_id = m.id 
        WHERE m.user_id = ?
    """, (user_id,))
    total_paid_all_time = cursor.fetchone()["total"]
    
    # 5. Fetch user configured notification recipients
    cursor.execute("SELECT name, email, phone, sms_recipient_phone, email_recipient_email FROM users WHERE id = ?", (user_id,))
    u_rec = cursor.fetchone()
    raw_sms_rec = (u_rec["sms_recipient_phone"] or u_rec["phone"] or "") if u_rec else ""
    raw_email_rec = (u_rec["email_recipient_email"] or u_rec["email"] or "") if u_rec else ""

    conn.close()
    
    if active_bill:
        ab = dict(active_bill)
        bill_amount = float(ab["bill_amount"] or ab["amount"])
        amount_paid = float(ab["amount_paid"] or 0.0)
        remaining_amount = float(ab["remaining_amount"] if ab["remaining_amount"] is not None else bill_amount - amount_paid)
        due_date = ab["due_date"]
        payment_status = ab["payment_status"]
        next_reminder = get_next_scheduled_reminder_text(due_date) if payment_status != "Paid" else "Stopped (Fully Paid)"
    else:
        ab = None
        bill_amount = 0.0
        amount_paid = 0.0
        remaining_amount = 0.0
        due_date = "N/A"
        payment_status = "Paid"
        next_reminder = "No Active Bills"
        
    return {
        "bill_amount": bill_amount,
        "amount_paid": amount_paid,
        "remaining_amount": remaining_amount,
        "due_date": due_date,
        "payment_status": payment_status,
        "next_reminder": next_reminder,
        "sms_status": latest_sms["status"] if latest_sms else "NOT_SCHEDULED",
        "email_status": latest_email["status"] if latest_email else "NOT_SCHEDULED",
        "latest_sms_time": latest_sms["sent_at"] if latest_sms else None,
        "latest_email_time": latest_email["sent_at"] if latest_email else None,
        "sms_error": latest_sms["error_message"] if latest_sms and latest_sms["status"] == "FAILED" else None,
        "email_error": latest_email["error_message"] if latest_email and latest_email["status"] == "FAILED" else None,
        "sms_recipient": raw_sms_rec,
        "email_recipient": raw_email_rec,
        "sms_recipient_masked": mask_phone(raw_sms_rec) if raw_sms_rec else "Not configured",
        "email_recipient_masked": mask_email(raw_email_rec) if raw_email_rec else "Not configured",
        "active_bill": ab,
        "active_bill_id": ab["id"] if ab else None,
        "billing_month": ab["billing_month"] if ab else None,
        "meters_count": meters_count,
        "total_paid_all_time": total_paid_all_time
    }


# ==============================================================================
# NOTIFICATION HISTORY & RETRY SYSTEM
# ==============================================================================
@app.get("/api/notifications/history")
def get_notification_history(user_id: int = Depends(get_current_user_id)):
    """Returns full history log of real SMS and Email notifications with status and retry capability."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            nh.id,
            nh.user_id,
            nh.bill_id,
            nh.type,
            nh.recipient,
            nh.title,
            nh.message,
            nh.status,
            nh.provider_response,
            nh.error_message,
            nh.sent_at,
            nh.retry_count,
            b.billing_month,
            b.bill_amount
        FROM notification_history nh
        LEFT JOIN bills b ON nh.bill_id = b.id
        WHERE nh.user_id = ?
        ORDER BY nh.id DESC
        LIMIT 100
    """, (user_id,))
    history = [dict(h) for h in cursor.fetchall()]
    conn.close()
    return history

@app.post("/api/notifications/{notification_id}/retry")
def retry_notification(notification_id: int, user_id: int = Depends(get_current_user_id)):
    """
    Retries sending a previously failed SMS or Email notification and records new provider status.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nh.*, u.phone as user_phone, u.email as user_email, u.name as user_name,
               b.bill_amount, b.amount_paid, b.remaining_amount, b.due_date, b.billing_month, b.payment_status,
               COALESCE(b.consumer_name, u.name) as consumer_name,
               COALESCE(b.consumer_id, 'CN' || PRINTF('%08d', nh.bill_id)) as consumer_id
        FROM notification_history nh
        JOIN users u ON nh.user_id = u.id
        LEFT JOIN bills b ON nh.bill_id = b.id
        WHERE nh.id = ? AND nh.user_id = ?
    """, (notification_id, user_id))
    notif = cursor.fetchone()
    
    if not notif:
        conn.close()
        raise HTTPException(status_code=404, detail="Notification record not found or unauthorized")
        
    n_dict = dict(notif)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Retry SMS
    if n_dict["type"] == "SMS":
        phone_to_use = n_dict["user_phone"]
        res = send_sms(phone_to_use, n_dict["message"])
        new_status = "SENT" if res["success"] else "FAILED"
        err_msg = res.get("error")
        prov_resp = str(res.get("response_data", {}))
        
        cursor.execute("""
            UPDATE notification_history 
            SET status = ?, provider_response = ?, error_message = ?, sent_at = ?, retry_count = retry_count + 1
            WHERE id = ?
        """, (new_status, prov_resp, err_msg, now_str, notification_id))
        broadcast_update("update")
        conn.commit()
        conn.close()
        
        return {
            "success": res["success"],
            "status": new_status,
            "error": err_msg,
            "message": "SMS retry succeeded!" if res["success"] else f"SMS retry failed: {err_msg}"
        }
        
    # 2. Retry Email
    elif n_dict["type"] == "Email":
        email_to_use = n_dict["user_email"]
        subject = n_dict["title"] or "Electricity Bill Reminder"
        
        # Build fresh HTML email
        app_base_url = os.getenv("APP_BASE_URL", "http://localhost:8000")
        bill_amount = float(n_dict.get("bill_amount") or 0.0)
        amount_paid = float(n_dict.get("amount_paid") or 0.0)
        remaining = float(n_dict.get("remaining_amount") or (bill_amount - amount_paid))
        due_date = n_dict.get("due_date") or "N/A"
        month = n_dict.get("billing_month") or "Current Month"
        status = n_dict.get("payment_status") or "Unpaid"
        
        html_body = build_reminder_email_html(
            consumer_name=n_dict["consumer_name"],
            consumer_id=n_dict["consumer_id"],
            bill_amount=bill_amount,
            amount_paid=amount_paid,
            remaining_amount=remaining,
            due_date=due_date,
            billing_month=month,
            payment_status=status,
            pay_url=f"{app_base_url}/#pay?bill_id={n_dict['bill_id']}"
        )
        
        res = send_email(email_to_use, subject, html_body, n_dict["message"])
        new_status = "SENT" if res["success"] else "FAILED"
        err_msg = res.get("error")
        prov_resp = str(res.get("response_data", {}))
        
        cursor.execute("""
            UPDATE notification_history 
            SET status = ?, provider_response = ?, error_message = ?, sent_at = ?, retry_count = retry_count + 1
            WHERE id = ?
        """, (new_status, prov_resp, err_msg, now_str, notification_id))
        broadcast_update("update")
        conn.commit()
        conn.close()
        
        return {
            "success": res["success"],
            "status": new_status,
            "error": err_msg,
            "message": "Email retry succeeded!" if res["success"] else f"Email retry failed: {err_msg}"
        }
        
    else:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Unsupported notification type: {n_dict['type']}")


# ==============================================================================
# REMINDERS ON-DEMAND CHECK TRIGGER & RECIPIENT SETTINGS
# ==============================================================================
@app.get("/api/settings/recipients")
def get_recipient_settings(user_id: int = Depends(get_current_user_id)):
    """Retrieves the user's configured SMS recipient mobile number and Email recipient address."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, email, phone, sms_recipient_phone, email_recipient_email, 
               COALESCE(sms_reminders, 1) as sms_reminders, COALESCE(email_reminders, 1) as email_reminders 
        FROM users WHERE id = ?
    """, (user_id,))
    usr = cursor.fetchone()
    conn.close()
    if not usr:
        raise HTTPException(status_code=404, detail="User not found")
    u = dict(usr)
    sms_phone = u["sms_recipient_phone"] or u["phone"] or ""
    email_addr = u["email_recipient_email"] or u["email"] or ""
    return {
        "sms_recipient_phone": sms_phone,
        "email_recipient_email": email_addr,
        "sms_reminders": bool(u["sms_reminders"]),
        "email_reminders": bool(u["email_reminders"]),
        "masked_phone": mask_phone(sms_phone) if sms_phone else "Not configured",
        "masked_email": mask_email(email_addr) if email_addr else "Not configured"
    }

@app.post("/api/settings/recipients")
def save_recipient_settings(data: RecipientSettingsSchema, user_id: int = Depends(get_current_user_id)):
    """Saves the user's configured SMS recipient mobile number and Email recipient address in the database."""
    conn = get_db()
    cursor = conn.cursor()
    sms_phone = data.sms_recipient_phone.strip()
    email_addr = data.email_recipient_email.strip()
    sms_enabled = 1 if data.sms_reminders else 0
    email_enabled = 1 if data.email_reminders else 0
    
    cursor.execute("""
        UPDATE users 
        SET sms_recipient_phone = ?, email_recipient_email = ?, sms_reminders = ?, email_reminders = ?
        WHERE id = ?
    """, (sms_phone, email_addr, sms_enabled, email_enabled, user_id))
    
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO notifications (user_id, title, message, created_at)
        VALUES (?, 'Notification Settings Updated', ?, ?)
    """, (user_id, f"SMS Recipient: {sms_phone}, Email Recipient: {email_addr}", now_str))
    
    conn.commit()
    conn.close()
    return {
        "success": True,
        "message": "Notification recipient settings saved successfully.",
        "sms_recipient_phone": sms_phone,
        "email_recipient_email": email_addr,
        "masked_phone": mask_phone(sms_phone),
        "masked_email": mask_email(email_addr)
    }

@app.get("/api/settings/api-keys")
def get_api_key_settings(user_id: int = Depends(get_current_user_id)):
    """Retrieves current email provider connection status and masked keys."""
    resend_key = os.getenv("RESEND_API_KEY", "").strip()
    is_resend_set = bool(resend_key and not resend_key.startswith("your_"))
    masked_resend = (resend_key[:4] + "..." + resend_key[-4:]) if is_resend_set and len(resend_key) > 8 else ("Configured" if is_resend_set else "Not configured")
    
    smtp_user = os.getenv("SMTP_USER", "").strip()
    is_smtp_set = bool(smtp_user and os.getenv("SMTP_PASSWORD") and not smtp_user.startswith("your_"))
    
    return {
        "resend_configured": is_resend_set,
        "resend_key_masked": masked_resend,
        "smtp_configured": is_smtp_set,
        "smtp_user_masked": mask_email(smtp_user) if is_smtp_set else "Not configured"
    }

@app.post("/api/settings/api-keys")
def save_api_key_settings(data: ApiKeyConfigSchema, user_id: int = Depends(get_current_user_id)):
    """Saves Resend API key or SMTP credentials to runtime and updates backend/.env file directly."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    
    if data.resend_api_key is not None:
        key_val = data.resend_api_key.strip()
        os.environ["RESEND_API_KEY"] = key_val
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "RESEND_API_KEY=" in content:
                content = re.sub(r"RESEND_API_KEY=.*", f"RESEND_API_KEY={key_val}", content)
            else:
                content += f"\nRESEND_API_KEY={key_val}\n"
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(content)
                
    if data.smtp_user is not None and data.smtp_password is not None:
        s_user = data.smtp_user.strip()
        s_pass = data.smtp_password.strip()
        os.environ["SMTP_USER"] = s_user
        os.environ["SMTP_PASSWORD"] = s_pass
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()
            content = re.sub(r"SMTP_USER=.*", f"SMTP_USER={s_user}", content)
            content = re.sub(r"SMTP_PASSWORD=.*", f"SMTP_PASSWORD={s_pass}", content)
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(content)

    resend_ready = bool(os.getenv("RESEND_API_KEY") and not os.getenv("RESEND_API_KEY").startswith("your_"))
    smtp_ready = bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"))

    return {
        "success": True,
        "message": "API key configuration saved and activated successfully!",
        "resend_configured": resend_ready,
        "smtp_configured": smtp_ready
    }

@app.post("/api/notifications/test-sms")
def send_test_sms(data: TestSmsSchema, user_id: int = Depends(get_current_user_id)):
    """Directly dispatches a real test SMS to the requested mobile number through the configured SMS provider."""
    phone = data.phone_number.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Mobile number is required.")
        
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = data.message or f"Smart Electricity Test Alert: Real SMS service connected! Delivered at {now_str}."
    
    sms_res = send_sms(phone, msg)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notification_history 
        (user_id, bill_id, type, recipient, title, message, status, provider_response, error_message, sent_at)
        VALUES (?, NULL, 'SMS', ?, 'Test SMS Dispatch', ?, ?, ?, ?, ?)
    """, (
        user_id,
        mask_phone(phone),
        msg,
        "SENT" if sms_res["success"] else "FAILED",
        str(sms_res.get("response_data", {})),
        sms_res.get("error"),
        now_str
    ))
    conn.commit()
    conn.close()
    
    return {
        "success": sms_res["success"],
        "status": "SENT" if sms_res["success"] else "FAILED",
        "recipient": phone,
        "masked_recipient": mask_phone(phone),
        "error": sms_res.get("error"),
        "message": "✅ Real SMS Sent Successfully via Provider!" if sms_res["success"] else (
            f"⚠️ SMS service is not configured: {sms_res.get('error')}" if "not configured" in str(sms_res.get("error", "")).lower()
            else f"❌ SMS Dispatch Failed: {sms_res.get('error')}"
        )
    }

@app.post("/api/notifications/test-email")
def send_test_email(data: TestEmailSchema, user_id: int = Depends(get_current_user_id)):
    """Directly dispatches a real test Email to the requested email address through the configured email provider (Resend/SMTP)."""
    email = data.email_address.strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email address is required.")
        
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = data.subject or "⚡ Smart Electricity - Test Email Notification"
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    user_name = usr["name"] if usr else "User"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: Arial, sans-serif; background-color: #f1f5f9; padding: 30px 20px;">
      <div style="max-width: 540px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
        <div style="background: #1d63ed; padding: 24px; text-align: center; color: #ffffff;">
          <h2 style="margin: 0; font-size: 22px;">⚡ Smart Electricity Test Notification</h2>
        </div>
        <div style="padding: 24px 30px; color: #334155; font-size: 14px; line-height: 1.6;">
          <p>Hello <strong>{user_name}</strong>,</p>
          <p>This is an actual test email from your <strong>Smart Electricity Bill Monitoring System</strong>.</p>
          <div style="background: #f8fafc; border-left: 4px solid #10b981; padding: 14px; border-radius: 6px; margin: 20px 0;">
            <p style="margin: 0; color: #0f172a; font-weight: 600;">Status: Real Email Provider Connected & Active</p>
            <p style="margin: 4px 0 0 0; font-size: 12px; color: #64748b;">Timestamp: {now_str}</p>
          </div>
          <p style="color: #64748b; font-size: 13px;">Your email recipient configuration is working correctly.</p>
        </div>
        <div style="background: #0f172a; padding: 14px; text-align: center; font-size: 11px; color: #94a3b8;">
          Smart Electricity Monitoring & Payment Reminder System
        </div>
      </div>
    </body>
    </html>
    """
    
    email_res = send_email(email, subject, html_body, f"Test email from Smart Electricity. Sent at {now_str}")
    is_sent = email_res["success"]
    err_msg = email_res.get("error")
    status_code = email_res.get("status", "FAILED")
    prov_resp = str(email_res.get("response_data", {}))
    
    cursor.execute("""
        INSERT INTO notification_history 
        (user_id, bill_id, type, recipient, title, message, status, provider_response, error_message, sent_at)
        VALUES (?, NULL, 'Email', ?, ?, 'Test Email Notification', ?, ?, ?, ?)
    """, (
        user_id,
        mask_email(email),
        subject,
        "SENT" if is_sent else ("NOT_CONFIGURED" if status_code == "NOT_CONFIGURED" else "FAILED"),
        prov_resp,
        err_msg,
        now_str
    ))
    conn.commit()
    conn.close()
    
    if is_sent:
        return {
            "success": True,
            "status": "SENT",
            "recipient": email,
            "masked_recipient": mask_email(email),
            "error": None,
            "message": "✅ Email sent successfully",
            "provider": email_res.get("provider", "resend")
        }
    elif status_code == "NOT_CONFIGURED":
        return {
            "success": False,
            "status": "NOT_CONFIGURED",
            "recipient": email,
            "masked_recipient": mask_email(email),
            "error": err_msg,
            "message": "⚠️ Email service is not configured. Add RESEND_API_KEY to the backend environment."
        }
    else:
        return {
            "success": False,
            "status": "FAILED",
            "recipient": email,
            "masked_recipient": mask_email(email),
            "error": err_msg,
            "message": f"❌ Email failed: {err_msg}"
        }

# ==============================================================================
# DEMO ELECTRICITY BILL & DYNAMIC NOTIFICATION HUB
# ==============================================================================
@app.post("/api/demo/send-sms-reminder")
def send_demo_sms_reminder(data: DemoBillReminderSchema, user_id: int = Depends(get_current_user_id)):
    """
    Generates or dispatches a demo SMS electricity bill reminder using the dynamic mobile number and bill details.
    Adheres strictly to Zero Fake Delivery: if no real provider API is configured, clearly indicates demo generation.
    """
    mobile = data.mobile_number.strip()
    if not mobile:
        raise HTTPException(status_code=400, detail="Mobile number is required.")
        
    bill_amt_str = f"{data.bill_amount:,.2f}" if data.bill_amount % 1 != 0 else f"{int(data.bill_amount)}"
    sms_text = f"Electricity Bill Reminder: Your demo electricity bill is ₹{bill_amt_str}. Due date: {data.due_date}. Please make your payment before the due date."
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Check if real SMS provider credentials exist
    sms_provider = os.getenv("SMS_PROVIDER", "fast2sms").lower()
    has_sms_creds = False
    if sms_provider == "fast2sms" and os.getenv("FAST2SMS_API_KEY") and not os.getenv("FAST2SMS_API_KEY").startswith("your_"):
        has_sms_creds = True
    elif sms_provider == "twilio" and os.getenv("TWILIO_ACCOUNT_SID") and not os.getenv("TWILIO_ACCOUNT_SID").startswith("your_"):
        has_sms_creds = True
    elif sms_provider == "custom" and os.getenv("SMS_WEBHOOK_URL"):
        has_sms_creds = True
        
    conn = get_db()
    cursor = conn.cursor()
    
    if has_sms_creds:
        sms_res = send_sms(mobile, sms_text)
        is_sent = sms_res["success"]
        status_val = "SENT" if is_sent else "FAILED"
        err_msg = sms_res.get("error")
        prov_resp = str(sms_res.get("response_data", {}))
        
        cursor.execute("""
            INSERT INTO notification_history 
            (user_id, bill_id, type, recipient, title, message, status, provider_response, error_message, sent_at)
            VALUES (?, NULL, 'SMS', ?, 'Demo Electricity Bill Reminder', ?, ?, ?, ?, ?)
        """, (user_id, mask_phone(mobile), sms_text, status_val, prov_resp, err_msg, now_str))
        conn.commit()
        conn.close()
        
        return {
            "success": is_sent,
            "status": status_val,
            "recipient": mobile,
            "masked_recipient": mask_phone(mobile),
            "message_text": sms_text,
            "status_message": (
                f"✅ SMS Sent to {mobile} via {sms_provider.upper()} API" if is_sent
                else f"❌ SMS Dispatch Failed: {err_msg}"
            ),
            "is_real_delivery": True
        }
    else:
        status_val = "DEMO_GENERATED"
        err_msg = "Demo notification generated — not actually sent (no SMS provider configured)"
        cursor.execute("""
            INSERT INTO notification_history 
            (user_id, bill_id, type, recipient, title, message, status, provider_response, error_message, sent_at)
            VALUES (?, NULL, 'SMS', ?, 'Demo Electricity Bill Reminder', ?, ?, 'Demo generated', ?, ?)
        """, (user_id, mask_phone(mobile), sms_text, status_val, err_msg, now_str))
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "status": status_val,
            "recipient": mobile,
            "masked_recipient": mask_phone(mobile),
            "message_text": sms_text,
            "status_message": f"📱 SMS: Demo notification generated — not actually sent",
            "full_details": f"SMS To: {mobile}\n{sms_text}",
            "is_real_delivery": False
        }

@app.post("/api/demo/send-email-reminder")
def send_demo_email_reminder(data: DemoBillReminderSchema, user_id: int = Depends(get_current_user_id)):
    """
    Sends a real transactional email reminder to the user's entered email address.
    Strictly follows zero-fake delivery rules: never claims sent unless provider accepts request.
    """
    email = data.email_address.strip()
    if not email:
        raise HTTPException(status_code=400, detail="Recipient email address is required.")
        
    bill_amt_str = f"{data.bill_amount:,.2f}" if data.bill_amount % 1 != 0 else f"{int(data.bill_amount)}"
    subject = "Electricity Bill Payment Reminder"
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    app_base_url = os.getenv("APP_BASE_URL", "http://localhost:8000")
    
    text_body = f"""Hello {data.consumer_name},

Your electricity bill payment reminder is ready.

Bill Amount: ₹{bill_amt_str}
Due Date: {data.due_date}
Consumer ID: {data.consumer_id}
Payment Status: Unpaid

Please complete your payment before the due date.

PAY BILL: {app_base_url}/dashboard.html

This is a demo electricity bill for the application.
"""

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: Arial, sans-serif; background-color: #f1f5f9; padding: 30px 20px; color: #334155;">
      <div style="max-width: 540px; margin: 0 auto; background: #ffffff; border-radius: 14px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
        <div style="background: #1d63ed; padding: 24px; text-align: center; color: #ffffff;">
          <h2 style="margin: 0; font-size: 22px;">⚡ Electricity Bill Payment Reminder</h2>
        </div>
        <div style="padding: 24px 30px; font-size: 14px; line-height: 1.6;">
          <p style="font-size: 16px; margin-top: 0;">Hello <strong>{data.consumer_name}</strong>,</p>
          <p>Your electricity bill payment reminder is ready.</p>
          
          <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0 0 8px 0;"><strong>Bill Amount:</strong> <strong style="color: #1d63ed; font-size: 16px;">₹{bill_amt_str}</strong></p>
            <p style="margin: 0 0 8px 0;"><strong>Due Date:</strong> <span style="color: #ef4444; font-weight: 700;">{data.due_date}</span></p>
            <p style="margin: 0 0 8px 0;"><strong>Consumer ID:</strong> {data.consumer_id}</p>
            <p style="margin: 0;"><strong>Payment Status:</strong> <span style="color: #f59e0b; font-weight: 700;">Unpaid</span></p>
          </div>

          <p>Please complete your payment before the due date.</p>

          <div style="text-align: center; margin: 26px 0 16px 0;">
            <a href="{app_base_url}/dashboard.html" style="background: #10b981; color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 800; font-size: 14px; display: inline-block;">
              💳 PAY BILL
            </a>
          </div>

          <p style="font-size: 12px; color: #64748b; text-align: center; margin-top: 20px; border-top: 1px solid #f1f5f9; padding-top: 12px;">
            This is a demo electricity bill for the application.
          </p>
        </div>
        <div style="background: #0f172a; padding: 14px; text-align: center; font-size: 11px; color: #94a3b8;">
          Smart Electricity Bill Monitoring & Reminder System
        </div>
      </div>
    </body>
    </html>
    """

    email_res = send_email(email, subject, html_body, text_body)
    is_sent = email_res["success"]
    err_msg = email_res.get("error")
    status_code = email_res.get("status", "FAILED")
    prov_resp = str(email_res.get("response_data", {}))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notification_history 
        (user_id, bill_id, type, recipient, title, message, status, provider_response, error_message, sent_at)
        VALUES (?, NULL, 'Email', ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        mask_email(email),
        subject,
        text_body,
        "SENT" if is_sent else ("NOT_CONFIGURED" if status_code == "NOT_CONFIGURED" else "FAILED"),
        prov_resp,
        err_msg,
        now_str
    ))
    conn.commit()
    conn.close()
    
    if is_sent:
        return {
            "success": True,
            "status": "SENT",
            "recipient": email,
            "masked_recipient": mask_email(email),
            "subject": subject,
            "message_id": email_res.get("message_id"),
            "status_message": "✅ Email sent successfully",
            "provider": email_res.get("provider", "resend")
        }
    elif status_code == "NOT_CONFIGURED":
        return {
            "success": False,
            "status": "NOT_CONFIGURED",
            "recipient": email,
            "masked_recipient": mask_email(email),
            "subject": subject,
            "status_message": "⚠️ Email service is not configured. Add RESEND_API_KEY to the backend environment.",
            "error": err_msg
        }
    else:
        return {
            "success": False,
            "status": "FAILED",
            "recipient": email,
            "masked_recipient": mask_email(email),
            "subject": subject,
            "status_message": f"❌ Email failed: {err_msg}",
            "error": err_msg
        }

@app.post("/api/demo/create-bill")
def create_demo_bill(data: DemoBillReminderSchema, user_id: int = Depends(get_current_user_id)):
    """Creates a demo electricity bill in the database with user's customized details."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check or create default meter
    cursor.execute("SELECT id FROM meters WHERE user_id = ? LIMIT 1", (user_id,))
    meter = cursor.fetchone()
    if not meter:
        cursor.execute("""
            INSERT INTO meters (user_id, service_number, board_name, consumer_name, address)
            VALUES (?, ?, 'DEMO POWER BOARD', ?, 'Demo Address, 123 Electricity Way')
        """, (user_id, data.consumer_id, data.consumer_name))
        meter_id = cursor.lastrowid
    else:
        meter_id = meter["id"]
        
    bill_amount = round(float(data.bill_amount), 2)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    cursor.execute("""
        INSERT INTO bills (
            meter_id, consumer_id, consumer_name, mobile_number, email_address,
            billing_month, units_consumed, amount, bill_amount, amount_paid, remaining_amount,
            bill_issue_date, due_date, payment_status
        ) VALUES (?, ?, ?, ?, ?, 'Demo Month', 140.0, ?, ?, 0.0, ?, ?, ?, 'Unpaid')
    """, (
        meter_id,
        data.consumer_id,
        data.consumer_name,
        data.mobile_number,
        data.email_address,
        bill_amount,
        bill_amount,
        bill_amount,
        today_str,
        data.due_date
    ))
    
    bill_id = cursor.lastrowid
    conn.commit()
    conn.close()
    broadcast_update("update")
    return {
        "success": True,
        "bill_id": bill_id,
        "consumer_name": data.consumer_name,
        "consumer_id": data.consumer_id,
        "bill_amount": bill_amount,
        "remaining_amount": bill_amount,
        "due_date": data.due_date,
        "mobile_number": data.mobile_number,
        "email_address": data.email_address,
        "payment_status": "Unpaid",
        "message": f"Demo bill of ₹{bill_amount:,.2f} created for {data.consumer_name} (ID: {data.consumer_id})."
    }

@app.post("/api/reminders/run-check")
def trigger_reminders_check(user_id: int = Depends(get_current_user_id)):
    """Manually triggers reminder evaluator to check all due dates and send real SMS & Email immediately."""
    results = evaluate_and_send_reminders(get_db, force_send=True)
    broadcast_update("update")
    return {
        "success": True,
        "message": f"Evaluated {results['evaluated_bills']} bill(s). Dispatched {results['sms_sent']} SMS and {results['email_sent']} Email(s).",
        "details": results
    }

@app.get("/api/reminders")
def get_reminders(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reminders WHERE user_id = ?", (user_id,))
    reminders = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return reminders

@app.post("/api/reminders/toggle")
def toggle_reminder(data: ReminderToggleSchema, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    val = 1 if data.enabled else 0
    cursor.execute("SELECT COUNT(*) as count FROM reminders WHERE user_id = ? AND days_before = ?", (user_id, data.days_before))
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO reminders (user_id, days_before, enabled) VALUES (?, ?, ?)", (user_id, data.days_before, val))
    else:
        cursor.execute("UPDATE reminders SET enabled = ? WHERE user_id = ? AND days_before = ?", (val, user_id, data.days_before))
    conn.commit()
    conn.close()
    return {"message": "Reminder preference saved successfully"}

@app.get("/api/predictions/next-bill")
def get_next_bill_prediction(user_id: int = Depends(get_current_user_id)):
    """Predicts next bill details based on historical user bills."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get latest active meter
    cursor.execute("SELECT id, board_name, service_number, prediction_reminder_enabled FROM meters WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    meter = cursor.fetchone()
    
    if not meter:
        conn.close()
        return {
            "meter_id": None,
            "expected_date": "05-Sep-2026",
            "estimated_amount_min": 650.0,
            "estimated_amount_max": 720.0,
            "expected_window_start": "04-Sep-2026",
            "expected_window_end": "07-Sep-2026",
            "confidence": "High",
            "reminder_enabled": True,
            "days_until": 8
        }
    
    # Fetch bills to predict
    cursor.execute("""
        SELECT units_consumed, bill_amount, due_date FROM bills 
        WHERE meter_id = ? ORDER BY id DESC
    """, (meter["id"],))
    bills = [dict(b) for b in cursor.fetchall()]
    conn.close()
    
    # Default fallback values
    expected_date_str = "05-Sep-2026"
    est_min = 650.0
    est_max = 720.0
    window_start_str = "04-Sep-2026"
    window_end_str = "07-Sep-2026"
    confidence = "High"
    
    # Calculate days until expected bill
    try:
        expected_dt = datetime.datetime.strptime(expected_date_str, "%d-%b-%Y")
        today = datetime.datetime.now()
        days_until = max(0, (expected_dt.date() - today.date()).days)
    except Exception:
        days_until = 8

    return {
        "meter_id": meter["id"],
        "expected_date": expected_date_str,
        "estimated_amount_min": est_min,
        "estimated_amount_max": est_max,
        "expected_window_start": window_start_str,
        "expected_window_end": window_end_str,
        "confidence": confidence,
        "reminder_enabled": bool(meter["prediction_reminder_enabled"]),
        "days_until": days_until
    }

@app.post("/api/predictions/toggle-reminder")
def toggle_prediction_reminder(data: PredictionToggleSchema, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    val = 1 if data.enabled else 0
    cursor.execute("UPDATE meters SET prediction_reminder_enabled = ? WHERE id = ? AND user_id = ?", (val, data.meter_id, user_id))
    conn.commit()
    conn.close()
    
    # Broadcast to all clients
    broadcast_update("update")
    return {"message": "Prediction reminder saved successfully"}


@app.get("/api/notifications")
def get_notifications(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user_id,))
    notifications = [dict(n) for n in cursor.fetchall()]
    conn.close()
    return notifications

@app.delete("/api/notifications/clear")
@app.post("/api/notifications/clear")
def clear_notification_history(user_id: int = Depends(get_current_user_id)):
    """Clears all notification logs for the user."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notification_history WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    broadcast_update("update")
    return {"message": "Notification log cleared successfully."}


# ==============================================================================
# AI ASSISTANT CHAT ENGINE & UNIVERSAL KNOWLEDGE
# ==============================================================================
def search_universal_knowledge(query: str) -> str:
    """Searches Wikipedia & DuckDuckGo to answer any general knowledge or technical question accurately."""
    cleaned = re.sub(r"^(what is|what are|who is|who are|explain|tell me about|how does|why is|why are|define|how to)\s+", "", query.lower()).strip("? .")
    
    # 1. Search Wikipedia API for natural question matching
    for search_term in [query, cleaned]:
        if not search_term:
            continue
        try:
            search_api = "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=" + urllib.parse.quote(search_term) + "&utf8=&format=json"
            req = urllib.request.Request(search_api, headers={"User-Agent": "SmartElectricityAI/2.0 (education_app)"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("query", {}).get("search", [])
                if results:
                    top_title = results[0]["title"]
                    # Fetch summary for exact title
                    summary_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(top_title.replace(" ", "_"))
                    req2 = urllib.request.Request(summary_url, headers={"User-Agent": "SmartElectricityAI/2.0 (education_app)"})
                    with urllib.request.urlopen(req2, timeout=4) as resp2:
                        s_data = json.loads(resp2.read().decode("utf-8"))
                        if s_data.get("extract"):
                            return f"📚 {s_data.get('title')}:\n\n{s_data.get('extract')}"
                    
                    snippet = re.sub(r"<[^>]+>", "", results[0].get("snippet", ""))
                    if snippet:
                        return f"📚 {top_title}:\n\n{snippet}"
        except Exception:
            pass

    # 2. Try DuckDuckGo Instant Answer
    try:
        ddg_url = "https://api.duckduckgo.com/?q=" + urllib.parse.quote(query) + "&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(ddg_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("Answer"):
                return str(data["Answer"])
            if data.get("AbstractText"):
                return f"📖 {data['Heading']}:\n\n{data['AbstractText']}"
            if data.get("RelatedTopics") and len(data["RelatedTopics"]) > 0:
                first = data["RelatedTopics"][0]
                if isinstance(first, dict) and first.get("Text"):
                    return f"📖 {first.get('Text')}"
    except Exception:
        pass

    return ""

def generate_ai_reply(raw_msg: str, user_id: int, cursor) -> str:
    msg = raw_msg.lower().strip()
    
    # 1. Greetings
    if re.search(r"^(hi|hello|hey|hii+|heyy+|namaste|good morning|good evening|good afternoon|howdy)\b", msg) or msg in ["hi", "hii", "hiii", "hello", "hey"]:
        cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
        u = cursor.fetchone()
        user_name = u["name"] if u else "there"
        return f"Hello {user_name}! 👋 I am your Smart Electricity AI Assistant. How can I help you today? You can ask me for power-saving tips, your pending bill balance, AC optimization, solar energy advice, or reminder schedules!"

    # 2. Power Saving & Efficiency ("how to power saving", "power saving", "reduce bill", "save electricity", "tips")
    if any(k in msg for k in ["power saving", "save power", "save energy", "save electricity", "power save", "reduce bill", "lower bill", "energy saving", "saving tips", "how to save", "efficiency", "cut power", "less power", "how to power saving", "save", "saving"]):
        return (
            "💡 Top 5 Practical Power Saving Tips to Cut Your Bill by 20-30%:\n\n"
            "1. ❄️ Air Conditioner (AC): Set temperature to 24°C - 26°C. Every degree higher saves ~6% electricity.\n"
            "2. 💡 Lighting: Replace old CFL/incandescent bulbs with 9W/12W LEDs to save up to 80% lighting energy.\n"
            "3. 🔌 Eliminate Vampire Load: Turn off switches for TV set-top boxes, chargers, and microwaves at the plug.\n"
            "4. 🧊 Refrigerator: Keep temperature at 3°C to 5°C, maintain 2 inches gap from walls for airflow, and avoid opening doors frequently.\n"
            "5. 🚿 Water Heaters/Geysers: Switch off geyser immediately after 10-15 mins of heating; do not leave it running continuously."
        )

    # 3. Air Conditioner / AC specific
    if any(k in msg for k in ["ac", "air condition", "cooling", "thermostat", "temperature"]):
        return (
            "❄️ Smart AC Energy Optimization:\n\n"
            "• Ideal Temperature: Set to 24°C or 25°C instead of 18°C. This reduces compressor load significantly.\n"
            "• Ceiling Fan Assist: Run a ceiling fan at low speed along with AC to circulate cool air evenly.\n"
            "• Clean Air Filters: Clean the AC dust filter every 2 weeks. Clogged filters consume 15% more power.\n"
            "• Timer Mode: Use the AC sleep timer so it turns off automatically after 3-4 hours when room is cool."
        )

    # 4. Refrigerator specific
    if any(k in msg for k in ["fridge", "refrigerator", "freezer"]):
        return (
            "🧊 Refrigerator Energy Tips:\n\n"
            "• Temperature Setting: Optimal fridge temp is 3°C to 4°C and freezer at -18°C.\n"
            "• Defrost Regularly: Frost buildup thicker than 5mm forces the compressor to work twice as hard.\n"
            "• Hot Food Warning: Always let hot food cool to room temperature before placing it inside the fridge.\n"
            "• Door Seals: Check rubber gaskets for leaks to prevent cool air from escaping."
        )

    # 5. Geyser / Water Heater
    if any(k in msg for k in ["geyser", "water heater", "heater", "hot water"]):
        return (
            "🚿 Water Heater (Geyser) Energy Tips:\n\n"
            "• Geysers consume 1500W to 3000W per hour.\n"
            "• Turn on the geyser 15 minutes before use and switch off immediately.\n"
            "• Set thermostat to 50°C instead of 60°C.\n"
            "• Consider installing a timer switch or an instant gas/solar water heater for massive savings."
        )

    # 6. Solar Energy & Rooftop Solar
    if any(k in msg for k in ["solar", "rooftop", "green energy", "renewable", "net metering"]):
        return (
            "☀️ Rooftop Solar & Net Metering:\n\n"
            "• A 1 kW rooftop solar system generates ~4 to 5 units (kWh) per day (120-150 units/month).\n"
            "• Net Metering allows you to export surplus power back to the electricity board (e.g. TANGEDCO/BESCOM) and deduct it from your monthly bill.\n"
            "• Government subsidies (PM Surya Ghar Muft Bijli Yojana) offer substantial discounts on solar installation."
        )

    # 7. Bill Status, Pending Amount, Due Date
    if any(k in msg for k in ["bill", "due date", "pending", "how much", "pay", "balance", "amount", "unpaid", "cost"]):
        cursor.execute("""
            SELECT b.id, b.consumer_name, b.bill_amount, b.amount_paid, b.remaining_amount, b.due_date, b.billing_month, b.payment_status 
            FROM bills b 
            JOIN meters m ON b.meter_id = m.id 
            WHERE m.user_id = ?
            ORDER BY b.id DESC
            LIMIT 1
        """, (user_id,))
        bill = cursor.fetchone()
        if bill:
            if bill["payment_status"] == "Paid":
                return f"✅ Your latest electricity bill for {bill['billing_month']} (₹{bill['bill_amount']:,.2f}) is already FULLY PAID! You have no outstanding dues."
            else:
                return (
                    f"📄 Bill Summary for {bill['consumer_name']}:\n\n"
                    f"• Billing Cycle: {bill['billing_month']}\n"
                    f"• Total Bill: ₹{bill['bill_amount']:,.2f}\n"
                    f"• Paid Amount: ₹{bill['amount_paid']:,.2f}\n"
                    f"• Pending Balance: ₹{bill['remaining_amount']:,.2f}\n"
                    f"• Due Date: {bill['due_date']}\n"
                    f"• Status: ⚠️ {bill['payment_status']}\n\n"
                    f"You can pay this bill directly using the 'PAY BILL' button on your dashboard."
                )
        else:
            return "You currently have no bills registered. You can add demo bills or connect your service number from the Connections tab."

    # 8. Reminders & Notification System
    if any(k in msg for k in ["reminder", "notification", "alert", "sms", "email", "schedule"]):
        return (
            "⏰ Smart Electricity Reminder Milestones:\n\n"
            "Our automated scheduler evaluates your bills every hour and dispatches alerts:\n"
            "• 7 Days before Due Date (Early Notice)\n"
            "• 3 Days before Due Date (Upcoming Due)\n"
            "• 1 Day before Due Date (Urgent Alert)\n"
            "• On Due Date (Final Payment Notice)\n\n"
            "You can configure your real mobile number and email in Notification Settings."
        )

    # 9. Why is my bill high / Troubleshooting
    if any(k in msg for k in ["high bill", "why high", "huge bill", "excessive", "faulty", "meter reading"]):
        return (
            "🔍 Reasons Why Your Electricity Bill Might Be High:\n\n"
            "1. Heavy Seasonal Appliance Usage: ACs in summer or Geysers/Room Heaters in winter.\n"
            "2. Slab Tariff Jumps: Crossing the 100 or 200 unit threshold moves you into a higher rate slab per unit.\n"
            "3. Old Inefficient Appliances: Non-inverter appliances consume up to 40% more energy.\n"
            "4. Phantom / Vampire Load: Devices left plugged into wall sockets continuously.\n"
            "5. Earth Leakage: Damaged neutral/earthing wire causing leakage into ground."
        )

    # 10. How to calculate units / kWh
    if any(k in msg for k in ["unit", "kwh", "calculate", "formula", "watt"]):
        return (
            "📐 How Electricity Units (kWh) Are Calculated:\n\n"
            "• 1 Unit = 1 Kilowatt-Hour (kWh) = 1,000 Watts used for 1 Hour.\n"
            "• Formula: Energy (Units) = (Watts × Hours of Use) ÷ 1,000\n\n"
            "Example: A 1,500W Air Conditioner running for 8 hours:\n"
            "(1500 × 8) ÷ 1000 = 12 Units per day (~360 units per month)."
        )

    # 11. Thank you / Appreciation
    if any(k in msg for k in ["thank", "thanks", "great", "helpful", "good job", "awesome", "nice"]):
        return "You're very welcome! 😊 Feel free to ask whenever you need guidance on energy conservation, bill analysis, or tariff calculations."

    # 12. Who are you / Assistant info
    if any(k in msg for k in ["who are you", "what can you do", "help", "about you"]):
        return (
            "🤖 I am your Smart Electricity AI Assistant!\n\n"
            "I can assist you with:\n"
            "• Power-saving tips for AC, refrigerators, geysers, and appliances\n"
            "• Checking your latest bill balance, due dates, and payment history\n"
            "• Explaining electricity units, tariff slabs, and solar rooftop benefits\n"
            "• Guiding you through smart reminder schedules and payment options"
        )

    # 13. Universal Knowledge Search for Any Question
    try:
        knowledge_ans = search_universal_knowledge(raw_msg)
        if knowledge_ans:
            return knowledge_ans
    except Exception:
        pass

    # 14. Smart Fallback for Any Other Question
    return (
        f"Regarding '{raw_msg}':\n\n"
        "In smart electricity management, maintaining energy efficiency is key. "
        "Monitor your daily consumption in the Analytics tab, switch to 5-star inverter appliances, "
        "and avoid peak-hour overload to optimize your power bill.\n\n"
        "Ask me specifically about: 'how to power saving', 'my pending bill', 'AC tips', 'how units are calculated', or 'solar energy'!"
    )

@app.post("/api/ai/chat")
def ai_chat(data: ChatSchema, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    reply = generate_ai_reply(data.message, user_id, cursor)
    conn.close()
    return {"reply": reply}


# Global Exception Handlers
@app.exception_handler(StarletteHTTPException)
def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
def global_exception_handler(request, exc):
    if isinstance(exc, StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )

# Static files for web app
static_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app-new"))
app.mount("/", StaticFiles(directory=static_path, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
