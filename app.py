from flask import Flask, render_template, request, redirect, url_for
import re
import os
import threading
import time

app = Flask(__name__)

FLAG = "Securinets{st0r3d_xss_4dm1n_c00k13_st34l}"

# In-memory message store
MESSAGES = []
MSG_ID = 0
REPORTED = set()


def sanitize(text: str) -> str:
    """Medium filter: blocks <script, onerror=, onload= (case-insensitive)"""
    if not text:
        return ""
    text = re.sub(r"<\s*script", "", text, flags=re.IGNORECASE)
    text = re.sub(r"onerror\s*=", "", text, flags=re.IGNORECASE)
    text = re.sub(r"onload\s*=", "", text, flags=re.IGNORECASE)
    return text


def get_bot_base_url():
    """Determine the base URL the bot should visit."""
    # Prefer explicit env var (set this on Render to your public URL)
    if os.environ.get("BOT_BASE_URL"):
        return os.environ["BOT_BASE_URL"].rstrip("/")
    # Fallback for local / same-container
    port = os.environ.get("PORT", "5000")
    return f"http://127.0.0.1:{port}"


def run_admin_bot(msg_id: int):
    """Visit the guestbook as admin (Playwright headless)."""
    try:
        from playwright.sync_api import sync_playwright

        time.sleep(1.0)  # let the response finish

        base = get_bot_base_url()
        url = base + "/"

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            context = browser.new_context()
            context.add_cookies([{
                "name": "flag",
                "value": FLAG,
                "url": base,
                "httpOnly": False,
                "sameSite": "Lax"
            }])
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=20000)
            page.wait_for_timeout(3000)  # time for XSS to execute
            browser.close()
            print(f"[bot] visited {url} for message {msg_id}")
    except Exception as e:
        print(f"[bot] error: {e}")


@app.route("/", methods=["GET", "POST"])
def index():
    global MSG_ID

    if request.method == "POST":
        name = request.form.get("name", "").strip()[:40]
        message = request.form.get("message", "").strip()[:500]

        if name and message:
            MSG_ID += 1
            MESSAGES.append({
                "id": MSG_ID,
                "name": sanitize(name),
                "message": sanitize(message),
            })
        return redirect(url_for("index"))

    return render_template("index.html", messages=list(reversed(MESSAGES)))


@app.route("/report/<int:msg_id>", methods=["POST"])
def report(msg_id):
    if msg_id in REPORTED:
        return redirect(url_for("index"))

    exists = any(m["id"] == msg_id for m in MESSAGES)
    if not exists:
        return redirect(url_for("index"))

    REPORTED.add(msg_id)

    t = threading.Thread(target=run_admin_bot, args=(msg_id,), daemon=True)
    t.start()

    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
