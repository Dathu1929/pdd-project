import os
import sqlite3
import datetime
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel
from jose import jwt, JWTError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

JWT_SECRET = "your-high-security-rotation-secret-key"
ALGORITHM = "HS256"

app = FastAPI(title="Smart Electricity Bill System API")

origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.github\.io",
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT"],
    allow_headers=["*"],
)

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
    conn = get_db()
    cursor = conn.cursor()
    
    # Tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        phone TEXT,
        alternate_phone TEXT
    )""")
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN alternate_phone TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    for col in ["sms_reminders", "email_reminders", "whatsapp_reminders", "phone_reminders"]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 1")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS meters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        service_number TEXT UNIQUE NOT NULL,
        board_name TEXT NOT NULL,
        consumer_name TEXT NOT NULL,
        address TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meter_id INTEGER NOT NULL,
        billing_month TEXT NOT NULL,
        units_consumed REAL NOT NULL,
        amount REAL NOT NULL,
        due_date TEXT NOT NULL,
        payment_status TEXT DEFAULT 'Unpaid',
        FOREIGN KEY(meter_id) REFERENCES meters(id)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        payment_method TEXT NOT NULL,
        transaction_ref TEXT NOT NULL,
        paid_at TEXT NOT NULL,
        FOREIGN KEY(bill_id) REFERENCES bills(id)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        days_before INTEGER NOT NULL,
        enabled INTEGER DEFAULT 1,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    
    conn.commit()

    # Seed initial test data if empty
    cursor.execute("SELECT COUNT(*) as count FROM users")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO users (name, email, password, phone) VALUES (?, ?, ?, ?)",
                       ("Dattu", "dattu@gmail.com", "dattu123", "+919876543210"))
        user_id = cursor.lastrowid
        
        cursor.execute("INSERT INTO meters (user_id, service_number, board_name, consumer_name, address) VALUES (?, ?, ?, ?, ?)",
                       (user_id, "EB/321232345600/12", "Tamil Nadu Generation and Distribution Corporation (TANGEDCO)", "Dattu", "12, Gandhi Road, Chennai"))
        meter_id = cursor.lastrowid
        
        # Add bills
        cursor.execute("INSERT INTO bills (meter_id, billing_month, units_consumed, amount, due_date, payment_status) VALUES (?, ?, ?, ?, ?, ?)",
                       (meter_id, "August 2026", 250.0, 1402.00, "2026-08-25", "Unpaid"))
        cursor.execute("INSERT INTO bills (meter_id, billing_month, units_consumed, amount, due_date, payment_status) VALUES (?, ?, ?, ?, ?, ?)",
                       (meter_id, "July 2026", 240.0, 1285.00, "2026-07-25", "Paid"))
        
        # Add reminders
        cursor.execute("INSERT INTO reminders (user_id, days_before, enabled) VALUES (?, ?, ?)", (user_id, 7, 1))
        cursor.execute("INSERT INTO reminders (user_id, days_before, enabled) VALUES (?, ?, ?)", (user_id, 3, 1))
        cursor.execute("INSERT INTO reminders (user_id, days_before, enabled) VALUES (?, ?, ?)", (user_id, 1, 1))

        # Add notifications
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        cursor.execute("INSERT INTO notifications (user_id, title, message, created_at) VALUES (?, ?, ?, ?)",
                       (user_id, "Bill Generated", "Your bill for Aug 2026 has been generated.", now))
        
        conn.commit()
    conn.close()

# Pydantic Schemas
class ReminderChannelsSchema(BaseModel):
    sms_reminders: bool
    email_reminders: bool
    whatsapp_reminders: bool
    phone_reminders: bool

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

class PaymentSchema(BaseModel):
    bill_id: int
    amount: float
    payment_method: str

class ReminderToggleSchema(BaseModel):
    days_before: int
    enabled: bool

class ChatSchema(BaseModel):
    message: str

def create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)

# Helper to verify tokens
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

@app.post("/api/auth/register")
def register(data: RegisterSchema):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (name, email, password, phone, alternate_phone) VALUES (?, ?, ?, ?, ?)",
                       (data.name, data.email, data.password, data.phone, data.alternate_phone))
        conn.commit()
        user_id = cursor.lastrowid
        token = create_access_token(user_id)
        return {"token": token, "user": {"id": user_id, "name": data.name, "email": data.email}}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    finally:
        conn.close()

@app.post("/api/auth/login")
def login(data: LoginSchema):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE (email = ? OR phone = ?) AND password = ?", (data.email, data.email, data.password))
    user = cursor.fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email/mobile or password")
    token = create_access_token(user["id"])
    return {"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"], "phone": user["phone"], "alternate_phone": user["alternate_phone"]}}

@app.get("/api/users/profile")
def get_profile(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, phone, alternate_phone FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user)

@app.post("/api/users/profile")
def update_profile(data: RegisterSchema, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET name = ?, email = ?, password = ?, phone = ?, alternate_phone = ? WHERE id = ?",
                   (data.name, data.email, data.password, data.phone, data.alternate_phone, user_id))
    conn.commit()
    conn.close()
    return {"message": "Profile updated successfully"}

@app.get("/api/meters")
def get_meters(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM meters WHERE user_id = ?", (user_id,))
    meters = [dict(m) for m in cursor.fetchall()]
    conn.close()
    return meters

@app.post("/api/meters")
def add_meter(data: MeterSchema, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO meters (user_id, service_number, board_name, consumer_name, address) VALUES (?, ?, ?, ?, ?)",
                       (user_id, data.service_number, data.board_name, data.consumer_name, data.address))
        conn.commit()
        meter_id = cursor.lastrowid
        # Automatically generate a mock unpaid bill for new meters
        due = (datetime.date.today() + datetime.timedelta(days=15)).strftime("%Y-%m-%d")
        cursor.execute("INSERT INTO bills (meter_id, billing_month, units_consumed, amount, due_date, payment_status) VALUES (?, ?, ?, ?, ?, ?)",
                       (meter_id, "September 2026", 180.0, 950.00, due, "Unpaid"))
        conn.commit()
        return {"id": meter_id, "message": "Connection added successfully"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Service number already registered")
    finally:
        conn.close()

@app.delete("/api/meters/{meter_id}")
def delete_meter(meter_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Verify owner of the meter before modifying any database tables
    cursor.execute("SELECT id FROM meters WHERE id = ? AND user_id = ?", (meter_id, user_id))
    meter = cursor.fetchone()
    if not meter:
        conn.close()
        raise HTTPException(status_code=403, detail="Not authorized to modify this connection")
        
    cursor.execute("DELETE FROM bills WHERE meter_id = ?", (meter_id,))
    cursor.execute("DELETE FROM meters WHERE id = ?", (meter_id,))
    conn.commit()
    conn.close()
    return {"message": "Connection deleted successfully"}

@app.get("/api/bills")
def get_bills(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, m.service_number, m.board_name, m.consumer_name 
        FROM bills b 
        JOIN meters m ON b.meter_id = m.id 
        WHERE m.user_id = ?
        ORDER BY b.due_date DESC
    """, (user_id,))
    bills = [dict(b) for b in cursor.fetchall()]
    conn.close()
    return bills

@app.post("/api/payments")
def make_payment(data: PaymentSchema, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    # Check if bill exists and belongs to the user
    cursor.execute("""
        SELECT b.* FROM bills b 
        JOIN meters m ON b.meter_id = m.id 
        WHERE b.id = ? AND m.user_id = ?
    """, (data.bill_id, user_id))
    bill = cursor.fetchone()
    if not bill:
        conn.close()
        raise HTTPException(status_code=404, detail="Bill not found")
        
    tx_ref = f"TXN-{int(datetime.datetime.now().timestamp())}"
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Record payment
    cursor.execute("INSERT INTO payments (bill_id, amount, payment_method, transaction_ref, paid_at) VALUES (?, ?, ?, ?, ?)",
                   (data.bill_id, data.amount, data.payment_method, tx_ref, now))
    # Update bill status
    cursor.execute("UPDATE bills SET payment_status = 'Paid' WHERE id = ?", (data.bill_id,))
    
    # Add success notification
    cursor.execute("INSERT INTO notifications (user_id, title, message, created_at) VALUES (?, ?, ?, ?)",
                   (user_id, "Payment Successful", f"Payment of ₹{data.amount:.2f} was successful. Transaction Ref: {tx_ref}", now))
    
    # Automatically generate next month's bill for the same meter
    try:
        bill_month_str = bill["billing_month"]
        due_date_str = bill["due_date"]
        
        import calendar
        from datetime import datetime as dt, timedelta
        
        current_due = dt.strptime(due_date_str, "%Y-%m-%d")
        next_due = current_due + timedelta(days=30)
        next_due_str = next_due.strftime("%Y-%m-%d")
        
        parts = bill_month_str.split(" ")
        if len(parts) == 2:
            months = list(calendar.month_name)
            if parts[0] in months:
                idx = months.index(parts[0])
                next_idx = idx + 1 if idx < 12 else 1
                next_year = int(parts[1]) if idx < 12 else int(parts[1]) + 1
                next_month_name = f"{months[next_idx]} {next_year}"
            else:
                next_month_name = "Next Month"
        else:
            next_month_name = "Next Month"
            
        cursor.execute("SELECT COUNT(*) as count FROM bills WHERE meter_id = ? AND billing_month = ?", (bill["meter_id"], next_month_name))
        if cursor.fetchone()["count"] == 0:
            next_amount = round(bill["amount"] * 0.95 + 50.0, 2)
            next_units = round(bill["units_consumed"] * 0.98, 1)
            cursor.execute("""
                INSERT INTO bills (meter_id, billing_month, units_consumed, amount, due_date, payment_status)
                VALUES (?, ?, ?, ?, ?, 'Unpaid')
            """, (bill["meter_id"], next_month_name, next_units, next_amount, next_due_str))
            
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, created_at)
                VALUES (?, 'New Bill Generated', ?, ?)
            """, (user_id, f"Your electricity bill for {next_month_name} of ₹{next_amount:.2f} has been generated.", now))
    except Exception as e:
        print(f"Error generating next month bill: {e}")
        
    conn.commit()
    conn.close()
    return {"message": "Payment successful", "transaction_ref": tx_ref}

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
    return {"message": "Reminder updated successfully"}

@app.get("/api/notifications")
def get_notifications(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    notifications = [dict(n) for n in cursor.fetchall()]
    conn.close()
    return notifications

@app.post("/api/ai/chat")
def ai_chat(data: ChatSchema, user_id: int = Depends(get_current_user_id)):
    msg = data.message.lower()
    if "save" in msg or "reduce" in msg or "lower" in msg:
        reply = "Here are a few ways to lower your electricity bill:\n1. Switch to LED lighting to save up to 80% on lighting energy.\n2. Service your air conditioning units regularly to ensure peak efficiency.\n3. Unplug standby appliances when not in use."
    elif "power" in msg or "use" in msg or "consume" in msg or "unit" in msg:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.units_consumed, b.billing_month 
            FROM bills b 
            JOIN meters m ON b.meter_id = m.id 
            WHERE m.user_id = ?
            ORDER BY b.due_date DESC
            LIMIT 3
        """, (user_id,))
        bills = cursor.fetchall()
        conn.close()
        if bills:
            details = "\n".join([f"- {b['billing_month']}: {b['units_consumed']} kWh" for b in bills])
            reply = f"Here is your recent power consumption:\n{details}"
        else:
            reply = "I couldn't find any recorded power usage details for your connection."
    elif any(k in msg for k in ["bill", "due", "date", "next", "month", "upcoming", "pending", "status", "pay", "cost", "amount", "when", "how much"]):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.amount, b.due_date, b.billing_month FROM bills b 
            JOIN meters m ON b.meter_id = m.id 
            WHERE m.user_id = ? AND b.payment_status = 'Unpaid' 
            LIMIT 1
        """, (user_id,))
        bill = cursor.fetchone()
        conn.close()
        if bill:
            reply = f"Your upcoming unpaid bill is ₹{bill['amount']:.2f}, due on {bill['due_date']} ({bill['billing_month']})."
        else:
            reply = "You don't have any pending unpaid bills."
    else:
        reply = "Hello! I am your Smart Electricity AI Assistant. Ask me questions about saving power, bill predictions, or your current bill status."
    
    return {"reply": reply}

@app.exception_handler(StarletteHTTPException)
def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )

# Serve Frontend static assets
static_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app-new"))
@app.get("/")
def read_root():
    return FileResponse(os.path.join(static_path, "index.html"))

init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
