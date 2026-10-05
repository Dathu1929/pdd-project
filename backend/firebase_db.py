import os
import datetime
import logging
from typing import Dict, Any, List, Optional
import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger("firebase_db")

# Path to the Firebase service account JSON key file.
# Users should place their firebase-key.json in the backend directory.
FIREBASE_KEY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "firebase-key.json"))

db = None
firebase_initialized = False

def init_firebase():
    global db, firebase_initialized
    if firebase_initialized:
        return
    
    try:
        if os.path.exists(FIREBASE_KEY_PATH):
            logger.info(f"Initializing Firebase with service account from {FIREBASE_KEY_PATH}")
            cred = credentials.Certificate(FIREBASE_KEY_PATH)
            firebase_admin.initialize_app(cred)
        else:
            logger.warning(f"firebase-key.json not found at {FIREBASE_KEY_PATH}. Attempting default initialization...")
            firebase_admin.initialize_app()
        db = firestore.client()
        firebase_initialized = True
        logger.info("Firebase Firestore database connection established successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}. SQLite database or a mock/local fallback will be used if Firebase is unavailable.")
        # Create an in-memory/local mock client to prevent the server from crashing
        db = MockFirestoreClient()

class MockFirestoreClient:
    """Fallback in-memory mock client to prevent server crash if firebase is not configured."""
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        if name not in self._collections:
            self._collections[name] = MockCollection(name)
        return self._collections[name]

    def transaction(self):
        return MockTransaction()

class MockTransaction:
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): pass

class MockCollection:
    def __init__(self, name):
        self.name = name
        self._documents = {}

    def document(self, doc_id=None):
        if doc_id is None:
            import uuid
            doc_id = str(uuid.uuid4())
        else:
            doc_id = str(doc_id)
        if doc_id not in self._documents:
            self._documents[doc_id] = MockDocument(doc_id)
        return self._documents[doc_id]

    def stream(self):
        return [doc for doc in self._documents.values() if doc.exists]

    def where(self, field, op, value):
        return MockQuery(self, field, op, value)

class MockDocument:
    def __init__(self, doc_id):
        self.id = doc_id
        self._data = {}
        self.exists = False

    def get(self, transaction=None):
        return self

    def to_dict(self):
        return self._data

    def set(self, data, merge=False):
        if merge:
            self._data.update(data)
        else:
            self._data = data
        self.exists = True

    def update(self, data):
        self._data.update(data)
        self.exists = True

    def delete(self):
        self.exists = False
        self._data = {}

class MockQuery:
    def __init__(self, collection, field, op, value):
        self.collection = collection
        self.filters = [(field, op, value)]

    def where(self, field, op, value):
        self.filters.append((field, op, value))
        return self

    def stream(self):
        results = []
        for doc in self.collection._documents.values():
            if not doc.exists:
                continue
            data = doc._data
            matches = True
            for field, op, value in self.filters:
                # Simple operator checks
                val = data.get(field)
                if op == "==":
                    if val != value: matches = False
                elif op == "!=":
                    if val == value: matches = False
                elif op == "in":
                    if val not in value: matches = False
            if matches:
                results.append(doc)
        return results

# Initialize Firebase on module import
init_firebase()

def get_next_id(collection_name: str) -> int:
    """Uses a atomic Firestore counter to generate sequential integer IDs matching SQLite behavior."""
    if not firebase_initialized or isinstance(db, MockFirestoreClient):
        # Local mock counter logic
        counter_ref = db.collection("counters").document(collection_name)
        snap = counter_ref.get()
        current = snap.to_dict().get("current_value", 0) if snap.exists else 0
        next_val = current + 1
        counter_ref.set({"current_value": next_val})
        return next_val

    # Real Firestore transaction-based atomic counter
    counter_ref = db.collection("counters").document(collection_name)
    @firestore.transactional
    def update_counter(transaction):
        snapshot = counter_ref.get(transaction=transaction)
        if snapshot.exists:
            current = snapshot.get("current_value")
            next_val = current + 1
        else:
            next_val = 1
        transaction.set(counter_ref, {"current_value": next_val})
        return next_val
        
    transaction = db.transaction()
    return update_counter(transaction)

# ----------------- USERS MODULE -----------------

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    docs = db.collection("users").where("email", "==", email).stream()
    for doc in docs:
        d = doc.to_dict()
        d["id"] = int(doc.id)
        return d
    return None

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    doc = db.collection("users").document(str(user_id)).get()
    if doc.exists:
        d = doc.to_dict()
        d["id"] = int(doc.id)
        return d
    return None

def get_user_by_email_or_phone_and_password(login_id: str, password_hash: str) -> Optional[Dict[str, Any]]:
    # Search by email first
    docs = db.collection("users").where("email", "==", login_id).stream()
    for doc in docs:
        d = doc.to_dict()
        if d.get("password") == password_hash:
            d["id"] = int(doc.id)
            return d
    # Search by phone
    docs = db.collection("users").where("phone", "==", login_id).stream()
    for doc in docs:
        d = doc.to_dict()
        if d.get("password") == password_hash:
            d["id"] = int(doc.id)
            return d
    return None

def create_user(name: str, email: str, password_hash: str, phone: str = None) -> int:
    user_id = get_next_id("users")
    doc_ref = db.collection("users").document(str(user_id))
    doc_ref.set({
        "name": name,
        "email": email,
        "password": password_hash,
        "phone": phone,
        "alternate_phone": "",
        "sms_recipient_phone": phone or "",
        "email_recipient_email": email,
        "sms_reminders": 1,
        "email_reminders": 1,
        "whatsapp_reminders": 1,
        "phone_reminders": 1
    })
    return user_id

def update_user_profile(user_id: int, name: str, phone: str, alternate_phone: str) -> bool:
    doc_ref = db.collection("users").document(str(user_id))
    if not doc_ref.get().exists:
        return False
    doc_ref.update({
        "name": name,
        "phone": phone,
        "alternate_phone": alternate_phone
    })
    return True

def update_reminder_channels(user_id: int, sms: int, email: int, whatsapp: int, phone: int) -> bool:
    doc_ref = db.collection("users").document(str(user_id))
    if not doc_ref.get().exists:
        return False
    doc_ref.update({
        "sms_reminders": sms,
        "email_reminders": email,
        "whatsapp_reminders": whatsapp,
        "phone_reminders": phone
    })
    return True

# ----------------- METERS MODULE -----------------

def get_meters(user_id: int) -> List[Dict[str, Any]]:
    docs = db.collection("meters").where("user_id", "==", int(user_id)).stream()
    meters = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = int(doc.id)
        meters.append(d)
    # Sort by id descending
    meters.sort(key=lambda x: x["id"], reverse=True)
    return meters

def get_meter_by_id(meter_id: int) -> Optional[Dict[str, Any]]:
    doc = db.collection("meters").document(str(meter_id)).get()
    if doc.exists:
        d = doc.to_dict()
        d["id"] = int(doc.id)
        return d
    return None

def add_meter(user_id: int, service_number: str, board_name: str, consumer_name: str, address: str) -> int:
    # Check uniqueness
    existing = db.collection("meters").where("service_number", "==", service_number).stream()
    if any(existing):
        raise ValueError("Service number already exists.")
        
    meter_id = get_next_id("meters")
    doc_ref = db.collection("meters").document(str(meter_id))
    doc_ref.set({
        "user_id": int(user_id),
        "service_number": service_number,
        "board_name": board_name,
        "consumer_name": consumer_name,
        "address": address,
        "prediction_reminder_enabled": 1
    })
    return meter_id

def delete_meter(meter_id: int, user_id: int) -> bool:
    doc_ref = db.collection("meters").document(str(meter_id))
    snap = doc_ref.get()
    if not snap.exists or snap.to_dict().get("user_id") != int(user_id):
        return False

    # Delete nested elements (bills, payments, notifications associated with this meter)
    bills_docs = db.collection("bills").where("meter_id", "==", int(meter_id)).stream()
    for bill in bills_docs:
        bill_id = int(bill.id)
        # Delete payments for this bill
        pay_docs = db.collection("payments").where("bill_id", "==", bill_id).stream()
        for pay in pay_docs:
            db.collection("payments").document(pay.id).delete()
        # Delete notification history
        hist_docs = db.collection("notification_history").where("bill_id", "==", bill_id).stream()
        for hist in hist_docs:
            db.collection("notification_history").document(hist.id).delete()
        db.collection("bills").document(str(bill_id)).delete()

    doc_ref.delete()
    return True

# ----------------- BILLS MODULE -----------------

def get_bills(user_id: int, meter_id: Optional[int] = None) -> List[Dict[str, Any]]:
    # Get all meters for this user to filter bills
    meters = get_meters(user_id)
    meter_ids = [m["id"] for m in meters]
    if not meter_ids:
        return []

    if meter_id is not None:
        if int(meter_id) not in meter_ids:
            return []
        query_ids = [int(meter_id)]
    else:
        query_ids = meter_ids

    # Firestore in queries support maximum of 30 values in a list (concurrency/limit constraint)
    all_bills = []
    
    # Batch IDs into groups of 30
    for i in range(0, len(query_ids), 30):
        batch_ids = query_ids[i:i+30]
        docs = db.collection("bills").where("meter_id", "in", batch_ids).stream()
        for doc in docs:
            d = doc.to_dict()
            d["id"] = int(doc.id)
            # Find board/consumer/service info from meter
            m_info = next((m for m in meters if m["id"] == d["meter_id"]), {})
            d["board_name"] = m_info.get("board_name", "")
            d["service_number"] = m_info.get("service_number", "")
            all_bills.append(d)

    # Sort bills by due_date or ID descending
    all_bills.sort(key=lambda x: x["id"], reverse=True)
    return all_bills

def get_bill_by_id(bill_id: int) -> Optional[Dict[str, Any]]:
    doc = db.collection("bills").document(str(bill_id)).get()
    if doc.exists:
        d = doc.to_dict()
        d["id"] = int(doc.id)
        # Populate board/service details
        m_doc = db.collection("meters").document(str(d["meter_id"])).get()
        if m_doc.exists:
            m_data = m_doc.to_dict()
            d["board_name"] = m_data.get("board_name", "")
            d["service_number"] = m_data.get("service_number", "")
            d["user_id"] = m_data.get("user_id")
        return d
    return None

def create_bill(meter_id: int, consumer_id: str, consumer_name: str, mobile_number: str,
                email_address: str, billing_month: str, units_consumed: float, amount: float,
                due_date: str, bill_issue_date: str = None) -> int:
    bill_id = get_next_id("bills")
    doc_ref = db.collection("bills").document(str(bill_id))
    doc_ref.set({
        "meter_id": int(meter_id),
        "consumer_id": consumer_id,
        "consumer_name": consumer_name,
        "mobile_number": mobile_number,
        "email_address": email_address,
        "billing_month": billing_month,
        "units_consumed": float(units_consumed),
        "amount": float(amount),
        "bill_amount": float(amount),
        "amount_paid": 0.0,
        "remaining_amount": float(amount),
        "bill_issue_date": bill_issue_date or datetime.date.today().isoformat(),
        "due_date": due_date,
        "payment_status": "Unpaid",
        "transaction_ref": None
    })
    return bill_id

def update_bill_payment(bill_id: int, amount_paid: float, remaining_amount: float, status: str, transaction_ref: str = None) -> bool:
    doc_ref = db.collection("bills").document(str(bill_id))
    if not doc_ref.get().exists:
        return False
    updates = {
        "amount_paid": float(amount_paid),
        "remaining_amount": float(remaining_amount),
        "payment_status": status
    }
    if transaction_ref:
        updates["transaction_ref"] = transaction_ref
    doc_ref.update(updates)
    return True

def search_bills(query_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Search all bills using specific fields like consumer_id or mobile_number
    ref = db.collection("bills")
    for k, v in query_dict.items():
        ref = ref.where(k, "==", v)
    
    docs = ref.stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = int(doc.id)
        # Fetch meter detail
        m_doc = db.collection("meters").document(str(d["meter_id"])).get()
        if m_doc.exists:
            m_data = m_doc.to_dict()
            d["board_name"] = m_data.get("board_name", "")
            d["service_number"] = m_data.get("service_number", "")
        results.append(d)
    return results

# ----------------- PAYMENTS MODULE -----------------

def create_payment(bill_id: int, amount: float, payment_method: str, transaction_ref: str, verification_status: str = "VERIFIED") -> int:
    payment_id = get_next_id("payments")
    doc_ref = db.collection("payments").document(str(payment_id))
    doc_ref.set({
        "bill_id": int(bill_id),
        "amount": float(amount),
        "payment_method": payment_method,
        "transaction_ref": transaction_ref,
        "paid_at": datetime.datetime.now().isoformat(),
        "verification_status": verification_status
    })
    return payment_id

def update_payment_verification_status(payment_id: int, status: str) -> bool:
    doc_ref = db.collection("payments").document(str(payment_id))
    if not doc_ref.get().exists:
        return False
    doc_ref.update({"verification_status": status})
    return True

def get_payments_history(user_id: int) -> List[Dict[str, Any]]:
    meters = get_meters(user_id)
    meter_ids = [m["id"] for m in meters]
    if not meter_ids:
        return []

    # Get all bills for these meters
    bills = []
    for i in range(0, len(meter_ids), 30):
        batch_ids = meter_ids[i:i+30]
        b_docs = db.collection("bills").where("meter_id", "in", batch_ids).stream()
        for doc in b_docs:
            d = doc.to_dict()
            d["id"] = int(doc.id)
            bills.append(d)

    if not bills:
        return []

    bill_ids = [b["id"] for b in bills]
    payments = []
    # Get payments for these bills
    for i in range(0, len(bill_ids), 30):
        batch_bills = bill_ids[i:i+30]
        p_docs = db.collection("payments").where("bill_id", "in", batch_bills).stream()
        for doc in p_docs:
            d = doc.to_dict()
            d["id"] = int(doc.id)
            
            # Join bill and meter info
            bill_info = next((b for b in bills if b["id"] == d["bill_id"]), {})
            meter_info = next((m for m in meters if m["id"] == bill_info.get("meter_id")), {})
            
            d["consumer_name"] = bill_info.get("consumer_name", "")
            d["billing_month"] = bill_info.get("billing_month", "")
            d["service_number"] = meter_info.get("service_number", "")
            d["board_name"] = meter_info.get("board_name", "")
            payments.append(d)

    # Sort payments by paid_at descending
    payments.sort(key=lambda x: x.get("paid_at", ""), reverse=True)
    return payments

# ----------------- RECIPIENT SETTINGS & REMINDERS -----------------

def get_settings_recipients(user_id: int) -> Dict[str, Any]:
    u = get_user_by_id(user_id)
    if not u:
        return {}
    return {
        "sms_recipient_phone": u.get("sms_recipient_phone") or u.get("phone") or "",
        "email_recipient_email": u.get("email_recipient_email") or u.get("email") or ""
    }

def update_settings_recipients(user_id: int, sms_phone: str, email_address: str) -> bool:
    doc_ref = db.collection("users").document(str(user_id))
    if not doc_ref.get().exists:
        return False
    doc_ref.update({
        "sms_recipient_phone": sms_phone,
        "email_recipient_email": email_address
    })
    return True

def get_reminders(user_id: int) -> List[Dict[str, Any]]:
    docs = db.collection("reminders").where("user_id", "==", int(user_id)).stream()
    reminders = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = int(doc.id)
        reminders.append(d)
    return reminders

def add_reminder(user_id: int, days_before: int, enabled: int = 1) -> int:
    rem_id = get_next_id("reminders")
    doc_ref = db.collection("reminders").document(str(rem_id))
    doc_ref.set({
        "user_id": int(user_id),
        "days_before": int(days_before),
        "enabled": int(enabled)
    })
    return rem_id

def toggle_reminder(user_id: int, days_before: int, enabled: int) -> bool:
    # Find existing reminder
    docs = db.collection("reminders").where("user_id", "==", int(user_id)).where("days_before", "==", int(days_before)).stream()
    found = False
    for doc in docs:
        db.collection("reminders").document(doc.id).update({"enabled": int(enabled)})
        found = True
    if not found:
        # Create new reminder
        add_reminder(user_id, days_before, enabled)
    return True

def toggle_prediction_reminder(user_id: int, meter_id: int, enabled: int) -> bool:
    doc_ref = db.collection("meters").document(str(meter_id))
    snap = doc_ref.get()
    if not snap.exists or snap.to_dict().get("user_id") != int(user_id):
        return False
    doc_ref.update({"prediction_reminder_enabled": int(enabled)})
    return True

# ----------------- NOTIFICATIONS MODULE -----------------

def get_notifications(user_id: int) -> List[Dict[str, Any]]:
    docs = db.collection("notifications").where("user_id", "==", int(user_id)).stream()
    notifications = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = int(doc.id)
        notifications.append(d)
    # Sort by created_at descending
    notifications.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return notifications

def clear_notifications(user_id: int) -> bool:
    docs = db.collection("notifications").where("user_id", "==", int(user_id)).stream()
    for doc in docs:
        db.collection("notifications").document(doc.id).delete()
    return True

def add_notification(user_id: int, title: str, message: str) -> int:
    notif_id = get_next_id("notifications")
    doc_ref = db.collection("notifications").document(str(notif_id))
    doc_ref.set({
        "user_id": int(user_id),
        "title": title,
        "message": message,
        "created_at": datetime.datetime.now().isoformat(),
        "is_read": 0
    })
    return notif_id

def get_notification_history(user_id: int) -> List[Dict[str, Any]]:
    docs = db.collection("notification_history").where("user_id", "==", int(user_id)).stream()
    history = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = int(doc.id)
        history.append(d)
    # Sort by sent_at descending
    history.sort(key=lambda x: x.get("sent_at", ""), reverse=True)
    return history

def get_notification_history_by_id(history_id: int) -> Optional[Dict[str, Any]]:
    doc = db.collection("notification_history").document(str(history_id)).get()
    if doc.exists:
        d = doc.to_dict()
        d["id"] = int(doc.id)
        return d
    return None

def add_notification_history(user_id: int, bill_id: Optional[int], n_type: str, recipient: str, title: Optional[str], message: str, status: str, provider_response: str = None, error_message: str = None) -> int:
    hist_id = get_next_id("notification_history")
    doc_ref = db.collection("notification_history").document(str(hist_id))
    doc_ref.set({
        "user_id": int(user_id),
        "bill_id": int(bill_id) if bill_id is not None else None,
        "type": n_type,
        "recipient": recipient,
        "title": title,
        "message": message,
        "status": status,
        "provider_response": provider_response,
        "error_message": error_message,
        "sent_at": datetime.datetime.now().isoformat(),
        "retry_count": 0
    })
    return hist_id

def update_notification_history(history_id: int, status: str, provider_response: str = None, error_message: str = None, increment_retry: bool = False) -> bool:
    doc_ref = db.collection("notification_history").document(str(history_id))
    snap = doc_ref.get()
    if not snap.exists:
        return False
    
    updates = {
        "status": status,
        "provider_response": provider_response,
        "error_message": error_message
    }
    if increment_retry:
        current_retry = snap.to_dict().get("retry_count", 0)
        updates["retry_count"] = current_retry + 1
        
    doc_ref.update(updates)
    return True
