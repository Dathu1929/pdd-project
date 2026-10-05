import re
import logging
from typing import Any, List, Dict, Optional, Union
import firebase_db

logger = logging.getLogger("firebase_sqlite_mock")

class MockRow:
    """Mimics sqlite3.Row for dict conversion and indexing."""
    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def __getitem__(self, key: Union[int, str]) -> Any:
        if isinstance(key, int):
            return list(self._data.values())[key]
        return self._data[key]

    def keys(self) -> List[str]:
        return list(self._data.keys())

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __repr__(self):
        return f"MockRow({self._data})"

Row = MockRow

class MockCursor:
    def __init__(self):
        self._results: List[MockRow] = []
        self.lastrowid: Optional[int] = None
        self.rowcount: int = 0

    def execute(self, sql: str, params: tuple = ()):
        sql_clean = re.sub(r'\s+', ' ', sql.strip()).lower()
        logger.debug(f"Intercepted SQL: {sql_clean} | Params: {params}")

        # ----------------- INITS / PRAGMA -----------------
        if "pragma " in sql_clean:
            self._results = []
            return self

        if "create table" in sql_clean:
            self._results = []
            return self

        if "alter table" in sql_clean:
            self._results = []
            return self

        # ----------------- USERS MODULE -----------------
        # 1. Register User
        if "insert into users" in sql_clean:
            # (name, email, password, phone, alternate_phone)
            # or dynamically added columns
            name, email, password, phone = params[0], params[1], params[2], params[3]
            user_id = firebase_db.create_user(name, email, password, phone)
            if len(params) > 4 and params[4]:
                firebase_db.update_user_profile(user_id, name, phone, params[4])
            self.lastrowid = user_id
            self._results = []
            return self

        # 2. Login User
        if "select * from users where (email = ? or phone = ?) and password = ?" in sql_clean:
            login_id = params[0]
            password_hash = params[2]
            user = firebase_db.get_user_by_email_or_phone_and_password(login_id, password_hash)
            self._results = [MockRow(user)] if user else []
            return self

        # 3. User profile details
        if "select id, name, email, phone, alternate_phone," in sql_clean and "from users where id = ?" in sql_clean:
            user_id = params[0]
            user = firebase_db.get_user_by_id(user_id)
            self._results = [MockRow(user)] if user else []
            return self

        # 4. Fetch notification recipients
        if "select name, email, phone, sms_recipient_phone, email_recipient_email from users where id = ?" in sql_clean:
            user_id = params[0]
            user = firebase_db.get_user_by_id(user_id)
            self._results = [MockRow(user)] if user else []
            return self

        # 5. Profile Update
        if "update users set name = ?, email = ?, password = ?, phone = ?, alternate_phone = ? where id = ?" in sql_clean:
            name, email, password, phone, alt_phone, user_id = params
            firebase_db.update_user_profile(user_id, name, phone, alt_phone)
            # Update password/email directly
            doc_ref = firebase_db.db.collection("users").document(str(user_id))
            doc_ref.update({"password": password, "email": email})
            self._results = []
            return self

        # 6. Reminder preferences update
        if "update users set sms_reminders = ?, email_reminders = ?, whatsapp_reminders = ?, phone_reminders = ? where id = ?" in sql_clean:
            sms, email, whatsapp, phone, user_id = params
            firebase_db.update_reminder_channels(user_id, sms, email, whatsapp, phone)
            self._results = []
            return self

        # 7. Recipients settings update
        if "update users set sms_recipient_phone = ?, email_recipient_email = ? where id = ?" in sql_clean:
            sms_phone, email_address, user_id = params
            firebase_db.update_settings_recipients(user_id, sms_phone, email_address)
            self._results = []
            return self

        # ----------------- METERS MODULE -----------------
        # 1. Get Meters
        if "select * from meters where user_id = ? order by id desc" in sql_clean:
            user_id = params[0]
            meters = firebase_db.get_meters(user_id)
            self._results = [MockRow(m) for m in meters]
            return self

        # 2. Add Meter
        if "insert into meters (user_id, service_number, board_name, consumer_name, address)" in sql_clean:
            user_id, service_number, board_name, consumer_name, address = params[:5]
            meter_id = firebase_db.add_meter(user_id, service_number, board_name, consumer_name, address)
            self.lastrowid = meter_id
            self._results = []
            return self

        # 3. Check Meter ID ownership or verification
        if "select id from meters where id = ? and user_id = ?" in sql_clean:
            meter_id, user_id = params
            meter = firebase_db.get_meter_by_id(meter_id)
            if meter and meter.get("user_id") == int(user_id):
                self._results = [MockRow({"id": meter_id})]
            else:
                self._results = []
            return self

        if "select id, consumer_name from meters where id = ? and user_id = ?" in sql_clean:
            meter_id, user_id = params
            meter = firebase_db.get_meter_by_id(meter_id)
            if meter and meter.get("user_id") == int(user_id):
                self._results = [MockRow({"id": meter_id, "consumer_name": meter.get("consumer_name", "")})]
            else:
                self._results = []
            return self

        # 4. Delete Meter
        if "delete from meters where id = ?" in sql_clean:
            # Note: server.py handles deleting associated tables separately,
            # but firebase_db.delete_meter deletes them nested as well. Let's run it.
            meter_id = params[0]
            # Find owner user_id
            meter = firebase_db.get_meter_by_id(meter_id)
            if meter:
                firebase_db.delete_meter(meter_id, meter["user_id"])
            self._results = []
            return self

        if "delete from bills where meter_id = ?" in sql_clean:
            # Handled by firebase_db.delete_meter
            self._results = []
            return self

        if "delete from payments where bill_id in (select id from bills where meter_id = ?)" in sql_clean:
            self._results = []
            return self

        if "delete from notification_history where bill_id in (select id from bills where meter_id = ?)" in sql_clean:
            self._results = []
            return self

        # 5. Meters count
        if "select count(*) as count from meters where user_id = ?" in sql_clean:
            user_id = params[0]
            meters = firebase_db.get_meters(user_id)
            self._results = [MockRow({"count": len(meters)})]
            return self

        # 6. Prediction reminder toggle
        if "update meters set prediction_reminder_enabled = ? where id = ?" in sql_clean:
            enabled, meter_id = params
            meter = firebase_db.get_meter_by_id(meter_id)
            if meter:
                firebase_db.toggle_prediction_reminder(meter["user_id"], meter_id, enabled)
            self._results = []
            return self

        # 7. Prediction scheduler query
        if "from meters m join users u on m.user_id = u.id" in sql_clean:
            docs = firebase_db.db.collection("meters").stream()
            results = []
            for doc in docs:
                m = doc.to_dict()
                m_id = int(doc.id)
                user = firebase_db.get_user_by_id(m["user_id"])
                if user:
                    results.append(MockRow({
                        "meter_id": m_id,
                        "service_number": m.get("service_number"),
                        "board_name": m.get("board_name"),
                        "prediction_reminder_enabled": m.get("prediction_reminder_enabled", 1),
                        "user_id": user["id"],
                        "user_name": user.get("name"),
                        "user_email": user.get("email"),
                        "user_phone": user.get("phone")
                    }))
            self._results = results
            return self

        # ----------------- BILLS MODULE -----------------
        # 1. Fetch Bills
        if "from bills b join meters m on b.meter_id = m.id join users u on m.user_id = u.id" in sql_clean:
            # Dashboard or Bill list
            # Can be filtered by meter or board/service number
            if "where m.user_id = ?" in sql_clean:
                user_id = params[0]
                if len(params) > 2:
                    # Search bill (user_id, board_name, service_number)
                    board_name = params[1]
                    service_number = params[2]
                    bills = firebase_db.get_bills(user_id)
                    filtered = [b for b in bills if b.get("board_name") == board_name and b.get("service_number") == service_number]
                    self._results = [MockRow(b) for b in filtered]
                else:
                    bills = firebase_db.get_bills(user_id)
                    self._results = [MockRow(b) for b in bills]
            else:
                # Scheduler query: fetch all unpaid/partially paid bills for all users
                docs = firebase_db.db.collection("bills").where("payment_status", "!=", "Paid").stream()
                results = []
                for doc in docs:
                    d = doc.to_dict()
                    d["id"] = int(doc.id)
                    if float(d.get("remaining_amount", 0.0)) > 0:
                        meter = firebase_db.get_meter_by_id(d["meter_id"])
                        if meter:
                            user = firebase_db.get_user_by_id(meter["user_id"])
                            if user:
                                row_data = {
                                    "bill_id": d["id"],
                                    "billing_month": d.get("billing_month"),
                                    "bill_amount": d.get("bill_amount", d.get("amount")),
                                    "amount_paid": d.get("amount_paid", 0.0),
                                    "remaining_amount": d.get("remaining_amount"),
                                    "due_date": d.get("due_date"),
                                    "bill_issue_date": d.get("bill_issue_date"),
                                    "payment_status": d.get("payment_status"),
                                    "bill_consumer_name": d.get("consumer_name") or meter.get("consumer_name") or user.get("name"),
                                    "bill_mobile": d.get("mobile_number") or user.get("phone"),
                                    "bill_email": d.get("email_address") or user.get("email"),
                                    "meter_id": d["meter_id"],
                                    "service_number": meter.get("service_number"),
                                    "board_name": meter.get("board_name"),
                                    "meter_consumer_name": meter.get("consumer_name"),
                                    "user_id": user["id"],
                                    "user_name": user.get("name"),
                                    "user_email": user.get("email"),
                                    "user_phone": user.get("phone"),
                                    "target_mobile": user.get("sms_recipient_phone") or d.get("mobile_number") or user.get("phone") or "",
                                    "target_email": user.get("email_recipient_email") or d.get("email_address") or user.get("email") or "",
                                    "sms_enabled": user.get("sms_reminders", 1),
                                    "email_enabled": user.get("email_reminders", 1)
                                }
                                results.append(MockRow(row_data))
                self._results = results
            return self

        if "select b.*, m.service_number, m.board_name, u.email as user_email" in sql_clean:
            # Single bill details for payment / verification
            bill_id = params[0]
            bill = firebase_db.get_bill_by_id(bill_id)
            if bill:
                user = firebase_db.get_user_by_id(bill["user_id"])
                bill_data = {
                    **bill,
                    "user_email": user.get("email", ""),
                    "user_phone": user.get("phone", ""),
                    "user_name": user.get("name", ""),
                    "sms_recipient_phone": user.get("sms_recipient_phone") or user.get("phone") or "",
                    "email_recipient_email": user.get("email_recipient_email") or user.get("email") or "",
                    "sms_enabled": user.get("sms_reminders", 1),
                    "email_enabled": user.get("email_reminders", 1),
                }
                self._results = [MockRow(bill_data)]
            else:
                self._results = []
            return self

        # 2. Add Bill
        if "insert into bills (" in sql_clean:
            # (meter_id, consumer_id, consumer_name, mobile_number, email_address, billing_month, units_consumed, amount, bill_amount, amount_paid, remaining_amount, bill_issue_date, due_date, payment_status)
            meter_id = params[0]
            consumer_id = params[1]
            consumer_name = params[2]
            mobile_number = params[3]
            email_address = params[4]
            billing_month = params[5]
            units_consumed = params[6]
            amount = params[7]
            # Handle default positions
            due_date = params[12]
            bill_issue_date = params[11]
            bill_id = firebase_db.create_bill(
                meter_id=meter_id,
                consumer_id=consumer_id,
                consumer_name=consumer_name,
                mobile_number=mobile_number,
                email_address=email_address,
                billing_month=billing_month,
                units_consumed=units_consumed,
                amount=amount,
                due_date=due_date,
                bill_issue_date=bill_issue_date
            )
            self.lastrowid = bill_id
            self._results = []
            return self

        # 3. Previous Bill Comparison
        if "where meter_id = ? and id < ?" in sql_clean and "limit 1" in sql_clean:
            meter_id, bill_id = params
            # Fetch all bills for meter and find the previous one
            docs = firebase_db.db.collection("bills").where("meter_id", "==", int(meter_id)).stream()
            bills = []
            for doc in docs:
                d = doc.to_dict()
                d["id"] = int(doc.id)
                if d["id"] < int(bill_id):
                    bills.append(d)
            if bills:
                bills.sort(key=lambda x: x["id"], reverse=True)
                self._results = [MockRow(bills[0])]
            else:
                self._results = []
            return self

        # 4. Update Bill Payment
        if "update bills set amount_paid = ?, remaining_amount = ?, payment_status = ?, transaction_ref = ? where id = ?" in sql_clean:
            amt_paid, rem_amt, status, tx_ref, bill_id = params
            firebase_db.update_bill_payment(bill_id, amt_paid, rem_amt, status, tx_ref)
            self._results = []
            return self

        # 5. Dashboard unpaid amounts sum
        if "select coalesce(sum(remaining_amount), 0.0) as unpaid_amount" in sql_clean:
            user_id = params[0]
            bills = firebase_db.get_bills(user_id)
            unpaid = sum(float(b.get("remaining_amount", 0.0)) for b in bills if b.get("payment_status") != "Paid")
            self._results = [MockRow({"unpaid_amount": unpaid})]
            return self

        # 6. Dashboard paid amounts sum
        if "select coalesce(sum(amount_paid), 0.0) as paid_amount" in sql_clean:
            user_id = params[0]
            bills = firebase_db.get_bills(user_id)
            paid = sum(float(b.get("amount_paid", 0.0)) for b in bills)
            self._results = [MockRow({"paid_amount": paid})]
            return self

        # 7. Dashboard active/latest bill
        if "from bills b join meters m on b.meter_id = m.id where m.user_id = ?" in sql_clean and "limit 1" in sql_clean:
            user_id = params[0]
            bills = firebase_db.get_bills(user_id)
            if bills:
                # server.py logic: unpaid first, then due_date asc, then id desc
                def sort_key(b):
                    paid_val = 1 if b.get("payment_status") == "Paid" else 0
                    due = b.get("due_date", "")
                    b_id = b.get("id", 0)
                    return (paid_val, due, -b_id)
                bills.sort(key=sort_key)
                self._results = [MockRow(bills[0])]
            else:
                self._results = []
            return self

        # ----------------- PAYMENTS MODULE -----------------
        # 1. Record payment
        if "insert into payments (" in sql_clean:
            bill_id, amount, method, ref, paid_at = params[:5]
            pay_id = firebase_db.create_payment(bill_id, amount, method, ref)
            self.lastrowid = pay_id
            self._results = []
            return self

        # 2. Payments history
        if "from payments p join bills b on p.bill_id = b.id join meters m on b.meter_id = m.id" in sql_clean:
            user_id = params[0]
            history = firebase_db.get_payments_history(user_id)
            self._results = [MockRow(p) for p in history]
            return self

        # 3. Dashboard payments total
        if "select coalesce(sum(p.amount), 0.0) as total from payments p" in sql_clean:
            user_id = params[0]
            history = firebase_db.get_payments_history(user_id)
            total = sum(float(p.get("amount", 0.0)) for p in history)
            self._results = [MockRow({"total": total})]
            return self

        # ----------------- REMINDERS MODULE -----------------
        # 1. Fetch Reminders
        if "select * from reminders where user_id = ?" in sql_clean:
            user_id = params[0]
            if len(params) > 1:
                # Specific reminder check
                days_before = params[1]
                rems = firebase_db.get_reminders(user_id)
                filtered = [r for r in rems if r.get("days_before") == int(days_before)]
                self._results = [MockRow(r) for r in filtered]
            else:
                rems = firebase_db.get_reminders(user_id)
                self._results = [MockRow(r) for r in rems]
            return self

        # 2. Toggle reminder settings
        if "update reminders set enabled = ? where user_id = ? and days_before = ?" in sql_clean:
            enabled, user_id, days_before = params
            firebase_db.toggle_reminder(user_id, days_before, enabled)
            self._results = []
            return self

        if "insert into reminders (user_id, days_before, enabled) values (?, ?, ?)" in sql_clean:
            user_id, days_before, enabled = params
            rem_id = firebase_db.add_reminder(user_id, days_before, enabled)
            self.lastrowid = rem_id
            self._results = []
            return self

        # ----------------- NOTIFICATIONS MODULE -----------------
        # 1. Fetch Notifications
        if "select * from notifications where user_id = ?" in sql_clean:
            user_id = params[0]
            notifs = firebase_db.get_notifications(user_id)
            self._results = [MockRow(n) for n in notifs]
            return self

        # 2. Clear notifications
        if "delete from notifications where user_id = ?" in sql_clean:
            user_id = params[0]
            firebase_db.clear_notifications(user_id)
            self._results = []
            return self

        # 3. Add notification
        if "insert into notifications (" in sql_clean:
            user_id, title, message, created_at = params
            notif_id = firebase_db.add_notification(user_id, title, message)
            self.lastrowid = notif_id
            self._results = []
            return self

        # 4. Fetch notification history
        if "select * from notification_history where user_id = ? order by id desc" in sql_clean:
            user_id = params[0]
            history = firebase_db.get_notification_history(user_id)
            self._results = [MockRow(h) for h in history]
            return self

        if "select status, sent_at, error_message from notification_history where user_id = ? and type = ? order by id desc limit 1" in sql_clean:
            user_id, n_type = params
            history = firebase_db.get_notification_history(user_id)
            filtered = [h for h in history if h.get("type") == n_type]
            self._results = [MockRow(filtered[0])] if filtered else []
            return self

        if "select * from notification_history where id = ?" in sql_clean:
            history_id = params[0]
            hist = firebase_db.get_notification_history_by_id(history_id)
            self._results = [MockRow(hist)] if hist else []
            return self

        # 5. Insert notification history
        if "insert into notification_history" in sql_clean:
            # Matches scheduler or payment verification inserts
            # user_id, bill_id, type, recipient, title, message, status, provider_response, error_message, sent_at
            # Length can vary based on exact query
            user_id = params[0]
            bill_id = params[1]
            n_type = params[2]
            recipient = params[3]
            title = params[4]
            message = params[5]
            status = params[6]
            prov_resp = params[7] if len(params) > 7 else None
            err_msg = params[8] if len(params) > 8 else None
            hist_id = firebase_db.add_notification_history(
                user_id=user_id, bill_id=bill_id, n_type=n_type, recipient=recipient,
                title=title, message=message, status=status, provider_response=prov_resp, error_message=err_msg
            )
            self.lastrowid = hist_id
            self._results = []
            return self

        # 6. Update notification history status (and retry count)
        if "update notification_history set status = ?, provider_response = ?, error_message = ?" in sql_clean:
            status, prov_resp, err_msg = params[0], params[1], params[2]
            if "retry_count = retry_count + 1" in sql_clean:
                history_id = params[3]
                firebase_db.update_notification_history(history_id, status, prov_resp, err_msg, increment_retry=True)
            else:
                history_id = params[3]
                firebase_db.update_notification_history(history_id, status, prov_resp, err_msg, increment_retry=False)
            self._results = []
            return self

        # ----------------- SCHEDULER / DEMO QUERIES -----------------
        if "where b.due_date <= ? and b.payment_status != 'paid'" in sql_clean:
            # scheduler query to evaluate reminders
            due_date_threshold = params[0]
            # Fetch all bills from firebase
            docs = firebase_db.db.collection("bills").where("payment_status", "!=", "Paid").stream()
            results = []
            for doc in docs:
                d = doc.to_dict()
                d["id"] = int(doc.id)
                if d.get("due_date", "") <= due_date_threshold:
                    # Join user and meter details
                    user = firebase_db.get_user_by_id(d.get("user_id") or firebase_db.get_meter_by_id(d["meter_id"])["user_id"])
                    meter = firebase_db.get_meter_by_id(d["meter_id"])
                    # Combine fields
                    row_data = {
                        "bill_id": d["id"],
                        "bill_amount": d.get("bill_amount", d.get("amount")),
                        "amount_paid": d.get("amount_paid", 0.0),
                        "remaining_amount": d.get("remaining_amount"),
                        "due_date": d.get("due_date"),
                        "billing_month": d.get("billing_month"),
                        "meter_id": d["meter_id"],
                        "service_number": meter.get("service_number"),
                        "board_name": meter.get("board_name"),
                        "user_id": user["id"],
                        "user_name": user.get("name"),
                        "user_phone": user.get("phone"),
                        "user_email": user.get("email"),
                        "sms_recipient_phone": user.get("sms_recipient_phone") or user.get("phone") or "",
                        "email_recipient_email": user.get("email_recipient_email") or user.get("email") or "",
                        "sms_reminders": user.get("sms_reminders", 1),
                        "email_reminders": user.get("email_reminders", 1),
                        "whatsapp_reminders": user.get("whatsapp_reminders", 1),
                        "phone_reminders": user.get("phone_reminders", 1)
                    }
                    results.append(MockRow(row_data))
            self._results = results
            return self

        # 7. Predictions queries (next bill prediction)
        if "where meter_id = ? order by id desc" in sql_clean:
            meter_id = params[0]
            docs = firebase_db.db.collection("bills").where("meter_id", "==", int(meter_id)).stream()
            bills = []
            for doc in docs:
                d = doc.to_dict()
                d["id"] = int(doc.id)
                bills.append(d)
            bills.sort(key=lambda x: x["id"], reverse=True)
            self._results = [MockRow(b) for b in bills]
            return self

        # Fallback/Uncaught
        logger.warning(f"UNHANDLED SQL QUERY IN MOCK: {sql_clean} | Params: {params}")
        self._results = []
        return self

    def fetchone(self) -> Optional[MockRow]:
        if self._results:
            return self._results[0]
        return None

    def fetchall(self) -> List[MockRow]:
        return self._results

    def cursor(self):
        return self

    def commit(self):
        pass

    def close(self):
        pass

class MockConnection:
    def __init__(self):
        self.row_factory = None

    def cursor(self) -> MockCursor:
        return MockCursor()

    def execute(self, sql: str, params: tuple = ()) -> MockCursor:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        pass

    def close(self):
        pass

def connect(database: str, *args, **kwargs) -> MockConnection:
    return MockConnection()

class OperationalError(Exception):
    pass

class IntegrityError(Exception):
    pass
