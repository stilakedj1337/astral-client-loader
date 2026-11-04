import os, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests

BOT_TOKEN = os.getenv("9068347313:AAEw6w2mnGufjGoG02IsMAqBH0Rf5Ci3RX4", "").strip()
CHAT_ID   = os.getenv("5884767841", "").strip()
PORT      = int(os.getenv("PORT", 10000))

print(f"Запуск бота... Токен: {BOT_TOKEN[:10]}...", flush=True)

def bot_loop():
    offset = None
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                             params={"timeout": 30, "offset": offset}, timeout=40)
            data = r.json()
            if not data.get("ok"):
                print(f"Ошибка Telegram API: {data}", flush=True)
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = msg.get("text", "")
                chat = msg.get("chat", {}).get("id")
                if text.startswith("/start"):
                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                  data={"chat_id": chat, "text": "AstralClient bot online. Send /get to fetch reports."})
                elif text.startswith("/get") and str(chat) == str(CHAT_ID):
                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                  data={"chat_id": chat, "text": "No new reports."})
        except Exception as e:
            print(f"Ошибка в цикле: {e}", flush=True)
            time.sleep(5)

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, *a): pass

def keepalive():
    srv = HTTPServer(("0.0.0.0", PORT), Health)
    srv.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    keepalive()
