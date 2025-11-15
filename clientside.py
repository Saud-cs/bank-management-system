
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime
from bankmanagementsystem import BankDB  
class ClientApp(tk.Tk):
    def __init__(self, db: BankDB):
        super().__init__()
        self.db = db
        self.account = None  # will hold tuple returned by db.get_account()
        self.title("Customer Portal - Bank")
        self.geometry("700x520")
        self.configure(bg="#f7f7f7")

        self._build_login_ui()

    def _build_login_ui(self):
        for w in self.winfo_children():
            w.destroy()

        frame = ttk.Frame(self, padding=20)
        frame.pack(expand=True)

        ttk.Label(frame, text="Customer Portal", font=("Segoe UI", 16, "bold")).pack(pady=(0,10))

        ttk.Label(frame, text="Login with Account ID or Account Number").pack(pady=(5,2))

        self.login_id = ttk.Entry(frame, width=40)
        self.login_id.pack(pady=4)
        self.login_id.insert(0, "Account ID (numeric) or Account No (e.g. AC00000001)")

        ttk.Label(frame, text="Emirates ID (for verification)").pack(pady=(10,2))
        self.login_eid = ttk.Entry(frame, width=40)
        self.login_eid.pack(pady=4)
        self.login_eid.insert(0, "XXX-XXXX-XXXXXXX-X")

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="Login", command=self._do_login).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Exit", command=self.destroy).pack(side=tk.LEFT, padx=8)

        ttk.Label(frame, text="(No password required — this demo uses Emirates ID as simple verification)", foreground="gray").pack(pady=(12,0))

    def _do_login(self):
        ident = self.login_id.get().strip()
        eid = self.login_eid.get().strip()
        if not ident or not eid:
            messagebox.showerror("Input required", "Please enter account identifier and Emirates ID")
            return

        try:
            # Try numeric id first
            acc = None
            try:
                acc_id = int(ident)
                acc = self.db.get_account(acc_id)
            except ValueError:
                # not numeric => search by account_number
                rows = self.db.get_accounts(filters={"search": ident, "search_col": "account_number"})
                acc = rows[0] if rows else None

            if not acc:
                messagebox.showerror("Not found", "Account not found")
                return

            # acc tuple: (id, account_number, name, emirates_id, balance, phone, email, account_type, status, created_at)
            # verify emirates id
            if not acc[3] or acc[3].strip() != eid:
                messagebox.showerror("Verification failed", "Emirates ID does not match")
                return

            self.account = acc
            self._build_dashboard_ui()
        except Exception as e:
            messagebox.showerror("Error", f"Login failed: {e}")

    def _build_dashboard_ui(self):
        for w in self.winfo_children():
            w.destroy()

        header = ttk.Frame(self, padding=10)
        header.pack(fill=tk.X)
        ttk.Label(header, text=f"Welcome, {self.account[2]}", font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT)
        ttk.Button(header, text="Logout", command=self._logout).pack(side=tk.RIGHT, padx=6)

        main = ttk.Frame(self, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,8))
        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Account summary
        ttk.Label(left, text="Account Summary", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
        info = ttk.Frame(left, padding=(0,8))
        info.pack(fill=tk.X, pady=(6,12))

        ttk.Label(info, text=f"Account No: {self.account[1]}").pack(anchor=tk.W)
        ttk.Label(info, text=f"Account ID: {self.account[0]}").pack(anchor=tk.W)
        ttk.Label(info, text=f"Type: {self.account[7]}").pack(anchor=tk.W)
        ttk.Label(info, text=f"Status: {self.account[8]}").pack(anchor=tk.W)
        self.balance_var = tk.StringVar(value=f"${float(self.account[4]):,.2f}")
        ttk.Label(info, text="Balance:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(8,0))
        ttk.Label(info, textvariable=self.balance_var, foreground="#2E8B57", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)

        # Quick actions
        ttk.Label(left, text="Quick Actions", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W, pady=(14,4))
        act_frame = ttk.Frame(left)
        act_frame.pack(fill=tk.X)
        ttk.Button(act_frame, text="Deposit", command=self._deposit_dialog).pack(fill=tk.X, pady=4)
        ttk.Button(act_frame, text="Withdraw", command=self._withdraw_dialog).pack(fill=tk.X, pady=4)
        ttk.Button(act_frame, text="Transfer", command=self._transfer_dialog).pack(fill=tk.X, pady=4)
        ttk.Button(act_frame, text="Update Contact", command=self._update_contact_dialog).pack(fill=tk.X, pady=4)
        ttk.Button(act_frame, text="Export Transactions (CSV)", command=self._export_transactions).pack(fill=tk.X, pady=4)

        # Recent transactions on right
        ttk.Label(right, text="Recent Transactions", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
        tv_frame = ttk.Frame(right)
        tv_frame.pack(fill=tk.BOTH, expand=True, pady=(6,0))

        cols = ("id", "amount", "type", "note", "created_at")
        self.tv = ttk.Treeview(tv_frame, columns=cols, show="headings", height=15)
        for c, text in zip(cols, ("ID", "Amount", "Type", "Note", "Date")):
            self.tv.heading(c, text=text)
            self.tv.column(c, width=100 if c!="note" else 220, anchor=tk.W)
        self.tv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(tv_frame, orient="vertical", command=self.tv.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tv.configure(yscrollcommand=vsb.set)

        self._refresh_account_view()

    def _refresh_account_view(self):
        try:
            # refresh account info
            acc = self.db.get_account(self.account[0])
            if acc:
                self.account = acc
                self.balance_var.set(f"${float(self.account[4]):,.2f}")

            # refresh transactions
            for r in self.tv.get_children():
                self.tv.delete(r)
            rows = self.db.get_transactions(acc_id=self.account[0], limit=200)
            for idx, r in enumerate(rows):
                # r: (id, account_id, amount, type, note, created_at)
                amt = f"${float(r[2]):+.2f}"
                dt = r[5].strftime("%Y-%m-%d %H:%M:%S") if hasattr(r[5], "strftime") else str(r[5])
                self.tv.insert("", tk.END, values=(r[0], amt, r[3], r[4] or "", dt))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh: {e}")

    def _deposit_dialog(self):
        amt = simpledialog.askfloat("Deposit", "Enter amount to deposit:", minvalue=0.01, parent=self)
        if amt is None:
            return
        try:
            new_bal = self.db.change_balance(self.account[0], float(amt), trans_type="deposit", note="Customer deposit")
            messagebox.showinfo("Success", f"Deposited ${amt:.2f}\nNew balance: ${new_bal:.2f}")
            self._refresh_account_view()
        except Exception as e:
            messagebox.showerror("Error", f"Deposit failed: {e}")

    def _withdraw_dialog(self):
        amt = simpledialog.askfloat("Withdraw", "Enter amount to withdraw:", minvalue=0.01, parent=self)
        if amt is None:
            return
        try:
            new_bal = self.db.change_balance(self.account[0], -float(amt), trans_type="withdraw", note="Customer withdrawal")
            messagebox.showinfo("Success", f"Withdrew ${amt:.2f}\nNew balance: ${new_bal:.2f}")
            self._refresh_account_view()
        except Exception as e:
            messagebox.showerror("Error", f"Withdrawal failed: {e}")

    def _transfer_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Transfer Funds")
        dlg.geometry("380x220")
        dlg.transient(self)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="To Account ID:").pack(anchor=tk.W, pady=(4,0))
        to_ent = ttk.Entry(frm)
        to_ent.pack(fill=tk.X, pady=4)

        ttk.Label(frm, text="Amount:").pack(anchor=tk.W, pady=(8,0))
        amt_ent = ttk.Entry(frm)
        amt_ent.pack(fill=tk.X, pady=4)

        ttk.Label(frm, text="Note (optional):").pack(anchor=tk.W, pady=(8,0))
        note_ent = ttk.Entry(frm)
        note_ent.pack(fill=tk.X, pady=4)

        def do_transfer():
            try:
                to_id = int(to_ent.get().strip())
                amt = float(amt_ent.get().strip())
                if amt <= 0:
                    raise ValueError("Amount must be positive")
                self.db.transfer_funds(self.account[0], to_id, amt, note_ent.get().strip() or None)
                messagebox.showinfo("Success", f"Transferred ${amt:.2f} to account {to_id}")
                dlg.destroy()
                self._refresh_account_view()
            except ValueError as ve:
                messagebox.showerror("Invalid input", str(ve), parent=dlg)
            except Exception as e:
                messagebox.showerror("Transfer failed", str(e), parent=dlg)

        btns = ttk.Frame(frm)
        btns.pack(pady=10)
        ttk.Button(btns, text="Transfer", command=do_transfer).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT, padx=6)

    def _update_contact_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Update Contact Details")
        dlg.geometry("420x220")
        dlg.transient(self)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Phone:").pack(anchor=tk.W, pady=(4,0))
        phone_ent = ttk.Entry(frm)
        phone_ent.pack(fill=tk.X, pady=4)
        phone_ent.insert(0, self.account[5] or "")

        ttk.Label(frm, text="Email:").pack(anchor=tk.W, pady=(8,0))
        email_ent = ttk.Entry(frm)
        email_ent.pack(fill=tk.X, pady=4)
        email_ent.insert(0, self.account[6] or "")

        def save():
            try:
                phone = phone_ent.get().strip() or None
                email = email_ent.get().strip() or None
                # reuse update_account with same values for missing fields
                self.db.update_account(self.account[0], self.account[2], self.account[1], self.account[3], phone, email, self.account[7], self.account[8])
                messagebox.showinfo("Saved", "Contact details updated")
                dlg.destroy()
                self._refresh_account_view()
            except Exception as e:
                messagebox.showerror("Error", f"Update failed: {e}", parent=dlg)

        btns = ttk.Frame(frm)
        btns.pack(pady=12)
        ttk.Button(btns, text="Save", command=save).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT, padx=6)

    def _export_transactions(self):
        fn = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile=f"transactions_acc{self.account[0]}_{datetime.now().strftime('%Y%m%d')}.csv")
        if not fn:
            return
        try:
            self.db.export_transactions_csv(fn, acc_id=self.account[0])
            messagebox.showinfo("Exported", f"Transactions exported to {fn}")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}")

    def _logout(self):
        self.account = None
        self._build_login_ui()


if __name__ == "__main__":
    try:
        db = BankDB()
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Database Error", f"Cannot connect to database: {e}")
    else:
        app = ClientApp(db)
        try:
            app.mainloop()
        finally:
            try:
                db.close()
            except Exception:
                pass