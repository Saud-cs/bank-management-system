import requests
import os
import csv
import re
import hashlib
import logging
from datetime import datetime, timedelta
from decimal import Decimal
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog, scrolledtext
import mysql.connector
from mysql.connector import Error, IntegrityError
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


DB_HOST = "localhost"
DB_USER = "root"
DB_PASS = "hello"  
DB_NAME = "bankdb"
DB_PORT = 3306

ADMIN_PASSWORD_FILE = "admin.pass"
LOG_FILE = "bank_operations.log"

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")


COLORS = {
    'primary': '#2C3E50',      
    'secondary': '#3498DB',    
    'success': '#27AE60',      
    'danger': '#E74C3C',       
    'warning': '#F39C12',      
    'info': '#16A085',         
    'light': '#ECF0F1',        
    'dark': '#34495E',         
    'bg': '#F8F9FA',           
    'accent': '#9B59B6',       
    'highlight': '#E8F4F8'     
}


def load_admin_password_hash():
    if os.path.exists(ADMIN_PASSWORD_FILE):
        try:
            with open(ADMIN_PASSWORD_FILE, "r") as f:
                return f.read().strip()
        except Exception:
            pass
    return hashlib.sha256("admin123".encode()).hexdigest()

def save_admin_password_hash(h):
    with open(ADMIN_PASSWORD_FILE, "w") as f:
        f.write(h)

def sha256_hash(s: str):
    return hashlib.sha256(s.encode()).hexdigest()

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    pattern = r'^\+?[0-9]{10,15}$'
    return re.match(pattern, phone) is not None




GEMINI_API_KEY = "your_gemeni_api_key"

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

class BankingAIAssistant:
    
    def __init__(self):
        self.conversation_history = []
        self.system_prompt = """
You are a professional banking assistant for a Bank Management System. 
Your role is to help with banking-related queries ONLY. You can provide information about:

- Account types (Savings, Current, Business)
- Banking transactions (deposits, withdrawals, transfers)
- Account management and features
- Banking terminology and concepts
- Interest rates and fees
- Financial planning and savings advice
- Security and fraud prevention
- General banking procedures

IMPORTANT RESTRICTIONS:
1. ONLY answer banking and finance-related questions
2. If asked about non-banking topics, politely redirect to banking matters
3. Do not provide specific account information or perform transactions
4. Keep responses concise and professional
5. If unsure, admit it rather than providing incorrect information
"""

    def get_response(self, user_query):
        """
        Robust call to the Gemini generateContent endpoint.
        - Validates response shapes (handles multiple possible shapes)
        - Catches all exceptions to avoid crashing the backend
        - Returns a short error message on failure (so UI won't hang)
        """
        self.conversation_history.append({"role": "user", "content": user_query})

        full_prompt = self.system_prompt + "\n\n"
        for msg in self.conversation_history[-10:]:
            full_prompt += f"{msg['role'].capitalize()}: {msg['content']}\n"

        payload = {
            "contents": [
                {"parts": [{"text": full_prompt}]}
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 250
            }
        }

        headers = {"Content-Type": "application/json"}
        api_key = os.environ.get("GEMINI_API_KEY") or GEMINI_API_KEY
        url = f"{GEMINI_API_URL}?key={api_key}"

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            return f"Error connecting to AI service: {e}"

        try:
            result = resp.json()
        except Exception as e:
            return f"AI returned non-JSON response: {e}"
        answer = None
        try:
            if isinstance(result, dict) and 'candidates' in result and result['candidates']:
                cand = result['candidates'][0]
                if isinstance(cand, dict):
                    content = cand.get('content') or cand.get('message') or {}
                    if isinstance(content, list) and content:
                        part0 = content[0]
                        if isinstance(part0, dict) and 'parts' in part0:
                            parts = part0.get('parts') or []
                            if parts and isinstance(parts, list) and 'text' in parts[0]:
                                answer = parts[0].get('text')
                        elif isinstance(part0, dict) and 'text' in part0:
                            answer = part0.get('text')
                    elif isinstance(content, dict):
                        parts = content.get('parts') or []
                        if parts and isinstance(parts, list):
                            if isinstance(parts[0], dict) and 'text' in parts[0]:
                                answer = parts[0].get('text')

            
            if not answer and isinstance(result, dict) and 'output' in result:
                out = result['output']
                if isinstance(out, list) and out:
                    for o in out:
                        if isinstance(o, dict):
                            if 'content' in o:
                                cont = o['content']
                                if isinstance(cont, list):
                                    for p in cont:
                                        if isinstance(p, dict) and (p.get('type') == 'output_text' or 'text' in p):
                                            answer = p.get('text') or p.get('text')
                                            if answer:
                                                break
                            if 'text' in o and not answer:
                                answer = o.get('text')
                        if answer:
                            break

            
            if not answer and isinstance(result, dict) and 'candidates' in result and result['candidates']:
                try:
                    answer = str(result['candidates'][0])[:2000]
                except Exception:
                    answer = None

            if not answer:
                answer = str(result)[:2000]

            answer = answer.strip() if isinstance(answer, str) else None
            if not answer:
                return "AI returned an empty response."

            self.conversation_history.append({"role": "assistant", "content": answer})
            return answer

        except Exception as e:
            return f"Error parsing AI response: {e}"


class BankDB:
    def __init__(self, host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME, port=DB_PORT):
        try:
            self.conn = mysql.connector.connect(
                host=host, user=user, password=password, database=database, port=port
            )
            self.conn.autocommit = False
        except mysql.connector.Error as e:
            raise RuntimeError(f"Database connection failed: {e}")

    def close(self):
        try:
            if self.conn.is_connected():
                self.conn.close()
        except Exception:
            pass

    def _get_next_auto_increment(self, table="accounts"):
        cur = self.conn.cursor()
        try:
            cur.execute(
                "SELECT AUTO_INCREMENT FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
                (self.conn.database, table)
            )
            r = cur.fetchone()
            return int(r[0]) if r and r[0] else None
        finally:
            cur.close()

    def add_account(self, name, account_number, emirates_id, balance,
                    phone, email, account_type):
        if not re.match(r'^\d{3}-\d{4}-\d{7}-\d{1}$', emirates_id):
            raise ValueError("Invalid Emirates ID format (XXX-XXXX-XXXXXXX-X)")

        acct_no = account_number.strip() if account_number and account_number.strip() else None
        if not acct_no:
            next_ai = self._get_next_auto_increment("accounts")
            if next_ai:
                acct_no = f"AC{next_ai:08d}"
            else:
                acct_no = f"AC{int(datetime.utcnow().timestamp()):010d}"

        cur = self.conn.cursor()
        try:
            cur.execute(
                """INSERT INTO accounts 
                   (name, account_number, emirates_id, balance, phone, email, account_type, status, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                (name, acct_no, emirates_id, float(balance), phone or None, email or None, account_type, "Active")
            )
            last_id = cur.lastrowid
            self.conn.commit()
            logging.info(f"Account created: {acct_no} (id={last_id}) by admin")
            return last_id, acct_no
        except IntegrityError as ie:
            self.conn.rollback()
            raise
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def update_account(self, acc_id, name, account_number, emirates_id, phone, email, account_type, status):
        cur = self.conn.cursor()
        try:
            cur.execute(
                """UPDATE accounts SET name=%s, account_number=%s, emirates_id=%s,
                   phone=%s, email=%s, account_type=%s, status=%s, last_transaction_date=last_transaction_date
                   WHERE id=%s""",
                (name, account_number, emirates_id, phone or None, email or None, account_type, status, acc_id)
            )
            self.conn.commit()
            logging.info(f"Account updated: id={acc_id} by admin")
        except IntegrityError:
            self.conn.rollback()
            raise
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def delete_account(self, acc_id):
        cur = self.conn.cursor()
        try:
            cur.execute("DELETE FROM accounts WHERE id=%s", (acc_id,))
            self.conn.commit()
            logging.warning(f"Account deleted: id={acc_id} by admin")
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def get_accounts(self, filters=None):
        sql = ("SELECT id, account_number, name, emirates_id, balance, account_type, status, created_at "
               "FROM accounts")
        params = []
        where = []

        if filters:
            search = filters.get("search")
            search_col = filters.get("search_col")
            if search:
                if search_col in ("name", "account_number", "emirates_id"):
                    where.append(f"{search_col} LIKE %s")
                    params.append(f"%{search}%")
                else:
                    where.append("(name LIKE %s OR account_number LIKE %s OR emirates_id LIKE %s)")
                    params.extend([f"%{search}%"] * 3)

            if filters.get("status"):
                where.append("status=%s"); params.append(filters["status"])
            if filters.get("account_type"):
                where.append("account_type=%s"); params.append(filters["account_type"])
            if filters.get("date_from"):
                where.append("created_at >= %s"); params.append(filters["date_from"])
            if filters.get("date_to"):
                where.append("created_at <= %s"); params.append(filters["date_to"])
            if filters.get("balance_min"):
                where.append("balance >= %s"); params.append(filters["balance_min"])
            if filters.get("balance_max"):
                where.append("balance <= %s"); params.append(filters["balance_max"])

        if where:
            sql += " WHERE " + " AND ".join(where)

        sql += " ORDER BY created_at DESC LIMIT 1000"

        cur = self.conn.cursor()
        try:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            return rows
        finally:
            cur.close()

    def get_account(self, acc_id):
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT id, account_number, name, emirates_id, balance, phone, email, account_type, status, created_at FROM accounts WHERE id=%s", (acc_id,))
            return cur.fetchone()
        finally:
            cur.close()

    def change_balance(self, acc_id, amount, trans_type="manual", note=None):
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT balance FROM accounts WHERE id=%s FOR UPDATE", (acc_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("Account not found")
            bal = float(row[0])
            new_bal = bal + float(amount)
            if new_bal < 0:
                raise ValueError("Insufficient funds")
            cur.execute("UPDATE accounts SET balance=%s, last_transaction_date=NOW() WHERE id=%s", (round(new_bal, 2), acc_id))
            try:
                cur.execute(
                    "INSERT INTO transactions (account_id, amount, type, note, created_at) VALUES (%s,%s,%s,%s,NOW())",
                    (acc_id, amount, trans_type, note)
                )
            except Exception:
                pass
            self.conn.commit()
            logging.info(f"Balance changed for account id={acc_id}: {amount:+.2f} new={new_bal:.2f}")
            return new_bal
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def get_transactions(self, acc_id=None, limit=200, date_from=None, date_to=None):
        cur = self.conn.cursor()
        try:
            sql = "SELECT id, account_id, amount, type, note, created_at FROM transactions"
            params = []
            where = []
            if acc_id:
                where.append("account_id=%s"); params.append(acc_id)
            if date_from:
                where.append("created_at >= %s"); params.append(date_from)
            if date_to:
                where.append("created_at <= %s"); params.append(date_to)
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY created_at DESC LIMIT %s"; params.append(limit)
            cur.execute(sql, tuple(params))
            return cur.fetchall()
        except Exception:
            return []
        finally:
            cur.close()

    def get_statistics(self):
        cur = self.conn.cursor()
        try:
            stats = {}
            cur.execute("SELECT COUNT(*), SUM(balance), AVG(balance) FROM accounts WHERE status='Active'")
            row = cur.fetchone()
            stats['total_accounts'] = row[0] or 0
            stats['total_balance'] = float(row[1] or 0)
            stats['avg_balance'] = float(row[2] or 0)
            
            cur.execute("SELECT COUNT(*) FROM accounts WHERE status='Frozen'")
            stats['frozen_accounts'] = cur.fetchone()[0] or 0
            
            cur.execute("SELECT COUNT(*) FROM accounts WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)")
            stats['new_accounts_30d'] = cur.fetchone()[0] or 0
            
            cur.execute("SELECT account_type, COUNT(*) FROM accounts GROUP BY account_type")
            stats['by_type'] = dict(cur.fetchall())
            
            return stats
        except Exception as e:
            return {}
        finally:
            cur.close()

    def export_accounts_csv(self, filename, filters=None):
        rows = self.get_accounts(filters=filters)
        headers = ["id", "account_number", "name", "emirates_id", "balance", "account_type", "status", "created_at"]
        with open(filename, "w", newline='', encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for r in rows:
                r = list(r)
                try:
                    r[4] = f"{float(r[4]):.2f}"
                except Exception:
                    pass
                w.writerow(r)
        logging.info(f"Accounts exported to CSV: {filename}")

    def export_transactions_csv(self, filename, acc_id=None, date_from=None, date_to=None):
        rows = self.get_transactions(acc_id=acc_id, date_from=date_from, date_to=date_to, limit=10000)
        headers = ["id", "account_id", "amount", "type", "note", "created_at"]
        with open(filename, "w", newline='', encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for r in rows:
                w.writerow(r)
        logging.info(f"Transactions exported to CSV: {filename}")

    def transfer_funds(self, from_acc_id, to_acc_id, amount, note=None):
        """Transfer funds between accounts"""
        cur = self.conn.cursor()
        try:
    
            cur.execute("SELECT balance FROM accounts WHERE id=%s FOR UPDATE", (from_acc_id,))
            from_bal = cur.fetchone()
            if not from_bal:
                raise ValueError("Source account not found")
            
            cur.execute("SELECT balance FROM accounts WHERE id=%s FOR UPDATE", (to_acc_id,))
            to_bal = cur.fetchone()
            if not to_bal:
                raise ValueError("Destination account not found")
            
            from_balance = float(from_bal[0])
            to_balance = float(to_bal[0])
            
            if from_balance < amount:
                raise ValueError("Insufficient funds in source account")
            

            new_from = from_balance - amount
            new_to = to_balance + amount
            
            cur.execute("UPDATE accounts SET balance=%s, last_transaction_date=NOW() WHERE id=%s", 
                       (round(new_from, 2), from_acc_id))
            cur.execute("UPDATE accounts SET balance=%s, last_transaction_date=NOW() WHERE id=%s", 
                       (round(new_to, 2), to_acc_id))
            

            try:
                cur.execute(
                    "INSERT INTO transactions (account_id, amount, type, note, created_at) VALUES (%s,%s,%s,%s,NOW())",
                    (from_acc_id, -amount, "transfer_out", note or f"Transfer to account {to_acc_id}")
                )
                cur.execute(
                    "INSERT INTO transactions (account_id, amount, type, note, created_at) VALUES (%s,%s,%s,%s,NOW())",
                    (to_acc_id, amount, "transfer_in", note or f"Transfer from account {from_acc_id}")
                )
            except Exception:
                pass
            
            self.conn.commit()
            logging.info(f"Transfer: {amount:.2f} from account {from_acc_id} to {to_acc_id}")
            return new_from, new_to
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()
    

    def close(self):
        try:
            if self.conn.is_connected():
                self.conn.close()
        except Exception:
            pass

    def create_loan(self, account_id, amount, term_months, rate):
        """Create a loan request (status Pending). Returns loan_id."""
        cur = self.conn.cursor()
        try:
            cur.execute(
                "INSERT INTO loans (account_id, amount, term_months, rate, status) VALUES (%s,%s,%s,%s,%s)",
                (account_id, float(amount), int(term_months), float(rate), "Pending")
            )
            loan_id = cur.lastrowid
            self.conn.commit()
            logging.info(f"Loan request created: loan_id={loan_id} account_id={account_id} amount={amount}")
            return loan_id
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def get_loans(self, account_id = None, status = None, limit=1000):
        cur = self.conn.cursor()
        try:
            sql = "SELECT * FROM loans"
            where = []
            params = []
            if account_id:
                where.append("account_id=%s"); params.append(account_id)
            if status:
                where.append("status=%s"); params.append(status)
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY created_at DESC LIMIT %s"; params.append(limit)
            cur.execute(sql, tuple(params))
            return cur.fetchall()
        finally:
            cur.close()

    def update_loan_status(self, loan_id, new_status, admin_note=None):
        cur = self.conn.cursor()
        try:

            cur.execute("SELECT account_id, amount, status FROM loans WHERE id=%s FOR UPDATE", (loan_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("Loan not found")
            account_id, amount, cur_status = row
            if cur_status == new_status:
                return

            if new_status == "Approved":
       
                self.change_balance(account_id, float(amount), trans_type="loan_disbursement", note=f"Loan #{loan_id} disbursed")
 
            cur.execute("UPDATE loans SET status=%s, updated_at=NOW() WHERE id=%s", (new_status, loan_id))
           
            try:
                cur.execute("INSERT INTO transactions (account_id, amount, type, note, created_at) VALUES (%s,%s,%s,%s,NOW())",
                            (account_id, amount if new_status == "Approved" else 0.0, f"loan_{new_status.lower()}", admin_note))
            except Exception:
                pass
            self.conn.commit()
            logging.info(f"Loan {loan_id} status changed to {new_status} by admin")
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()


    def add_debt(self, account_id, amount, description=None):
        cur = self.conn.cursor()
        try:
            cur.execute("INSERT INTO debts (account_id, amount, description, status) VALUES (%s,%s,%s,%s)",
                        (account_id, float(amount), description, "Open"))
            debt_id = cur.lastrowid
            self.conn.commit()
            logging.info(f"Debt recorded: debt_id={debt_id} account_id={account_id} amount={amount}")
            return debt_id
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def get_debts(self, account_id=None, status=None,limit = 1000):
        cur = self.conn.cursor()
        try:
            sql = "SELECT id, account_id, amount, description, status, created_at FROM debts"
            where = []
            params = []
            if account_id:
                where.append("account_id=%s"); params.append(account_id)
            if status:
                where.append("status=%s"); params.append(status)
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY created_at DESC"
            cur.execute(sql, tuple(params))
            return cur.fetchall()
        finally:
            cur.close()

    def settle_debt(self, debt_id):
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT account_id, amount, status FROM debts WHERE id=%s FOR UPDATE", (debt_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("Debt not found")
            account_id, amount, status = row
            if status == "Settled":
                raise ValueError("Debt already settled")
            
        
            cur.execute("SELECT balance FROM accounts WHERE id=%s FOR UPDATE", (account_id,))
            acc_row = cur.fetchone()
            if not acc_row:
                raise ValueError("Account not found")
            
            current_balance = float(acc_row[0])
            debt_amount = float(amount)
            
            if current_balance < debt_amount:
                raise ValueError(f"Insufficient funds. Balance: ${current_balance:.2f}, Debt: ${debt_amount:.2f}")
            
          
            new_balance = current_balance - debt_amount
            cur.execute("UPDATE accounts SET balance=%s, last_transaction_date=NOW() WHERE id=%s", 
                    (round(new_balance, 2), account_id))
            
            
            cur.execute("UPDATE debts SET status='Settled' WHERE id=%s", (debt_id,))
            
           
            try:
                cur.execute(
                    "INSERT INTO transactions (account_id, amount, type, note, created_at) VALUES (%s,%s,%s,%s,NOW())",
                    (account_id, -debt_amount, "debt_payment", f"Debt #{debt_id} settled")
                )
            except Exception:
                pass
            
            self.conn.commit()
            logging.info(f"Debt {debt_id} settled for account {account_id}, amount: ${debt_amount:.2f}")
            return new_balance
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def close(self):
        try:
            if self.conn.is_connected():
                self.conn.close()
        except Exception:
            pass

    def get_statistics(self):
        """Return the same bank statistics as used by the UI (safe to call)."""
        cur = self.conn.cursor()
        try:
            stats = {}
            cur.execute("SELECT COUNT(*), SUM(balance), AVG(balance) FROM accounts WHERE status='Active'")
            row = cur.fetchone()
            stats['total_accounts'] = row[0] or 0
            stats['total_balance'] = float(row[1] or 0)
            stats['avg_balance'] = float(row[2] or 0)

            cur.execute("SELECT COUNT(*) FROM accounts WHERE status='Frozen'")
            stats['frozen_accounts'] = cur.fetchone()[0] or 0

            cur.execute("SELECT COUNT(*) FROM accounts WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)")
            stats['new_accounts_30d'] = cur.fetchone()[0] or 0

            cur.execute("SELECT account_type, COUNT(*) FROM accounts GROUP BY account_type")
            stats['by_type'] = dict(cur.fetchall())

            return stats
        finally:
            cur.close()




class ModernButton(tk.Button):
    def __init__(self, parent, text="", command=None, style="primary", **kwargs):
        color = COLORS.get(style, COLORS['primary'])
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=color,
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            relief=tk.FLAT,
            padx=20,
            pady=8,
            cursor='hand2',
            **kwargs
        )
        self.bind("<Enter>", lambda e: self.config(bg=self._darken_color(color)))
        self.bind("<Leave>", lambda e: self.config(bg=color))
    
    def _darken_color(self, color):
        color = color.lstrip('#')
        r, g, b = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        return f'#{max(0, r-30):02x}{max(0, g-30):02x}{max(0, b-30):02x}'
    

class StyledEntry(ttk.Entry):
    def __init__(self, parent, **kwargs):
        style = ttk.Style()
        style.configure('Styled.TEntry', padding=5)
        super().__init__(parent, style='Styled.TEntry', **kwargs)
    

class AdminAuth:
    def __init__(self):
        self.password_hash = load_admin_password_hash()

    def verify(self, password):
        return sha256_hash(password) == self.password_hash

    def change_password(self, new_password):
        h = sha256_hash(new_password)
        save_admin_password_hash(h)
        self.password_hash = h
        logging.info("Admin password changed")

class BankApp(tk.Tk):
    def __init__(self, db: BankDB):
        super().__init__()
        self.db = db
        self.selected_id = None
        self.ai_assistant = BankingAIAssistant()
        
        if not self._verify_admin():
            self.destroy()
            return
        
        self.title(" Bank Management System - Admin Dashboard")
        self.geometry("1400x800")
        self.configure(bg=COLORS['bg'])
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        

        self._apply_theme()
        self._build_ui()
        self._refresh_tree()
        self._update_dashboard()

    def _open_ai_chat(self):
        chat_win = tk.Toplevel(self)
        chat_win.title("🤖 AI Assistant")
        chat_win.geometry("700x600")
        chat_win.configure(bg='white')
        
       
        header = tk.Frame(chat_win, bg=COLORS['info'])
        header.pack(fill=tk.X)
        tk.Label(header, text="🤖 AI Assistant", 
                font=('Segoe UI', 14, 'bold'), bg=COLORS['info'], fg='white').pack(pady=15)
        tk.Label(header, text="Ask me anything about banking services!", 
                font=('Segoe UI', 9), bg=COLORS['info'], fg='white').pack(pady=(0, 10))
        
        
        chat_frame = ttk.Frame(chat_win)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        chat_display = scrolledtext.ScrolledText(
            chat_frame, 
            wrap=tk.WORD, 
            font=('Segoe UI', 10),
            bg=COLORS['light'],
            relief=tk.FLAT,
            padx=10,
            pady=10
        )
        chat_display.pack(fill=tk.BOTH, expand=True)
        chat_display.config(state=tk.DISABLED)
        
        
        chat_display.tag_config('user', foreground=COLORS['primary'], font=('Segoe UI', 10, 'bold'))
        chat_display.tag_config('ai', foreground=COLORS['info'], font=('Segoe UI', 10))
        chat_display.tag_config('timestamp', foreground='gray', font=('Segoe UI', 8))
        
        # Input area
        input_frame = ttk.Frame(chat_win)
        input_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        input_entry = tk.Text(input_frame, height=3, font=('Segoe UI', 10), wrap=tk.WORD)
        input_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        def send_message(event=None):
            user_input = input_entry.get("1.0", tk.END).strip()
            if not user_input:
                return "break"
            
         
            chat_display.config(state=tk.NORMAL)
            timestamp = datetime.now().strftime("%H:%M")
            chat_display.insert(tk.END, f"\n[{timestamp}] ", 'timestamp')
            chat_display.insert(tk.END, "You: ", 'user')
            chat_display.insert(tk.END, f"{user_input}\n")
            chat_display.see(tk.END)
            chat_display.config(state=tk.DISABLED)
            
          
            input_entry.delete("1.0", tk.END)
            
            
            chat_display.config(state=tk.NORMAL)
            chat_display.insert(tk.END, "🤖 AI is thinking...\n", 'AI')
            chat_display.see(tk.END)
            chat_display.config(state=tk.DISABLED)
            chat_win.update()
            
            
            ai_response = self.ai_assistant.get_response(user_input)
            
           
            chat_display.config(state=tk.NORMAL)
            chat_display.delete("end-2l", "end-1l") 
            chat_display.insert(tk.END, f"[{timestamp}] ", 'timestamp')
            chat_display.insert(tk.END, "🤖 Assistant: ", 'AI')
            chat_display.insert(tk.END, f"{ai_response}\n")
            chat_display.see(tk.END)
            chat_display.config(state=tk.DISABLED)
            
            return "break" 
        
        input_entry.bind('<Return>', lambda e: send_message() if not e.state & 0x1 else None)
        input_entry.bind('<Shift-Return>', lambda e: None) 
        
        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y)
        ModernButton(btn_frame, text="Send", command=send_message, style="success").pack(pady=2)
        ModernButton(btn_frame, text="Clear", 
                    command=lambda: (chat_display.config(state=tk.NORMAL), 
                                chat_display.delete("1.0", tk.END),
                                chat_display.config(state=tk.DISABLED)), 
                    style="secondary").pack(pady=2)
        
      
        chat_display.config(state=tk.NORMAL)
        welcome = """Welcome to AI Banking Assistant! 🏦

    I can help you with:
    - Account types and features
    - Transaction procedures
    - Banking terminology
    - Financial advice
    - Security tips
    - And more banking topics!

    How can I assist you today?"""
        chat_display.insert(tk.END, welcome, 'ai')
        chat_display.config(state=tk.DISABLED)
        
        input_entry.focus()

    def _apply_theme(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('TFrame', background=COLORS['bg'])
        style.configure('TLabel', background=COLORS['bg'], font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI', 14, 'bold'), foreground=COLORS['primary'])
        style.configure('Card.TFrame', background='white', relief=tk.RAISED)
        style.configure('Treeview', font=('Segoe UI', 9), rowheight=25)
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'), background=COLORS['primary'], 
                       foreground='white')
        
        style.map('Treeview',
                 background=[('selected', COLORS['secondary'])],
                 foreground=[('selected', 'white')])

    def _on_close(self):
        try:
            self.db.close()
        finally:
            self.destroy()

    def _verify_admin(self):
        auth = AdminAuth()
        dialog = tk.Toplevel()
        dialog.title("🔐 Admin Authentication")
        dialog.geometry("400x250")
        dialog.configure(bg='white')
        dialog.transient(self)
        dialog.grab_set()
        

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        result = {'authenticated': False}
        
        ttk.Label(dialog, text="🏦 Bank Management System", 
                 font=('Segoe UI', 16, 'bold'), background='white').pack(pady=20)
        ttk.Label(dialog, text="Admin Login Required", 
                 font=('Segoe UI', 11), background='white').pack(pady=10)
        
        pwd_frame = ttk.Frame(dialog)
        pwd_frame.pack(pady=20)
        ttk.Label(pwd_frame, text="Password:", background='white').pack()
        pwd_entry = ttk.Entry(pwd_frame, show="●", width=30)
        pwd_entry.pack(pady=5)
        pwd_entry.focus()
        
        def check_auth():
            if auth.verify(pwd_entry.get()):
                result['authenticated'] = True
                dialog.destroy()
            else:
                messagebox.showerror("Access Denied", "Invalid credentials", parent=dialog)
        
        pwd_entry.bind('<Return>', lambda e: check_auth())
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ModernButton(btn_frame, text="Login", command=check_auth, style="success").pack(side=tk.LEFT, padx=5)
        ModernButton(btn_frame, text="Cancel", command=dialog.destroy, style="danger").pack(side=tk.LEFT, padx=5)
        
        dialog.wait_window()
        return result['authenticated']

    def _build_ui(self):
        main_container = ttk.Frame(self)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        

        dashboard_frame = ttk.Frame(main_container)
        dashboard_frame.pack(fill=tk.X, pady=(0, 10))
        self._build_dashboard(dashboard_frame)
        

        content = ttk.Frame(main_container)
        content.pack(fill=tk.BOTH, expand=True)
        

        left_panel = ttk.Frame(content, style='Card.TFrame', relief=tk.RAISED, borderwidth=1)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self._build_form(left_panel)
        
     
        right_panel = ttk.Frame(content)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self._build_table_area(right_panel)
        
        self._build_menu()
        
 
        self.status_var = tk.StringVar(value="  Ready")
        status_bar = tk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, 
                             anchor=tk.W, bg=COLORS['primary'], fg='white', 
                             font=('Segoe UI', 9), padx=10, pady=5)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _build_dashboard(self, parent):
        ttk.Label(parent, text="    Dashboard Overview", style='Title.TLabel').pack(anchor=tk.W, pady=(0, 10))
        
        cards_frame = ttk.Frame(parent)
        cards_frame.pack(fill=tk.X)
        

        self.cards = {}
        card_info = [
            ('total_accounts', 'Total Accounts', '👥', 'info'),
            ('total_balance', 'Total Balance', '💰', 'success'),
            ('avg_balance', 'Avg Balance', '📈', 'secondary'),
            ('frozen_accounts', 'Frozen', '❄️', 'warning'),
            ('new_accounts', 'New (30d)', '✨', 'accent')
        ]
        
        for i, (key, title, icon, color) in enumerate(card_info):
            card = self._create_dashboard_card(cards_frame, title, "0", icon, color)
            card.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
            self.cards[key] = card

    def _create_dashboard_card(self, parent, title, value, icon, color):
        frame = tk.Frame(parent, bg='white', relief=tk.RAISED, borderwidth=2)
        frame.configure(highlightbackground=COLORS[color], highlightthickness=3)
        
        tk.Label(frame, text=icon, font=('Segoe UI', 24), bg='white', 
                fg=COLORS[color]).pack(pady=(10, 0))
        tk.Label(frame, text=title, font=('Segoe UI', 9), bg='white', 
                fg=COLORS['dark']).pack()
        value_label = tk.Label(frame, text=value, font=('Segoe UI', 16, 'bold'), 
                              bg='white', fg=COLORS[color])
        value_label.pack(pady=(0, 10))
        
        frame.value_label = value_label
        return frame

    def _update_dashboard(self):
        stats = self.db.get_statistics()
        self.cards['total_accounts'].value_label.config(text=str(stats.get('total_accounts', 0)))
        self.cards['total_balance'].value_label.config(text=f"${stats.get('total_balance', 0):,.2f}")
        self.cards['avg_balance'].value_label.config(text=f"${stats.get('avg_balance', 0):,.2f}")
        self.cards['frozen_accounts'].value_label.config(text=str(stats.get('frozen_accounts', 0)))
        self.cards['new_accounts'].value_label.config(text=str(stats.get('new_accounts_30d', 0)))

    def _build_form(self, parent):
 
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, padx=15, pady=15)
        ttk.Label(header, text="📝 Account Management", style='Title.TLabel').pack(anchor=tk.W)
        

        form = ttk.Frame(parent)
        form.pack(fill=tk.BOTH, expand=True, padx=15)
        
        fields = [
            ("Account Number:", "ent_accno", "Leave blank for auto-generation"),
            ("Full Name: *", "ent_name", ""),
            ("Emirates ID: *", "ent_eid", "XXX-XXXX-XXXXXXX-X"),
            ("Phone:", "ent_phone", "+971XXXXXXXXX"),
            ("Email:", "ent_email", "example@email.com"),
            ("Initial Deposit:", "ent_init", "0.00"),
        ]
        
        for i, (label, attr, placeholder) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky=tk.W, pady=5)
            entry = StyledEntry(form, width=25)
            entry.grid(row=i, column=1, pady=5, sticky=tk.EW)
            if placeholder:
                entry.insert(0, placeholder)
                entry.config(foreground='gray')
                entry.bind('<FocusIn>', lambda e, ent=entry, ph=placeholder: self._clear_placeholder(ent, ph))
                entry.bind('<FocusOut>', lambda e, ent=entry, ph=placeholder: self._restore_placeholder(ent, ph))
            setattr(self, attr, entry)
        
        form.columnconfigure(1, weight=1)
        

        ttk.Label(form, text="Account Type:").grid(row=len(fields), column=0, sticky=tk.W, pady=5)
        self.ent_type = ttk.Combobox(form, values=["Savings", "Current", "Business"], state="readonly", width=23)
        self.ent_type.grid(row=len(fields), column=1, pady=5, sticky=tk.EW)
        self.ent_type.set("Savings")
        
        ttk.Label(form, text="Status:").grid(row=len(fields)+1, column=0, sticky=tk.W, pady=5)
        self.ent_status = ttk.Combobox(form, values=["Active", "Frozen", "Closed"], state="readonly", width=23)
        self.ent_status.grid(row=len(fields)+1, column=1, pady=5, sticky=tk.EW)
        self.ent_status.set("Active")
        

        btn_frame = ttk.Frame(form)
        btn_frame.grid(row=len(fields)+2, column=0, columnspan=2, pady=20)
        
        ModernButton(btn_frame, text="➕ Create", command=self.create_account, 
                    style="success", width=10).pack(side=tk.LEFT, padx=2)
        ModernButton(btn_frame, text="💾 Update", command=self.update_account, 
                    style="info", width=10).pack(side=tk.LEFT, padx=2)
        ModernButton(btn_frame, text="🗑️ Delete", command=self.delete_account, 
                    style="danger", width=10).pack(side=tk.LEFT, padx=2)
        ModernButton(btn_frame, text="🔄 Clear", command=self.clear_form, 
                    style="secondary", width=10).pack(side=tk.LEFT, padx=2)
        
 
        trans_frame = tk.LabelFrame(form, text="⚡ Quick Actions", bg='white', 
                                   font=('Segoe UI', 10, 'bold'), fg=COLORS['primary'])
        trans_frame.grid(row=len(fields)+3, column=0, columnspan=2, pady=10, sticky=tk.EW)
        
        ModernButton(trans_frame, text="🔄 Transfer", command=self.transfer, 
                    style="info", width=12).pack(pady=5, padx=10)
        ModernButton(trans_frame, text="  Transactions", command=self.view_transactions, 
                    style="secondary", width=12).pack(pady=5, padx=10)
        ModernButton(trans_frame, text="❄️ Freeze", command=self.freeze_account, 
                    style="accent", width=12).pack(pady=5, padx=10)

        ModernButton(trans_frame, text="🤖 AI Assistant", command=self._open_ai_chat, 
                    style="accent", width=12).pack(pady=5, padx=10)

    def _clear_placeholder(self, entry, placeholder):
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(foreground='black')

    def _restore_placeholder(self, entry, placeholder):
        if not entry.get():
            entry.insert(0, placeholder)
            entry.config(foreground='gray')

    def _build_table_area(self, parent):

        search_frame = tk.Frame(parent, bg='white', relief=tk.RAISED, borderwidth=1)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(search_frame, text="🔍 Search:", background='white', 
                 font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT, padx=10)
        
        self.ent_search = StyledEntry(search_frame, width=30)
        self.ent_search.pack(side=tk.LEFT, padx=5, pady=10)
        self.ent_search.bind('<Return>', lambda e: self.search())
        
        self.search_by = ttk.Combobox(search_frame, values=["Any", "Name", "Account", "Emirates ID"], 
                                     width=12, state="readonly")
        self.search_by.set("Any")
        self.search_by.pack(side=tk.LEFT, padx=5)
        
        ModernButton(search_frame, text="Search", command=self.search, 
                    style="secondary").pack(side=tk.LEFT, padx=5)
        ModernButton(search_frame, text="🔄 Refresh", command=self._refresh_tree, 
                    style="info").pack(side=tk.LEFT, padx=5)
        ModernButton(search_frame, text="🔧 Advanced", command=self._advanced_search, 
                    style="accent").pack(side=tk.LEFT, padx=5)
        

        table_container = tk.Frame(parent, bg='white', relief=tk.RAISED, borderwidth=1)
        table_container.pack(fill=tk.BOTH, expand=True)
        
  
        tree_frame = ttk.Frame(table_container)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
  
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        cols = ("id", "account_number", "name", "emirates_id", "balance", "account_type", "status", "created_at")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", 
                                selectmode="browse", yscrollcommand=vsb.set, 
                                xscrollcommand=hsb.set)
        
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        

        col_config = {
            "id": ("ID", 60, tk.CENTER),
            "account_number": ("Account No.", 120, tk.W),
            "name": ("Name", 150, tk.W),
            "emirates_id": ("Emirates ID", 150, tk.W),
            "balance": ("Balance", 100, tk.E),
            "account_type": ("Type", 90, tk.CENTER),
            "status": ("Status", 80, tk.CENTER),
            "created_at": ("Created", 150, tk.W)
        }
        
        for col, (text, width, anchor) in col_config.items():
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=anchor)
        

        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
   
        self.tree.tag_configure('evenrow', background=COLORS['highlight'])
        self.tree.tag_configure('oddrow', background='white')

    def _build_menu(self):
        menubar = tk.Menu(self, bg=COLORS['primary'], fg='white')
        

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="    Export All Accounts", command=self._export_all_accounts)
        file_menu.add_command(label="    Export Filtered", command=self._export_filtered_accounts)
        file_menu.add_command(label="    Export Transactions", command=self._export_transactions_selected)
        file_menu.add_separator()
        file_menu.add_command(label="  Generate Report", command=self._generate_report)
        file_menu.add_separator()
        file_menu.add_command(label="🚪 Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        

        admin_menu = tk.Menu(menubar, tearoff=0)
        admin_menu.add_command(label="🔑 Change Password", command=self._change_admin_password)
        admin_menu.add_command(label="📜 View Logs", command=self._view_logs)
        admin_menu.add_separator()
        admin_menu.add_command(label="    Statistics Dashboard", command=self._show_statistics)
        menubar.add_cascade(label="Admin", menu=admin_menu)
        
   
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="🔍 Advanced Search", command=self._advanced_search)
        tools_menu.add_command(label="    Account Analytics", command=self._show_analytics)
        tools_menu.add_command(label="💱 Bulk Transfer", command=self._bulk_operations)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="❓ Help", command=self._show_help)
        help_menu.add_command(label="ℹ️ About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.config(menu=menubar)

    def _set_status(self, s):
        self.status_var.set(s)

    def _refresh_tree(self, rows=None):
        self._set_status("🔄 Refreshing accounts...")
        for r in self.tree.get_children():
            self.tree.delete(r)
        try:
            if rows is None:
                rows = self.db.get_accounts()
            for idx, row in enumerate(rows):
                r = list(row)
                try:
                    r[4] = f"${float(r[4]):,.2f}"
                except Exception:
                    pass
                tag = 'evenrow' if idx % 2 == 0 else 'oddrow'
                self.tree.insert("", tk.END, values=r, tags=(tag,))
            self._set_status(f"  Loaded {len(rows)} accounts")
            self._update_dashboard()
        except Exception as e:
            messagebox.showerror("DB Error", str(e))
            self._set_status("  Error loading accounts")

    def clear_form(self):
        self.selected_id = None
        for name in ("ent_accno", "ent_name", "ent_eid", "ent_phone", "ent_email", "ent_init"):
            w = getattr(self, name, None)
            if w:
                w.delete(0, tk.END)
                w.config(foreground='black')
        

        placeholders = {
            'ent_accno': 'Leave blank for auto-generation',
            'ent_eid': 'XXX-XXXX-XXXXXXX-X',
            'ent_phone': '+971XXXXXXXXX',
            'ent_email': 'example@email.com',
            'ent_init': '0.00'
        }
        for name, ph in placeholders.items():
            w = getattr(self, name, None)
            if w:
                w.insert(0, ph)
                w.config(foreground='gray')
        
        self.ent_type.set("Savings")
        self.ent_status.set("Active")
        try:
            self.tree.selection_remove(self.tree.selection())
        except Exception:
            pass

    def on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        if not vals:
            return
        
        self.selected_id = int(vals[0])
        
     
        try:
            acc = self.db.get_account(self.selected_id)
            if acc:
          
                for name in ("ent_accno", "ent_name", "ent_eid", "ent_phone", "ent_email", "ent_init"):
                    w = getattr(self, name, None)
                    if w:
                        w.delete(0, tk.END)
                        w.config(foreground='black')
                
                self.ent_accno.insert(0, acc[1] or "")
                self.ent_name.insert(0, acc[2] or "")
                self.ent_eid.insert(0, acc[3] or "")
                self.ent_phone.insert(0, acc[5] or "")
                self.ent_email.insert(0, acc[6] or "")
                self.ent_init.insert(0, f"{float(acc[4]):.2f}")
                self.ent_type.set(acc[7])
                self.ent_status.set(acc[8])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load account details: {e}")

    def create_account(self):
        name = self.ent_name.get().strip()
        acc_no = self.ent_accno.get().strip()
        eid = self.ent_eid.get().strip()
        phone = self.ent_phone.get().strip()
        email = self.ent_email.get().strip()
        

        if acc_no == 'Leave blank for auto-generation':
            acc_no = ""
        if eid == 'XXX-XXXX-XXXXXXX-X':
            eid = ""
        if phone == '+971XXXXXXXXX':
            phone = ""
        if email == 'example@email.com':
            email = ""
        
        acct_type = self.ent_type.get()
        
        try:
            balance_str = self.ent_init.get()
            if balance_str == '0.00':
                balance = 0.0
            else:
                balance = float(balance_str)
        except Exception:
            messagebox.showerror("Invalid Input", "Initial deposit must be a valid number")
            return
        
        if not name or not eid:
            messagebox.showerror("Missing Required Fields", "Name and Emirates ID are required")
            return
        

        if email and not validate_email(email):
            messagebox.showerror("Invalid Email", "Please enter a valid email address")
            return

        if phone and not validate_phone(phone):
            messagebox.showerror("Invalid Phone", "Please enter a valid phone number")
            return
        
        try:
            last_id, used_acc_no = self.db.add_account(name, acc_no, eid, balance, phone, email, acct_type)
            messagebox.showinfo("  Success", f"Account created successfully!\n\nAccount Number: {used_acc_no}\nAccount ID: {last_id}")
            
            self.ent_accno.delete(0, tk.END)
            self.ent_accno.insert(0, used_acc_no)
            self.ent_accno.config(foreground='black')
            
            self._refresh_tree()
            self._set_status(f"  Account {used_acc_no} created")
        except IntegrityError:
            messagebox.showerror("Duplicate Entry", "Account number or Emirates ID already exists in the system")
        except ValueError as ve:
            messagebox.showerror("Validation Error", str(ve))
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to create account: {str(e)}")

    def update_account(self):
        if not self.selected_id:
            messagebox.showerror("No Selection", "Please select an account to update")
            return
        
        try:
            name = self.ent_name.get().strip()
            acc_no = self.ent_accno.get().strip()
            eid = self.ent_eid.get().strip()
            phone = self.ent_phone.get().strip()
            email = self.ent_email.get().strip()
            acct_type = self.ent_type.get()
            status = self.ent_status.get()
            
            if phone == '+971XXXXXXXXX':
                phone = ""
            if email == 'example@email.com':
                email = ""
            
            if email and not validate_email(email):
                messagebox.showerror("Invalid Email", "Please enter a valid email address")
                return

            if phone and not validate_phone(phone):
                messagebox.showerror("Invalid Phone", "Please enter a valid phone number")
                return
            
            self.db.update_account(self.selected_id, name, acc_no, eid, phone, email, acct_type, status)
            messagebox.showinfo("  Success", "Account updated successfully")
            self._refresh_tree()
            self._set_status(f"  Account {acc_no} updated")
        except IntegrityError:
            messagebox.showerror("Duplicate Entry", "Account number or Emirates ID already exists")
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to update account: {str(e)}")

    def delete_account(self):
        if not self.selected_id:
            messagebox.showerror("No Selection", "Please select an account to delete")
            return
        
        if not messagebox.askyesno("caution: Confirm Deletion", 
                                   "Are you sure you want to delete this account?\n\nThis action cannot be undone!",
                                   icon='warning'):
            return
        
        try:
            self.db.delete_account(self.selected_id)
            messagebox.showinfo("  Deleted", "Account deleted successfully")
            self.clear_form()
            self._refresh_tree()
            self._set_status("  Account deleted")
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to delete account: {str(e)}")

    def freeze_account(self):
        if not self.selected_id:
            messagebox.showerror("No Selection", "Please select an account to freeze")
            return
        
        if not messagebox.askyesno("Confirm Freeze", "Freeze this account?"):
            return
        
        try:
            name = self.ent_name.get().strip()
            acc_no = self.ent_accno.get().strip()
            eid = self.ent_eid.get().strip()
            phone = self.ent_phone.get().strip()
            email = self.ent_email.get().strip()
            
            if phone == '+971XXXXXXXXX':
                phone = ""
            if email == 'example@email.com':
                email = ""
            
            self.db.update_account(self.selected_id, name, acc_no, eid, phone, email,
                                 self.ent_type.get(), "Frozen")
            self._refresh_tree()
            self.ent_status.set("Frozen")
            messagebox.showinfo("  Success", "Account frozen successfully")
            self._set_status(f"❄️ Account {acc_no} frozen")
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to freeze account: {str(e)}")

    def transfer(self):

        if not self.selected_id:
            messagebox.showerror("No Selection", "Please select the source account")
            return
        

        dialog = tk.Toplevel(self)
        dialog.title("Transfer Funds")
        dialog.geometry("450x300")
        dialog.configure(bg='white')
        dialog.transient(self)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Transfer Funds", font=('Segoe UI', 14, 'bold'), 
                 background='white').pack(pady=20)
        
        form = ttk.Frame(dialog)
        form.pack(padx=30, fill=tk.BOTH, expand=True)
        
        ttk.Label(form, text="From Account:", background='white').grid(row=0, column=0, sticky=tk.W, pady=5)
        from_label = ttk.Label(form, text=f"ID: {self.selected_id}", font=('Segoe UI', 10, 'bold'), 
                              background='white')
        from_label.grid(row=0, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(form, text="To Account ID:", background='white').grid(row=1, column=0, sticky=tk.W, pady=5)
        to_entry = StyledEntry(form, width=20)
        to_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(form, text="Amount:", background='white').grid(row=2, column=0, sticky=tk.W, pady=5)
        amt_entry = StyledEntry(form, width=20)
        amt_entry.grid(row=2, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(form, text="Note:", background='white').grid(row=3, column=0, sticky=tk.W, pady=5)
        note_entry = StyledEntry(form, width=20)
        note_entry.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        def do_transfer():
            try:
                to_id = int(to_entry.get())
                amount = float(amt_entry.get())
                note = note_entry.get().strip() or None
                
                if amount <= 0:
                    messagebox.showerror("Invalid Amount", "Amount must be positive", parent=dialog)
                    return
                
                from_bal, to_bal = self.db.transfer_funds(self.selected_id, to_id, amount, note)
                messagebox.showinfo("  Transfer Successful", 
                                  f"Transferred ${amount:,.2f}\n\nFrom Balance: ${from_bal:,.2f}\nTo Balance: ${to_bal:,.2f}",
                                  parent=dialog)
                dialog.destroy()
                self._refresh_tree()
                self._set_status(f"  Transferred ${amount:,.2f}")
            except ValueError:
                messagebox.showerror("Invalid Input", "Please enter valid numbers", parent=dialog)
            except Exception as e:
                messagebox.showerror("Transfer Failed", str(e), parent=dialog)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=20)
        ModernButton(btn_frame, text="  Transfer", command=do_transfer, style="success").pack(side=tk.LEFT, padx=5)
        ModernButton(btn_frame, text="  Cancel", command=dialog.destroy, style="danger").pack(side=tk.LEFT, padx=5)

    def view_transactions(self):
        if not self.selected_id:
            messagebox.showerror("No Selection", "Please select an account to view transactions")
            return
        
        rows = self.db.get_transactions(acc_id=self.selected_id, limit=500)
        
        win = tk.Toplevel(self)
        win.title(f"  Transactions - Account ID {self.selected_id}")
        win.geometry("900x500")
        win.configure(bg='white')
        

        header = tk.Frame(win, bg=COLORS['primary'])
        header.pack(fill=tk.X)
        tk.Label(header, text=f"Transaction History - Account {self.selected_id}", 
                font=('Segoe UI', 12, 'bold'), bg=COLORS['primary'], fg='white').pack(pady=15)
        
        tree_frame = ttk.Frame(win)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        tv = ttk.Treeview(tree_frame, columns=("id", "account_id", "amount", "type", "note", "created_at"), 
                         show="headings", yscrollcommand=vsb.set)
        vsb.config(command=tv.yview)
        
        cols = [("id", "ID", 60), ("account_id", "Account", 80), ("amount", "Amount", 100), 
                ("type", "Type", 100), ("note", "Note", 250), ("created_at", "Date", 150)]
        
        for col, text, width in cols:
            tv.heading(col, text=text)
            tv.column(col, width=width, anchor=tk.W if col != "amount" else tk.E)
        
        tv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        for idx, r in enumerate(rows):
            r_list = list(r)
            try:
                r_list[2] = f"${float(r_list[2]):+,.2f}"
            except:
                pass
            tag = 'evenrow' if idx % 2 == 0 else 'oddrow'
            tv.insert("", tk.END, values=r_list, tags=(tag,))
        
        tv.tag_configure('evenrow', background=COLORS['highlight'])
        tv.tag_configure('oddrow', background='white')
        
   
        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=10)
        ModernButton(btn_frame, text="    Export CSV", 
                    command=lambda: self._export_transactions_window(self.selected_id), 
                    style="info").pack(side=tk.LEFT, padx=5)
        ModernButton(btn_frame, text="  Close", command=win.destroy, style="secondary").pack(side=tk.LEFT, padx=5)

    def search(self):
        term = self.ent_search.get().strip()
        col = self.search_by.get()
        filters = {}
        
        if term:
            if col == "Any":
                filters["search"] = term
            elif col == "Name":
                filters["search"] = term; filters["search_col"] = "name"
            elif col == "Account":
                filters["search"] = term; filters["search_col"] = "account_number"
            elif col == "Emirates ID":
                filters["search"] = term; filters["search_col"] = "emirates_id"
        
        try:
            rows = self.db.get_accounts(filters=filters)
            self._refresh_tree(rows=rows)
            self._set_status(f"🔍 Found {len(rows)} accounts")
        except Exception as e:
            messagebox.showerror("Search Error", str(e))

    def _ask_amount(self, prompt):
        dialog = tk.Toplevel(self)
        dialog.title("Enter Amount")
        dialog.geometry("350x200")
        dialog.configure(bg='white')
        dialog.transient(self)
        dialog.grab_set()
        
        result = {'amount': None}
        
        ttk.Label(dialog, text=prompt, font=('Segoe UI', 11), background='white').pack(pady=20)
        
        amt_entry = StyledEntry(dialog, width=20)
        amt_entry.pack(pady=10)
        amt_entry.focus()
        
        def submit():
            try:
                amt = float(amt_entry.get())
                if amt <= 0:
                    messagebox.showerror("Invalid", "Amount must be positive", parent=dialog)
                    return
                result['amount'] = amt
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Invalid", "Enter a valid number", parent=dialog)
        
        amt_entry.bind('<Return>', lambda e: submit())
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=20)
        ModernButton(btn_frame, text="  OK", command=submit, style="success").pack(side=tk.LEFT, padx=5)
        ModernButton(btn_frame, text="  Cancel", command=dialog.destroy, style="danger").pack(side=tk.LEFT, padx=5)
        
        dialog.wait_window()
        return result['amount']


    def _advanced_search(self):
        """Advanced search dialog with multiple filters"""
        dialog = tk.Toplevel(self)
        dialog.title("🔍 Advanced Search")
        dialog.geometry("500x600")
        dialog.configure(bg='white')
        dialog.transient(self)
        
        ttk.Label(dialog, text="Advanced Search", font=('Segoe UI', 14, 'bold'), 
                 background='white').pack(pady=20)
        
        form = ttk.Frame(dialog)
        form.pack(padx=30, fill=tk.BOTH, expand=True)
        

        ttk.Label(form, text="Search Term:", background='white').grid(row=0, column=0, sticky=tk.W, pady=5)
        search_entry = StyledEntry(form, width=25)
        search_entry.grid(row=0, column=1, pady=5, sticky=tk.EW)
        

        ttk.Label(form, text="Status:", background='white').grid(row=1, column=0, sticky=tk.W, pady=5)
        status_combo = ttk.Combobox(form, values=["All", "Active", "Frozen", "Closed"], state="readonly", width=23)
        status_combo.set("All")
        status_combo.grid(row=1, column=1, pady=5, sticky=tk.EW)
        

        ttk.Label(form, text="Account Type:", background='white').grid(row=2, column=0, sticky=tk.W, pady=5)
        type_combo = ttk.Combobox(form, values=["All", "Savings", "Current", "Business"], state="readonly", width=23)
        type_combo.set("All")
        type_combo.grid(row=2, column=1, pady=5, sticky=tk.EW)
        

        ttk.Label(form, text="Min Balance:", background='white').grid(row=3, column=0, sticky=tk.W, pady=5)
        min_bal_entry = StyledEntry(form, width=25)
        min_bal_entry.grid(row=3, column=1, pady=5, sticky=tk.EW)
        
        ttk.Label(form, text="Max Balance:", background='white').grid(row=4, column=0, sticky=tk.W, pady=5)
        max_bal_entry = StyledEntry(form, width=25)
        max_bal_entry.grid(row=4, column=1, pady=5, sticky=tk.EW)

        ttk.Label(form, text="From Date (YYYY-MM-DD):", background='white').grid(row=5, column=0, sticky=tk.W, pady=5)
        from_date_entry = StyledEntry(form, width=25)
        from_date_entry.grid(row=5, column=1, pady=5, sticky=tk.EW)
        
        ttk.Label(form, text="To Date (YYYY-MM-DD):", background='white').grid(row=6, column=0, sticky=tk.W, pady=5)
        to_date_entry = StyledEntry(form, width=25)
        to_date_entry.grid(row=6, column=1, pady=5, sticky=tk.EW)
        
        form.columnconfigure(1, weight=1)
        
        def do_search():
            filters = {}
            
            search_term = search_entry.get().strip()
            if search_term:
                filters["search"] = search_term
            
            status = status_combo.get()
            if status != "All":
                filters["status"] = status
            
            acc_type = type_combo.get()
            if acc_type != "All":
                filters["account_type"] = acc_type
            
            try:
                min_bal = min_bal_entry.get().strip()
                if min_bal:
                    filters["balance_min"] = float(min_bal)
            except ValueError:
                messagebox.showerror("Invalid Input", "Min balance must be a number", parent=dialog)
                return
            
            try:
                max_bal = max_bal_entry.get().strip()
                if max_bal:
                    filters["balance_max"] = float(max_bal)
            except ValueError:
                messagebox.showerror("Invalid Input", "Max balance must be a number", parent=dialog)
                return
            
            from_date = from_date_entry.get().strip()
            if from_date:
                filters["date_from"] = from_date
            
            to_date = to_date_entry.get().strip()
            if to_date:
                filters["date_to"] = to_date
            
            try:
                rows = self.db.get_accounts(filters=filters)
                self._refresh_tree(rows=rows)
                self._set_status(f"🔍 Advanced search: {len(rows)} results")
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Search Error", str(e), parent=dialog)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=20)
        ModernButton(btn_frame, text="🔍 Search", command=do_search, style="info").pack(side=tk.LEFT, padx=5)
        ModernButton(btn_frame, text="  Cancel", command=dialog.destroy, style="secondary").pack(side=tk.LEFT, padx=5)

    def _show_statistics(self):
        """Show detailed statistics dashboard"""
        stats = self.db.get_statistics()
        
        win = tk.Toplevel(self)
        win.title(" Statistics Dashboard")
        win.geometry("800x600")
        win.configure(bg='white')
        
        header = tk.Frame(win, bg=COLORS['primary'])
        header.pack(fill=tk.X)
        tk.Label(header, text="    Bank Statistics Dashboard", 
                font=('Segoe UI', 14, 'bold'), bg=COLORS['primary'], fg='white').pack(pady=15)
        
        content = ttk.Frame(win)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        

        stats_text = f"""
  ACCOUNT STATISTICS
{'='*50}

Total Active Accounts: {stats.get('total_accounts', 0):,}
Frozen Accounts: {stats.get('frozen_accounts', 0):,}
New Accounts (30 days): {stats.get('new_accounts_30d', 0):,}

💰 FINANCIAL OVERVIEW
{'='*50}

Total Balance: ${stats.get('total_balance', 0):,.2f}
Average Balance: ${stats.get('avg_balance', 0):,.2f}

    ACCOUNT TYPES
{'='*50}
"""
        
        for acc_type, count in stats.get('by_type', {}).items():
            stats_text += f"{acc_type}: {count:,} accounts\n"
        
        text_widget = tk.Text(content, font=('Consolas', 11), wrap=tk.WORD, 
                             bg=COLORS['light'], relief=tk.FLAT, padx=20, pady=20)
        text_widget.pack(fill=tk.BOTH, expand=True)
        text_widget.insert('1.0', stats_text)
        text_widget.config(state=tk.DISABLED)
        
        ModernButton(win, text="  Close", command=win.destroy, style="secondary").pack(pady=10)

# ...existing code...
    def _show_analytics(self):
        """Show account analytics with charts - includes balance distribution and balance vs account index."""
        try:
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        except ImportError:
            messagebox.showerror("Missing Library", "Matplotlib is required for analytics")
            return

        win = tk.Toplevel(self)
        win.title("    Account Analytics")
        win.geometry("1000x700")
        win.configure(bg='white')

        header = tk.Frame(win, bg=COLORS['secondary'])
        header.pack(fill=tk.X)
        tk.Label(header, text="    Account Analytics & Charts",
                 font=('Segoe UI', 14, 'bold'), bg=COLORS['secondary'], fg='white').pack(pady=15)

        stats = self.db.get_statistics()

        # fetch balances from DB
        cur = self.db.conn.cursor()
        try:
            cur.execute("SELECT id, balance FROM accounts WHERE balance IS NOT NULL")
            rows = cur.fetchall()
        finally:
            cur.close()

        ids = []
        balances = []
        for r in rows:
            try:
                ids.append(int(r[0]))
                balances.append(float(r[1] or 0.0))
            except Exception:
                continue

        if not balances:
            messagebox.showinfo("No Data", "No account balance data available for analytics.", parent=win)
            win.destroy()
            return

        fig = Figure(figsize=(10, 6), facecolor='white')

        # Pie: accounts by type (if available)
        ax1 = fig.add_subplot(221)
        by_type = stats.get('by_type', {})
        if by_type:
            colors = [COLORS['secondary'], COLORS['success'], COLORS['warning']]
            ax1.pie(list(by_type.values()), labels=list(by_type.keys()), autopct='%1.1f%%',
                    colors=colors[:len(by_type)], startangle=90)
            ax1.set_title('Accounts by Type', fontweight='bold')
        else:
            ax1.text(0.5, 0.5, "No account-type data", ha='center', va='center')

        # Bar: status distribution
        ax2 = fig.add_subplot(222)
        status_data = {
            'Active': stats.get('total_accounts', 0),
            'Frozen': stats.get('frozen_accounts', 0)
        }
        colors_bar = [COLORS['success'], COLORS['warning']]
        ax2.bar(status_data.keys(), status_data.values(), color=colors_bar)
        ax2.set_title('Account Status Distribution', fontweight='bold')
        ax2.set_ylabel('Count')

        # Histogram: balance distribution
        ax3 = fig.add_subplot(223)
        # sensible bins
        max_bal = max(balances)
        bins = [0, 1000, 5000, 10000, 50000, max(50000, max_bal) * 1.1]
        ax3.hist(balances, bins=bins, color=COLORS['info'], edgecolor='white')
        ax3.set_title('Balance Distribution', fontweight='bold')
        ax3.set_xlabel('Balance')
        ax3.set_ylabel('Number of Accounts')
        ax3.ticklabel_format(style='plain', axis='x')

        # Scatter / line: balance vs account index (sorted)
        ax4 = fig.add_subplot(224)
        sorted_pairs = sorted(zip(ids, balances), key=lambda x: x[0])
        idxs = list(range(1, len(sorted_pairs) + 1))
        sorted_balances = [b for (_, b) in sorted_pairs]
        ax4.plot(idxs, sorted_balances, marker='o', linestyle='-', color=COLORS['accent'])
        ax4.set_title('Balance vs Account (index)', fontweight='bold')
        ax4.set_xlabel('Account (sorted index)')
        ax4.set_ylabel('Balance')
        ax4.grid(alpha=0.3)
        ax4.ticklabel_format(style='plain', axis='y')

        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ModernButton(win, text="  Close", command=win.destroy, style="secondary").pack(pady=10)

    def _bulk_operations(self):
        dialog = tk.Toplevel(self)
        dialog.title("Bulk Transfer")
        dialog.geometry("700x560")
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="Bulk Transfer", font=('Segoe UI', 14, 'bold')).pack(pady=10)

        top_frame = ttk.Frame(dialog)
        top_frame.pack(fill=tk.X, padx=12)

        use_selected_var = tk.BooleanVar(value=bool(self.selected_id))
        ttk.Checkbutton(top_frame, text="Use selected account as source", variable=use_selected_var).grid(row=0, column=0, sticky=tk.W, pady=4)

        ttk.Label(top_frame, text="Or enter Source Account ID:").grid(row=1, column=0, sticky=tk.W, pady=4)
        src_entry = StyledEntry(top_frame, width=20)
        src_entry.grid(row=1, column=1, sticky=tk.W, padx=8, pady=4)
        if self.selected_id:
            src_entry.insert(0, str(self.selected_id))

        def load_csv():
            path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")], parent=dialog)
            if not path:
                return
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    txt.delete('1.0', tk.END)
                    txt.insert('1.0', f.read())
                self._set_status("Loaded CSV for bulk transfer")
            except Exception as e:
                messagebox.showerror("Load Error", f"Failed to load file: {e}", parent=dialog)

        ttk.Button(top_frame, text="Load CSV", command=load_csv).grid(row=1, column=2, padx=6)

        ttk.Label(dialog, text="Input transfers (one per line):\nFormat: to_account_id,amount[,note]", justify=tk.LEFT).pack(anchor=tk.W, padx=12, pady=(8,0))

        txt_frame = ttk.Frame(dialog)
        txt_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        txt = tk.Text(txt_frame, height=15, wrap=tk.NONE)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs = ttk.Scrollbar(txt_frame, orient='vertical', command=txt.yview); vs.pack(side=tk.RIGHT, fill=tk.Y)
        txt.config(yscrollcommand=vs.set)

        sample = "1002,250.00,monthly bonus\n1005,1000\n1010,50,refund"
        txt.insert('1.0', sample)

        progress_var = tk.StringVar(value="")
        ttk.Label(dialog, textvariable=progress_var).pack(pady=(4,0))

        def do_bulk():
            try:
                if use_selected_var.get():
                    if not self.selected_id:
                        messagebox.showerror("No Source", "No account selected in the table", parent=dialog)
                        return
                    src_id = int(self.selected_id)
                else:
                    s = src_entry.get().strip()
                    if not s:
                        messagebox.showerror("Missing Source", "Please provide source account ID or select an account", parent=dialog)
                        return
                    src_id = int(s)
            except ValueError:
                messagebox.showerror("Invalid Source", "Source account ID must be an integer", parent=dialog)
                return

            lines = [ln.strip() for ln in txt.get('1.0', tk.END).splitlines() if ln.strip()]
            if not lines:
                messagebox.showerror("No Transfers", "No transfer lines provided", parent=dialog)
                return

            parsed = []
            dest_ids = set()
            total_amount = 0.0
            for ln_num, line in enumerate(lines, start=1):
                parts = [p.strip() for p in line.split(',', 2)]
                if len(parts) < 2:
                    messagebox.showerror("Invalid Format", f"Line {ln_num} invalid format: '{line}'\nExpected: to_account_id,amount[,note]", parent=dialog)
                    return
                try:
                    to_id = int(parts[0])
                    amount = float(parts[1])
                    if amount <= 0:
                        messagebox.showerror("Invalid Amount", f"Line {ln_num} amount must be positive: '{line}'", parent=dialog)
                        return
                    note = parts[2] if len(parts) >= 3 else None
                    parsed.append((ln_num, to_id, amount, note, line))
                    dest_ids.add(to_id)
                    total_amount += amount
                except ValueError:
                    messagebox.showerror("Parse Error", f"Line {ln_num} has invalid numbers: '{line}'", parent=dialog)
                    return

            if dest_ids:
                placeholders = ",".join(["%s"] * len(dest_ids))
                cur = self.db.conn.cursor()
                try:
                    cur.execute(f"SELECT id FROM accounts WHERE id IN ({placeholders})", tuple(dest_ids))
                    found = {row[0] for row in cur.fetchall()}
                finally:
                    cur.close()
                missing = sorted(list(dest_ids - found))
                if missing:
                    if not messagebox.askyesno("Missing Destinations",
                                               f"The following destination account IDs were not found:\n{missing}\n\nDo you want to continue and skip missing entries?",
                                               parent=dialog):
                        return

          
            cur = self.db.conn.cursor()
            try:
                cur.execute("SELECT balance FROM accounts WHERE id=%s", (src_id,))
                row = cur.fetchone()
            finally:
                cur.close()
            if not row:
                messagebox.showerror("Source Not Found", f"Source account {src_id} not found", parent=dialog)
                return
            source_balance = float(row[0] or 0.0)
            if total_amount > source_balance:
                if not messagebox.askyesno("Insufficient Funds",
                                           f"Total required: ${total_amount:,.2f}\nSource balance: ${source_balance:,.2f}\n\nDo you want to continue and attempt transfers until funds run out?",
                                           parent=dialog):
                    return
                
            successes = []
            failures = []
            total = len(parsed)
            for i, (ln_num, to_id, amount, note, line) in enumerate(parsed, start=1):
                progress_var.set(f"Processing {i}/{total} ...")
                dialog.update_idletasks()
                try:
                  
                    cur = self.db.conn.cursor()
                    try:
                        cur.execute("SELECT id FROM accounts WHERE id=%s", (to_id,))
                        if not cur.fetchone():
                            raise ValueError("Destination account not found")
                    finally:
                        cur.close()

               
                    try:
                        self.db.transfer_funds(src_id, to_id, amount, note)
                        successes.append((to_id, amount))
                    except Exception as e:
                        failures.append((line, str(e)))
                        
                        if "Insufficient funds" in str(e) or "Insufficient funds in source account" in str(e):
                            break
                except Exception as e:
                    failures.append((line, str(e)))

        
            summary = tk.Toplevel(dialog)
            summary.title("Bulk Transfer Summary")
            summary.geometry("700x440")
            summary.transient(dialog)
            summary.grab_set()

            ttk.Label(summary, text="Bulk Transfer Summary", font=('Segoe UI', 12, 'bold')).pack(pady=8)
            txt_sum = tk.Text(summary, wrap=tk.WORD)
            txt_sum.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)



            btns = ttk.Frame(summary)
            btns.pack(pady=8)
            ModernButton(btns, text="Close & Continue", command=summary.destroy, style="info").pack(side=tk.LEFT, padx=6)
            ModernButton(btns, text="Finish", command=lambda: (summary.destroy(), dialog.destroy()), 
                        style="success").pack(side=tk.LEFT, padx=6)


            summary.focus_force()

            txt_sum.insert(tk.END, f"Source Account: {src_id}\n")
            txt_sum.insert(tk.END, f"Total lines: {total}\n")
            txt_sum.insert(tk.END, f"Successful transfers: {len(successes)}\n")
            txt_sum.insert(tk.END, f"Failed transfers: {len(failures)}\n\n")
            if successes:
                txt_sum.insert(tk.END, "SUCCESS:\n")
                for to_id, amt in successes:
                    txt_sum.insert(tk.END, f"  -> To {to_id}: ${amt:,.2f}\n")
                txt_sum.insert(tk.END, "\n")
            if failures:
                txt_sum.insert(tk.END, "FAILURES:\n")
                for line, err in failures:
                    txt_sum.insert(tk.END, f"  Line: {line}\n    Error: {err}\n")
            txt_sum.config(state=tk.DISABLED)

            btns = ttk.Frame(summary)
            btns.pack(pady=8)
            ttk.Button(btns, text="Close", command=summary.destroy).pack(side=tk.LEFT, padx=6)
            ttk.Button(btns, text="Close All", command=lambda: (summary.destroy(), dialog.destroy())).pack(side=tk.LEFT, padx=6)

            self._refresh_tree()
            self._set_status(f"Bulk transfer done: {len(successes)} success, {len(failures)} failures")
            logging.info(f"Bulk transfer completed: {len(successes)} success, {len(failures)} failures")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ModernButton(btn_frame, text="Start Bulk Transfer", command=do_bulk, style="success", width=18).pack(side=tk.LEFT, padx=6)
        ModernButton(btn_frame, text="Cancel", command=dialog.destroy, style="danger", width=12).pack(side=tk.LEFT, padx=6)



    def _generate_report(self):
   
        stats = self.db.get_statistics()
        
        report = f"""
{'='*60}
        BANK MANAGEMENT SYSTEM - COMPREHENSIVE REPORT
{'='*60}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

ACCOUNT OVERVIEW
{'-'*60}
Total Active Accounts:        {stats.get('total_accounts', 0):>10,}
Frozen Accounts:              {stats.get('frozen_accounts', 0):>10,}
New Accounts (Last 30 Days):  {stats.get('new_accounts_30d', 0):>10,}

FINANCIAL SUMMARY
{'-'*60}
Total Balance:                ${stats.get('total_balance', 0):>10,.2f}
Average Balance:              ${stats.get('avg_balance', 0):>10,.2f}

ACCOUNT TYPE BREAKDOWN
{'-'*60}
"""
        
        for acc_type, count in stats.get('by_type', {}).items():
            report += f"{acc_type:<30} {count:>10,}\n"
        
        report += f"\n{'='*60}\n"
        

        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
            initialfile=f"bank_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(report)
                messagebox.showinfo("  Report Generated", f"Report saved to:\n{filename}")
                logging.info(f"Report generated: {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save report: {str(e)}")




    def _export_all_accounts(self):
        fn = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            initialfile=f"all_accounts_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        if not fn:
            return
        try:
            self.db.export_accounts_csv(fn)
            messagebox.showinfo("  Exported", f"All accounts exported to:\n{fn}")
            self._set_status("  Accounts exported")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _export_filtered_accounts(self):
        term = simpledialog.askstring("Export Filter", 
                                      "Enter search term (leave empty for all visible accounts):",
                                      parent=self)
        filters = {}
        if term:
            filters["search"] = term
        
        fn = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            initialfile=f"filtered_accounts_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        if not fn:
            return
        
        try:
            self.db.export_accounts_csv(fn, filters=filters)
            messagebox.showinfo("  Exported", f"Filtered accounts exported to:\n{fn}")
            self._set_status("  Filtered export complete")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _export_transactions_selected(self):
        if not self.selected_id:
            messagebox.showerror("No Selection", "Please select an account to export transactions")
            return
        
        fn = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            initialfile=f"transactions_acc{self.selected_id}_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        if not fn:
            return
        
        try:
            self.db.export_transactions_csv(fn, acc_id=self.selected_id)
            messagebox.showinfo("  Exported", f"Transactions exported to:\n{fn}")
            self._set_status("  Transactions exported")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _export_transactions_window(self, acc_id=None):
        fn = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            initialfile=f"transactions_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        if not fn:
            return
        
        try:
            self.db.export_transactions_csv(fn, acc_id=acc_id)
            messagebox.showinfo("  Exported", f"Transactions exported to:\n{fn}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))


    def _view_logs(self):
        win = tk.Toplevel(self)
        win.title("📜 Operation Logs")
        win.geometry("900x600")
        win.configure(bg='white')
        
        header = tk.Frame(win, bg=COLORS['dark'])
        header.pack(fill=tk.X)
        tk.Label(header, text="📜 System Operation Logs", 
                font=('Segoe UI', 12, 'bold'), bg=COLORS['dark'], fg='white').pack(pady=15)
        

        text_frame = ttk.Frame(win)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        vsb = ttk.Scrollbar(text_frame)
        txt = tk.Text(text_frame, wrap=tk.WORD, font=('Consolas', 9), 
                     yscrollcommand=vsb.set, bg=COLORS['light'])
        vsb.config(command=txt.yview)
        
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = f.readlines()

                txt.insert('1.0', ''.join(logs[-1000:]))
        except FileNotFoundError:
            txt.insert('1.0', "No logs available yet.")
        except Exception as e:
            txt.insert('1.0', f"Error reading logs: {str(e)}")
        
        txt.config(state=tk.DISABLED)
        
        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=10)
        ModernButton(btn_frame, text="🔄 Refresh", 
                    command=lambda: self._refresh_logs(txt), style="info").pack(side=tk.LEFT, padx=5)
        ModernButton(btn_frame, text="  Close", command=win.destroy, style="secondary").pack(side=tk.LEFT, padx=5)

    def _refresh_logs(self, text_widget):
        text_widget.config(state=tk.NORMAL)
        text_widget.delete('1.0', tk.END)
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = f.readlines()
                text_widget.insert('1.0', ''.join(logs[-1000:]))
        except Exception as e:
            text_widget.insert('1.0', f"Error reading logs: {str(e)}")
        text_widget.config(state=tk.DISABLED)

    def _change_admin_password(self):
        auth = AdminAuth()
        
        dialog = tk.Toplevel(self)
        dialog.title("🔑 Change Admin Password")
        dialog.geometry("400x300")
        dialog.configure(bg='white')
        dialog.transient(self)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Change Admin Password", font=('Segoe UI', 12, 'bold'), 
                 background='white').pack(pady=20)
        
        form = ttk.Frame(dialog)
        form.pack(padx=30)
        
        ttk.Label(form, text="Current Password:", background='white').grid(row=0, column=0, sticky=tk.W, pady=5)
        current_entry = ttk.Entry(form, show="●", width=25)
        current_entry.grid(row=0, column=1, pady=5)
        
        ttk.Label(form, text="New Password:", background='white').grid(row=1, column=0, sticky=tk.W, pady=5)
        new_entry = ttk.Entry(form, show="●", width=25)
        new_entry.grid(row=1, column=1, pady=5)
        
        ttk.Label(form, text="Confirm Password:", background='white').grid(row=2, column=0, sticky=tk.W, pady=5)
        confirm_entry = ttk.Entry(form, show="●", width=25)
        confirm_entry.grid(row=2, column=1, pady=5)
        
        def change_pwd():
            if not auth.verify(current_entry.get()):
                messagebox.showerror("Error", "Incorrect current password", parent=dialog)
                return
            
            new_pwd = new_entry.get()
            if len(new_pwd) < 4:
                messagebox.showerror("Error", "Password must be at least 4 characters", parent=dialog)
                return
            
            if new_pwd != confirm_entry.get():
                messagebox.showerror("Error", "Passwords do not match", parent=dialog)
                return
            
            auth.change_password(new_pwd)
            messagebox.showinfo("  Success", "Admin password changed successfully", parent=dialog)
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=20)
        ModernButton(btn_frame, text="  Change", command=change_pwd, style="success").pack(side=tk.LEFT, padx=5)
        ModernButton(btn_frame, text="  Cancel", command=dialog.destroy, style="danger").pack(side=tk.LEFT, padx=5)

    def _show_help(self):
        help_text = """
 BANK MANAGEMENT SYSTEM - HELP GUIDE

GETTING STARTED
• Select an account from the table to edit or perform transactions
• Use the search bar for quick lookups
• All changes are logged automatically

CREATING ACCOUNTS
• Fill in the required fields (marked with *)
• Emirates ID format: XXX-XXXX-XXXXXXX-X
• Account number is auto-generated if left blank

TRANSACTIONS
• Deposit: Add funds to selected account
• Withdraw: Remove funds from selected account
• Transfer: Move funds between accounts
• All transactions are recorded in the database

SEARCH & FILTERS
• Quick search: Use the search bar at the top
• Advanced search: Access via Tools menu for detailed filtering
• Filter by status, type, balance range, and dates

EXPORTS
• Export all accounts or filtered results
• Export transaction history for any account
• Generate comprehensive reports

SECURITY
• All operations require admin authentication
• Change password regularly via Admin menu
• Review logs periodically for audit trail

KEYBOARD SHORTCUTS
• Enter: Submit in search/amount dialogs
• Escape: Close dialogs (where applicable)

For technical support, check the operation logs or contact your system administrator.
        """
        
        win = tk.Toplevel(self)
        win.title("❓ Help")
        win.geometry("700x600")
        win.configure(bg='white')
        
        header = tk.Frame(win, bg=COLORS['info'])
        header.pack(fill=tk.X)
        tk.Label(header, text="❓ Help & Documentation", 
                font=('Segoe UI', 12, 'bold'), bg=COLORS['info'], fg='white').pack(pady=15)
        
        text_frame = ttk.Frame(win)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        vsb = ttk.Scrollbar(text_frame)
        txt = tk.Text(text_frame, wrap=tk.WORD, font=('Segoe UI', 10), 
                     yscrollcommand=vsb.set, bg=COLORS['light'], padx=20, pady=20)
        vsb.config(command=txt.yview)
        
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        txt.insert('1.0', help_text)
        txt.config(state=tk.DISABLED)
        
        ModernButton(win, text="  Close", command=win.destroy, style="secondary").pack(pady=10)

    def _show_about(self):
        about_text = f"""
BANK MANAGEMENT SYSTEM

Version: 2.0 Enhanced Edition
Developed by: Saud bin Abdul Mutallib & Talha Abdul Ahad

FEATURES
 Complete account management
 Transaction processing
 Advanced search & filtering
 Comprehensive reporting
 Data export (CSV)
 Analytics dashboard
 Audit logging
 Secure authentication

TECHNOLOGY STACK
 Python 3.x
 Tkinter (GUI)
 MySQL Database
 Matplotlib (Analytics)

DATABASE: {DB_NAME}@{DB_HOST}:{DB_PORT}

{datetime.now().year} Bank Management System
All rights reserved.
        """
        
        win = tk.Toplevel(self)
        win.title("ℹ️ About")
        win.geometry("500x500")
        win.configure(bg='white')
        
        header = tk.Frame(win, bg=COLORS['secondary'])
        header.pack(fill=tk.X)
        tk.Label(header, text="ℹ️ About This Application", 
                font=('Segoe UI', 12, 'bold'), bg=COLORS['secondary'], fg='white').pack(pady=15)
        
        txt = tk.Text(win, wrap=tk.WORD, font=('Segoe UI', 10), 
                     bg=COLORS['light'], relief=tk.FLAT, padx=30, pady=30)
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        txt.insert('1.0', about_text)
        txt.config(state=tk.DISABLED)
        
        ModernButton(win, text="  Close", command=win.destroy, style="secondary").pack(pady=10)
       

    def _manage_loans(self):
        win = tk.Toplevel(self)
        win.title("💳 Loan Management")
        win.geometry("900x500")
        win.transient(self)

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        cols = ("id", "account_id", "amount", "term_months", "rate", "status", "created_at")
        tv = ttk.Treeview(frame, columns=cols, show="headings")
        for c in cols:
            tv.heading(c, text=c.replace("_", " ").title())
            tv.column(c, width=110)
        tv.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        tv.configure(yscrollcommand=vsb.set)

        try:
            loans = self.db.get_loans()
            for r in loans:
                tv.insert("", tk.END, values=r)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load loans: {e}", parent=win)

        def approve():
            sel = tv.selection()
            if not sel:
                messagebox.showerror("Select", "Select a loan")
                return
            loan_id = int(tv.item(sel[0], "values")[0])
            if not messagebox.askyesno("Approve", "Approve selected loan?"):
                return
            try:
                self.db.update_loan_status(loan_id, "Approved", admin_note="Approved by admin")
                messagebox.showinfo("Approved", "Loan approved and disbursed")
                win.destroy()
                self._manage_loans()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=win)

        def decline():
            sel = tv.selection()
            if not sel:
                messagebox.showerror("Select", "Select a loan")
                return
            loan_id = int(tv.item(sel[0], "values")[0])
            if not messagebox.askyesno("Decline", "Decline selected loan?"):
                return
            try:
                self.db.update_loan_status(loan_id, "Declined", admin_note="Declined by admin")
                messagebox.showinfo("Done", "Loan declined")
                win.destroy()
                self._manage_loans()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=win)

        btns = ttk.Frame(win)
        btns.pack(pady=6)
        ModernButton(btns, text="Approve", command=approve, style="success").pack(side=tk.LEFT, padx=4)
        ModernButton(btns, text="Decline", command=decline, style="danger").pack(side=tk.LEFT, padx=4)
        ModernButton(btns, text="Refresh", command=lambda: (win.destroy(), self._manage_loans()), style="info").pack(side=tk.LEFT, padx=4)
        ModernButton(btns, text="Close", command=win.destroy, style="secondary").pack(side=tk.LEFT, padx=4)

    def _create_loan_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("➕ Create Loan")
        dialog.geometry("420x320")
        dialog.transient(self)
        dialog.grab_set()

        form = ttk.Frame(dialog)
        form.pack(padx=20, pady=20, fill=tk.BOTH)

        ttk.Label(form, text="Account ID:").grid(row=0, column=0, sticky=tk.W, pady=5)
        acc_entry = StyledEntry(form); acc_entry.grid(row=0, column=1, pady=5)

        ttk.Label(form, text="Amount:").grid(row=1, column=0, sticky=tk.W, pady=5)
        amt_entry = StyledEntry(form); amt_entry.grid(row=1, column=1, pady=5)

        ttk.Label(form, text="Term (months):").grid(row=2, column=0, sticky=tk.W, pady=5)
        term_entry = StyledEntry(form); term_entry.grid(row=2, column=1, pady=5)

        ttk.Label(form, text="Interest Rate (%):").grid(row=3, column=0, sticky=tk.W, pady=5)
        rate_entry = StyledEntry(form); rate_entry.grid(row=3, column=1, pady=5)

        def create():
            try:
                acc_id = int(acc_entry.get())
                amt = float(amt_entry.get())
                term = int(term_entry.get())
                rate = float(rate_entry.get())
                loan_id = self.db.create_loan(acc_id, amt, term, rate)
                messagebox.showinfo("Created", f"Loan request created (id={loan_id})", parent=dialog)
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        btns = ttk.Frame(dialog)
        btns.pack(pady=10)
        ModernButton(btns, text="Create Loan", command=create, style="success").pack(side=tk.LEFT, padx=5)
        ModernButton(btns, text="Cancel", command=dialog.destroy, style="secondary").pack(side=tk.LEFT, padx=5)

    def _manage_debts(self):
        win = tk.Toplevel(self)
        win.title("💼 Debts")
        win.geometry("900x480")
        win.transient(self)

        frame = ttk.Frame(win); frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        cols = ("id", "account_id", "amount", "description", "status", "created_at")
        tv = ttk.Treeview(frame, columns=cols, show="headings")
        for c in cols:
            tv.heading(c, text=c.title().replace("_", " "))
            tv.column(c, width=120)
        tv.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        tv.configure(yscrollcommand=vsb.set)

        try:
            debts = self.db.get_debts() if hasattr(self.db, 'get_debts') else []
            for d in debts:
                tv.insert("", tk.END, values=d)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load debts: {e}", parent=win)

        def add_debt():
            d = simpledialog.askstring("Add Debt", "Enter: account_id,amount,description", parent=win)
            if not d:
                return
            try:
                parts = [p.strip() for p in d.split(",", 2)]
                acc = int(parts[0]); amt = float(parts[1]); desc = parts[2] if len(parts) > 2 else None
                debt_id = self.db.add_debt(acc, amt, desc)
                messagebox.showinfo("Added", f"Debt created: id={debt_id}", parent=win)
                win.destroy(); self._manage_debts()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=win)

        def settle():
            sel = tv.selection()
            if not sel:
                messagebox.showerror("Select", "Select a debt")
                return
            debt_id = int(tv.item(sel[0], "values")[0])
            if not messagebox.askyesno("Settle", "Mark selected debt as settled?"):
                return
            try:
                self.db.settle_debt(debt_id)
                messagebox.showinfo("Done", "Debt settled", parent=win)
                win.destroy(); self._manage_debts()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=win)

        btns = ttk.Frame(win); btns.pack(pady=6)
        ModernButton(btns, text="Add Debt", command=add_debt, style="info").pack(side=tk.LEFT, padx=4)
        ModernButton(btns, text="Settle Debt", command=settle, style="success").pack(side=tk.LEFT, padx=4)
        ModernButton(btns, text="Close", command=win.destroy, style="secondary").pack(side=tk.LEFT, padx=4)
   

    def _build_menu(self):
        menubar = tk.Menu(self, bg=COLORS['primary'], fg='white')
        

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label=" Export All Accounts", command=self._export_all_accounts)
        file_menu.add_command(label=" Export Filtered", command=self._export_filtered_accounts)
        file_menu.add_command(label=" Export Transactions", command=self._export_transactions_selected)
        file_menu.add_separator()
        file_menu.add_command(label=" Generate Report", command=self._generate_report)
        file_menu.add_separator()
        file_menu.add_command(label=" Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        

        admin_menu = tk.Menu(menubar, tearoff=0)
        admin_menu.add_command(label=" Change Password", command=self._change_admin_password)
        admin_menu.add_command(label=" View Logs", command=self._view_logs)
        admin_menu.add_separator()
        admin_menu.add_command(label=" Statistics Dashboard", command=self._show_statistics)
        menubar.add_cascade(label="Admin", menu=admin_menu)
        
    
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label=" Advanced Search", command=self._advanced_search)
        tools_menu.add_command(label=" Account Analytics", command=self._show_analytics)
        tools_menu.add_command(label=" Bulk Transfer", command=self._bulk_operations)

        menubar.add_cascade(label="Tools", menu=tools_menu)
        
   
        loans_menu = tk.Menu(menubar, tearoff=0)
        loans_menu.add_command(label="Manage Loans", command=self._manage_loans)
        loans_menu.add_command(label="Create Loan", command=self._create_loan_dialog)
        loans_menu.add_command(label="Debts", command=self._manage_debts)
        menubar.add_cascade(label="Loans", menu=loans_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="❓ Help", command=self._show_help)
        help_menu.add_command(label=" AI Assistant", command=self._open_ai_chat)
        help_menu.add_command(label="ℹ️ About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.config(menu=menubar)


def main():
    try:
        db = BankDB()
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Database Connection Error", 
                           f"Failed to connect to database:\n\n{str(e)}\n\n"
                           f"Please ensure MySQL is running and credentials are correct.")
        return
    
    app = BankApp(db)
    try:
        app.mainloop()
    finally:
        try:
            db.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()