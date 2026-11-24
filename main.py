import flet as ft
import base64
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime

ORDERS_FILE = "orders.json"
PROOF_FOLDER = "proofs"          # uploaded proof-of-payment files are stored here
WHATSAPP_DISPLAY = "0633067176"   # contact number shown to customers
OWNER_PHONE = "+27633067176"      # your number (international format) for alerts

# ---------------------------------------------------------------------------
# Back-end order alerts to the owner. The customer never sees any of this.
# Fill in ONE OR MORE of the options below; any left as "PASTE..." are skipped.
# Values can also be set as environment variables (names in brackets).
# ---------------------------------------------------------------------------

# Option A - WhatsApp message via CallMeBot (free, text only)
CALLMEBOT_API_KEY = os.environ.get("ZINE_CALLMEBOT_KEY", "2017")

# Option B - SMS or WhatsApp via Twilio (paid; works with a Twilio account)
TWILIO_ACCOUNT_SID = os.environ.get("ZINE_TWILIO_SID", "PASTE_TWILIO_SID_HERE")
TWILIO_AUTH_TOKEN = os.environ.get("ZINE_TWILIO_TOKEN", "PASTE_TWILIO_TOKEN_HERE")
TWILIO_FROM = os.environ.get("ZINE_TWILIO_FROM", "PASTE_TWILIO_FROM_HERE")
#   SMS example:       TWILIO_FROM = "+15551234567"           (your Twilio number)
#   WhatsApp example:  TWILIO_FROM = "whatsapp:+14155238886"  (Twilio WhatsApp sender)
# Twilio sends to OWNER_PHONE above (it adds "whatsapp:" automatically if needed).

# Option C - Telegram (free, also sends the proof of payment file)
TELEGRAM_BOT_TOKEN = os.environ.get("ZINE_TELEGRAM_TOKEN", "PASTE_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.environ.get("ZINE_TELEGRAM_CHAT_ID", "PASTE_CHAT_ID_HERE")

REQUIRE_PROOF = True             # set to False to make the upload optional
PROOF_EXTENSIONS = ["jpg", "jpeg", "png", "pdf"]

# Set your own password here, or (better) set the ZINE_ADMIN_PASSWORD
# environment variable so it is not stored in the code.
ADMIN_PASSWORD = os.environ.get("ZINE_ADMIN_PASSWORD", "change-me-123")

PRICES = {
    "30ml": 120,
    "50ml": 200,
}

THANK_YOU_MESSAGES = [
    "🤗 Thank you for your order. Stay confident and smell amazing!",
    "✨✨✨ Your fragrance journey starts with us. Thank you!",
    "💖💖💖 We appreciate your support. Enjoy your scent!",
    "🌸🌸🌸 Thank you for supporting Zine Perfume Store!",
    "🌷 Your order has been received. See you again soon!",
]


class Order:
    def __init__(
        self,
        order_number,
        order_date,
        customer,
        phone,
        perfume,
        size,
        quantity,
        perfume2,
        size2,
        quantity2,
        total,
        payment_option,
        amount_due,
        balance_due,
        proof_of_payment="",
    ):
        self.proof_of_payment = proof_of_payment
        self.order_number = order_number
        self.order_date = order_date
        self.customer = customer
        self.phone = phone

        self.perfume = perfume
        self.size = size
        self.quantity = quantity

        self.perfume2 = perfume2
        self.size2 = size2
        self.quantity2 = quantity2

        self.total = total
        self.payment_option = payment_option
        self.amount_due = amount_due
        self.balance_due = balance_due


class OrderManager:
    def load_orders(self):
        try:
            with open(ORDERS_FILE, "r") as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save_order(self, order):
        orders = self.load_orders()

        orders.append({
            "order_number": order.order_number,
            "date": order.order_date,
            "customer": order.customer,
            "phone": order.phone,
            "perfume": order.perfume,
            "size": order.size,
            "quantity": order.quantity,
            "perfume2": order.perfume2,
            "size2": order.size2,
            "quantity2": order.quantity2,
            "total": order.total,
            "payment_option": order.payment_option,
            "amount_due_now": order.amount_due,
            "balance_due": order.balance_due,
            "proof_of_payment": order.proof_of_payment,
        })

        with open(ORDERS_FILE, "w") as file:
            json.dump(orders, file, indent=4)


def main(page: ft.Page):

    page.title = "Zine Perfume Store"
    page.scroll = ft.ScrollMode.AUTO
    page.theme_mode = ft.ThemeMode.LIGHT

    manager = OrderManager()

    # ---------------------------------------------------------------
    # Form controls
    # ---------------------------------------------------------------
    customer_name = ft.TextField(label="Customer Name")
    phone_number = ft.TextField(label="Phone Number")

    perfume_name = ft.TextField(
        label="Perfume Name",
        hint_text="Example: Sauvage",
    )
    size = ft.Dropdown(
        label="Select Size",
        options=[
            ft.dropdown.Option("30ml"),
            ft.dropdown.Option("50ml"),
        ],
    )
    quantity = ft.TextField(label="Quantity", value="1")

    perfume_name2 = ft.TextField(label="Perfume Name (Optional)")
    size2 = ft.Dropdown(
        label="Select Size (Optional)",
        options=[
            ft.dropdown.Option("30ml"),
            ft.dropdown.Option("50ml"),
        ],
    )
    quantity2 = ft.TextField(label="Quantity (Optional)", value="0")

    payment_option = ft.Dropdown(
        label="Payment Option",
        options=[
            ft.dropdown.Option("Pay Full Amount"),
            ft.dropdown.Option("Pay 50% Deposit"),
        ],
    )

    total_text = ft.Text("Total: R0", size=18, weight="bold")
    payment_text = ft.Text("")

    payment_details = ft.Container(
        content=ft.Column([
            ft.Text("💳 PAYMENT DETAILS", size=20, weight="bold"),
            ft.Text("Account Number: 234848789"),
            ft.Text(f"Contact / WhatsApp: {WHATSAPP_DISPLAY}"),
            ft.Divider(),
            ft.Text(
                "💚 Flexible Payment Available",
                weight="bold",
                color="green",
            ),
            ft.Text(
                "Pay 50% today to confirm your order and pay the remaining "
                "balance on delivery day."
            ),
            ft.Text("Reference: Use your name when making payment."),
        ]),
        padding=10,
        border=ft.border.all(1),
    )

    # ---------------------------------------------------------------
    # Proof of payment upload
    # ---------------------------------------------------------------
    proof_state = {"file": ""}
    proof_text = ft.Text("No file selected", italic=True)

    def on_file_picked(e: ft.FilePickerResultEvent):
        if not e.files:
            return

        picked = e.files[0]
        safe_name = (
            f"{datetime.now().strftime('%Y%m%d%H%M%S')}_"
            f"{picked.name.replace(' ', '_')}"
        )

        try:
            os.makedirs(PROOF_FOLDER, exist_ok=True)

            if picked.path:
                # Desktop app: copy the chosen file into the proofs folder
                shutil.copy(picked.path, os.path.join(PROOF_FOLDER, safe_name))
            else:
                # Web app: upload the file to the server's proofs folder
                file_picker.upload([
                    ft.FilePickerUploadFile(
                        picked.name,
                        upload_url=page.get_upload_url(safe_name, 600),
                    )
                ])

            proof_state["file"] = safe_name
            proof_text.value = f"✅ Uploaded: {picked.name}"
            proof_text.color = "green"
            proof_text.italic = False
        except Exception as error:
            proof_state["file"] = ""
            proof_text.value = f"Upload failed: {error}"
            proof_text.color = "red"

        page.update()

    file_picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(file_picker)

    def choose_proof(e):
        file_picker.pick_files(
            dialog_title="Select proof of payment",
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=PROOF_EXTENSIONS,
        )

    upload_proof_button = ft.ElevatedButton(
        text="📎 Upload Proof of Payment",
        on_click=choose_proof,
    )

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------
    def compute_totals():
        """Returns (total, amount_due_now, balance_due, qty, qty2).
        Raises ValueError on bad quantity input."""
        qty = int(quantity.value)
        if qty <= 0:
            raise ValueError("Quantity must be greater than 0")

        total1 = qty * PRICES.get(size.value, 0)

        qty2 = 0
        total2 = 0
        if perfume_name2.value and size2.value:
            qty2 = int(quantity2.value or 0)
            if qty2 < 0:
                raise ValueError("Second quantity cannot be negative")
            total2 = qty2 * PRICES.get(size2.value, 0)

        total = total1 + total2

        if payment_option.value == "Pay 50% Deposit":
            due_now = total / 2
            balance = total / 2
        else:
            due_now = total
            balance = 0

        return total, due_now, balance, qty, qty2

    def reset_form():
        customer_name.value = ""
        phone_number.value = ""
        perfume_name.value = ""
        size.value = None
        quantity.value = "1"

        perfume_name2.value = ""
        size2.value = None
        quantity2.value = "0"

        payment_option.value = None

        for field in (customer_name, phone_number, perfume_name, size,
                      quantity, quantity2, payment_option):
            field.error_text = None

        proof_state["file"] = ""
        proof_text.value = "No file selected"
        proof_text.color = None
        proof_text.italic = True

        total_text.value = "Total: R0"
        payment_text.value = ""

    # ---------------------------------------------------------------
    # Event handlers
    # ---------------------------------------------------------------
    def calculate_total(e):
        try:
            total, due_now, balance, _, _ = compute_totals()

            total_text.value = f"Total: R{total}"
            payment_text.value = (
                f"Pay Today: R{due_now:.0f}\n"
                f"Remaining Balance Due On Delivery Day: R{balance:.0f}"
            )
        except ValueError as error:
            total_text.value = f"Error: {error}"
            payment_text.value = ""

        page.update()

    def submit_order(e):
        valid = True

        if not customer_name.value:
            customer_name.error_text = "Customer name is required"
            valid = False
        else:
            customer_name.error_text = None

        if not phone_number.value:
            phone_number.error_text = "Phone number is required"
            valid = False
        else:
            phone_number.error_text = None

        if not perfume_name.value:
            perfume_name.error_text = "Perfume name is required"
            valid = False
        else:
            perfume_name.error_text = None

        if not size.value:
            size.error_text = "Select a size"
            valid = False
        else:
            size.error_text = None

        if not payment_option.value:
            payment_option.error_text = "Select a payment option"
            valid = False
        else:
            payment_option.error_text = None

        if REQUIRE_PROOF and not proof_state["file"]:
            proof_text.value = "⚠ Please upload your proof of payment"
            proof_text.color = "red"
            proof_text.italic = False
            valid = False

        try:
            total, amount_due, balance_due, qty, qty2 = compute_totals()
            quantity.error_text = None
        except ValueError as error:
            quantity.error_text = str(error)
            valid = False

        page.update()

        if not valid:
            return

        order_number = f"ZPS-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        order_date = datetime.now().strftime("%d %B %Y %H:%M")

        has_second = bool(perfume_name2.value and size2.value and qty2 > 0)

        order = Order(
            order_number,
            order_date,
            customer_name.value,
            phone_number.value,
            perfume_name.value,
            size.value,
            qty,
            perfume_name2.value if has_second else "",
            size2.value if has_second else "",
            qty2 if has_second else 0,
            total,
            payment_option.value,
            amount_due,
            balance_due,
            proof_state["file"],
        )

        try:
            manager.save_order(order)
        except Exception as error:
            page.open(ft.SnackBar(content=ft.Text(f"Could not save order: {error}")))
            return

        # Notify the owner in the background (customer sees nothing)
        threading.Thread(
            target=notify_admin, args=(order, has_second), daemon=True
        ).start()

        page.clean()
        page.add(
            ft.Text("✅ ORDER RECEIVED", size=30, weight="bold"),
            ft.Text(
                f"Order Number: {order_number}",
                size=16,
                weight="bold",
                color="blue",
            ),
            ft.Text(f"Date: {order_date}"),
            ft.Text(random.choice(THANK_YOU_MESSAGES), size=18),
            ft.Divider(),
            ft.Text("Order Summary", size=22, weight="bold"),
            ft.Text(f"Customer: {order.customer}"),
            ft.Text(f"Phone: {order.phone}"),
            ft.Text("Items Ordered", size=18, weight="bold"),
            ft.Text(f"1. {order.perfume} | {order.size} x {order.quantity}"),
            *(
                [ft.Text(f"2. {order.perfume2} | {order.size2} x {order.quantity2}")]
                if has_second else []
            ),
            ft.Text(f"Total: R{order.total}", weight="bold"),
            ft.Text(f"Pay Today: R{order.amount_due:.0f}"),
            ft.Text(f"Balance Due On Delivery Day: R{order.balance_due:.0f}"),
            ft.Text(
                "Proof of payment: Received ✅"
                if order.proof_of_payment else "Proof of payment: Not provided"
            ),
            ft.Divider(),
            ft.Text(
                "🌹 Thank you for choosing Zine Perfume Store. "
                "We look forward to serving you again!"
            ),
            ft.ElevatedButton("➕ New Order", on_click=new_order),
        )
        page.update()


    def new_order(e):
        reset_form()
        show_order_form()

    def is_set(value):
        return bool(value) and "PASTE" not in value

    def telegram_post(method, fields, file_field=None, file_path=None):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"

        if file_path is None:
            data = urllib.parse.urlencode(fields).encode()
            request = urllib.request.Request(url, data=data)
        else:
            boundary = uuid.uuid4().hex
            body = bytearray()
            for key, value in fields.items():
                body += (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode()
            body += (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{os.path.basename(file_path)}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            with open(file_path, "rb") as f:
                body += f.read()
            body += f"\r\n--{boundary}--\r\n".encode()
            request = urllib.request.Request(
                url,
                data=bytes(body),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )

        urllib.request.urlopen(request, timeout=30).read()

    def send_callmebot(text):
        query = urllib.parse.urlencode({
            "phone": OWNER_PHONE,
            "text": text,
            "apikey": CALLMEBOT_API_KEY,
        })
        urllib.request.urlopen(
            f"https://api.callmebot.com/whatsapp.php?{query}", timeout=30
        ).read()

    def send_twilio(text):
        to_number = OWNER_PHONE
        if TWILIO_FROM.startswith("whatsapp:"):
            to_number = f"whatsapp:{OWNER_PHONE}"

        url = (
            "https://api.twilio.com/2010-04-01/Accounts/"
            f"{TWILIO_ACCOUNT_SID}/Messages.json"
        )
        data = urllib.parse.urlencode(
            {"From": TWILIO_FROM, "To": to_number, "Body": text}
        ).encode()
        credentials = base64.b64encode(
            f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()
        ).decode()
        request = urllib.request.Request(
            url, data=data, headers={"Authorization": f"Basic {credentials}"}
        )
        urllib.request.urlopen(request, timeout=30).read()

    def log_notify_error(order, channel, error):
        # Never bother the customer - keep a log for the owner instead
        with open("notify_errors.log", "a") as log:
            log.write(f"{datetime.now()} | {order.order_number} | {channel} | {error}\n")

    def notify_admin(order, has_second):
        """Runs in the background: alerts the owner about a new order."""
        items = f"1) {order.perfume} {order.size} x{order.quantity}"
        if has_second:
            items += f" 2) {order.perfume2} {order.size2} x{order.quantity2}"

        short_text = (
            f"NEW ORDER {order.order_number}\n"
            f"{order.customer} ({order.phone})\n"
            f"{items}\n"
            f"Total R{order.total} | {order.payment_option}\n"
            f"Paid today R{order.amount_due:.0f}, balance R{order.balance_due:.0f}\n"
            f"Proof: {'uploaded - view in Admin' if order.proof_of_payment else 'none'}"
        )

        if is_set(CALLMEBOT_API_KEY):
            try:
                send_callmebot(short_text)
            except Exception as error:
                log_notify_error(order, "callmebot", error)

        if is_set(TWILIO_ACCOUNT_SID) and is_set(TWILIO_AUTH_TOKEN) and is_set(TWILIO_FROM):
            try:
                send_twilio(short_text)
            except Exception as error:
                log_notify_error(order, "twilio", error)

        if is_set(TELEGRAM_BOT_TOKEN) and is_set(TELEGRAM_CHAT_ID):
            try:
                telegram_post(
                    "sendMessage",
                    {"chat_id": TELEGRAM_CHAT_ID, "text": short_text},
                )

                if order.proof_of_payment:
                    proof_path = os.path.join(PROOF_FOLDER, order.proof_of_payment)

                    # Web uploads can take a few seconds to finish arriving
                    for _ in range(20):
                        if os.path.exists(proof_path):
                            break
                        time.sleep(0.5)

                    if os.path.exists(proof_path):
                        is_image = proof_path.lower().endswith((".jpg", ".jpeg", ".png"))
                        telegram_post(
                            "sendPhoto" if is_image else "sendDocument",
                            {
                                "chat_id": TELEGRAM_CHAT_ID,
                                "caption": f"Proof - {order.customer} ({order.order_number})",
                            },
                            file_field="photo" if is_image else "document",
                            file_path=proof_path,
                        )
            except Exception as error:
                log_notify_error(order, "telegram", error)

    def open_file_externally(path):
        """Open a file (e.g. a PDF) with the computer's default viewer."""
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as error:
            page.open(ft.SnackBar(content=ft.Text(f"Could not open file: {error}")))

    def show_proof(filename):
        """Show a proof-of-payment image in a pop-up (PDFs open externally)."""
        path = os.path.join(PROOF_FOLDER, filename)

        if not os.path.exists(path):
            page.open(
                ft.SnackBar(content=ft.Text("Proof file not found in the proofs folder"))
            )
            return

        if filename.lower().endswith(".pdf"):
            open_file_externally(os.path.abspath(path))
            return

        try:
            with open(path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode()
        except Exception as error:
            page.open(ft.SnackBar(content=ft.Text(f"Could not read file: {error}")))
            return

        def close_proof(e):
            page.close(proof_dialog)

        proof_dialog = ft.AlertDialog(
            title=ft.Text("🧾 Proof of Payment"),
            content=ft.Container(
                content=ft.Column(
                    [ft.Image(src_base64=image_data, width=450)],
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=480,
                height=600,
            ),
            actions=[ft.TextButton("Close", on_click=close_proof)],
        )
        page.open(proof_dialog)

    def view_orders(e):
        page.clean()
        page.add(ft.Text("📋 Customer Orders", size=30, weight="bold"))

        try:
            orders = manager.load_orders()

            if not orders:
                page.add(ft.Text("No orders found."))
            else:
                for order in orders:
                    lines = [
                        ft.Text(f"Order: {order.get('order_number', '-')}"),
                        ft.Text(f"Customer: {order.get('customer', '-')}"),
                        ft.Text(f"Phone: {order.get('phone', '-')}"),
                        ft.Text(
                            f"1. {order.get('perfume', '-')} | "
                            f"{order.get('size', '-')} x {order.get('quantity', '-')}"
                        ),
                    ]
                    if order.get("perfume2"):
                        lines.append(
                            ft.Text(
                                f"2. {order['perfume2']} | "
                                f"{order.get('size2', '-')} x {order.get('quantity2', '-')}"
                            )
                        )
                    lines.append(ft.Text(f"Total: R{order.get('total', 0)}"))
                    lines.append(
                        ft.Text(f"Payment Option: {order.get('payment_option', '-')}")
                    )
                    lines.append(
                        ft.Text(f"Proof of Payment: {order.get('proof_of_payment') or 'Not provided'}")
                    )
                    if order.get("proof_of_payment"):
                        lines.append(
                            ft.ElevatedButton(
                                "👁 View Proof",
                                on_click=lambda e, f=order["proof_of_payment"]: show_proof(f),
                            )
                        )

                    page.add(
                        ft.Container(
                            content=ft.Column(lines),
                            padding=10,
                            border=ft.border.all(1),
                        )
                    )
        except Exception as error:
            page.add(ft.Text(f"Error: {error}", color="red"))

        page.add(
            ft.ElevatedButton("← Back", on_click=lambda e: show_order_form())
        )
        page.update()

    # ---------------------------------------------------------------
    # Buttons
    # ---------------------------------------------------------------
    calculate_button = ft.ElevatedButton(
        text="Calculate Total",
        on_click=calculate_total,
    )
    submit_button = ft.ElevatedButton(
        text="✅ SUBMIT ORDER",
        on_click=submit_order,
    )

    # ---------------------------------------------------------------
    # Admin login (password-protected access to orders)
    # ---------------------------------------------------------------
    def open_admin_login(e):
        password_field = ft.TextField(
            label="Admin Password",
            password=True,
            can_reveal_password=True,
            autofocus=True,
        )

        def close_dialog(e=None):
            page.close(dialog)

        def check_password(e):
            if password_field.value == ADMIN_PASSWORD:
                page.close(dialog)
                view_orders(None)
            else:
                password_field.error_text = "Incorrect password"
                password_field.value = ""
                page.update()

        password_field.on_submit = check_password

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("🔒 Admin Login"),
            content=password_field,
            actions=[
                ft.TextButton("Cancel", on_click=close_dialog),
                ft.ElevatedButton("Login", on_click=check_password),
            ],
        )
        page.open(dialog)

    admin_button = ft.TextButton(
        text="Admin",
        on_click=open_admin_login,
    )

    # ---------------------------------------------------------------
    # Main form screen
    # ---------------------------------------------------------------
    def show_order_form():
        page.clean()
        page.add(
            ft.Text("✨✨✨ Zine Perfume Store ✨✨✨", size=30, weight="bold"),
            customer_name,
            phone_number,
            perfume_name,
            size,
            quantity,
            ft.Divider(),
            ft.Text("Additional Perfume (Optional)", size=18, weight="bold"),
            perfume_name2,
            size2,
            quantity2,
            ft.Divider(),
            payment_option,
            calculate_button,
            total_text,
            payment_text,
            payment_details,
            ft.Divider(),
            ft.Text("Proof of Payment", size=18, weight="bold"),
            upload_proof_button,
            proof_text,
            submit_button,
            admin_button,
            ft.Container(height=20),
        )
        page.update()

    show_order_form()


ft.app(target=main, upload_dir=PROOF_FOLDER)