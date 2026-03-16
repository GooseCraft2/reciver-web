from flask import Flask, render_template, request, jsonify, session
import requests, json, time, os

app = Flask(__name__)
app.secret_key = os.urandom(24)

DB_URL  = "https://messendjer-e4d10-default-rtdb.europe-west1.firebasedatabase.app"
API_KEY = "AIzaSyADx4iNnP6IvttRE1ud_jv9bC217M0PEDg"

def db_get(path, token):
    try:
        r = requests.get(f"{DB_URL}/{path}.json", params={"auth": token}, timeout=10)
        return r.json() if r.ok else None
    except: return None

def db_set(path, data, token):
    try: return requests.put(f"{DB_URL}/{path}.json", json=data, params={"auth": token}, timeout=10).ok
    except: return False

def db_patch(path, data, token):
    try: return requests.patch(f"{DB_URL}/{path}.json", json=data, params={"auth": token}, timeout=10).ok
    except: return False

def db_push(path, data, token):
    try:
        r = requests.post(f"{DB_URL}/{path}.json", json=data, params={"auth": token}, timeout=10)
        return r.json().get("name") if r.ok else None
    except: return None

def db_delete(path, token):
    try: return requests.delete(f"{DB_URL}/{path}.json", params={"auth": token}, timeout=10).ok
    except: return False

def dm_id(a, b):
    return "dm_" + "_".join(sorted([a, b]))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/login", methods=["POST"])
def login():
    d = request.json
    r = requests.post(f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}",
        json={"email": d["email"], "password": d["password"], "returnSecureToken": True}, timeout=10).json()
    if "idToken" in r:
        session["token"] = r["idToken"]
        session["uid"] = r["localId"]
        return jsonify({"ok": True, "uid": r["localId"]})
    return jsonify({"ok": False, "error": r.get("error", {}).get("message", "Ошибка")})

@app.route("/api/register", methods=["POST"])
def register():
    d = request.json
    r = requests.post(f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}",
        json={"email": d["email"], "password": d["password"], "returnSecureToken": True}, timeout=10).json()
    if "idToken" in r:
        import random, string
        code = f"{''.join(random.choices(string.ascii_uppercase,k=3))}-{''.join(random.choices(string.digits,k=4))}"
        token = r["idToken"]; uid = r["localId"]
        db_set(f"users/{uid}", {
            "nickname": d.get("nickname", d["email"].split("@")[0]),
            "email": d["email"], "uid": uid,
            "online": True, "last_seen": int(time.time()),
            "friend_code": code, "avatar": ""
        }, token)
        db_set(f"friend_codes/{code}", uid, token)
        session["token"] = token; session["uid"] = uid
        return jsonify({"ok": True, "uid": uid})
    return jsonify({"ok": False, "error": r.get("error", {}).get("message", "Ошибка")})

@app.route("/api/logout", methods=["POST"])
def logout():
    uid = session.get("uid"); token = session.get("token")
    if uid and token: db_patch(f"users/{uid}", {"online": False}, token)
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/me")
def me():
    token = session.get("token"); uid = session.get("uid")
    if not token or not uid: return jsonify({"ok": False})
    data = db_get(f"users/{uid}", token)
    if not data: return jsonify({"ok": False})
    db_patch(f"users/{uid}", {"online": True, "last_seen": int(time.time())}, token)
    return jsonify({"ok": True, "uid": uid, "data": data})

@app.route("/api/messages/<chat_id>")
def get_messages(chat_id):
    token = session.get("token")
    if not token: return jsonify({"ok": False})
    data = db_get(f"chats/{chat_id}", token) or {}
    msgs = []
    if isinstance(data, dict):
        msgs = sorted([{"key": k, **v} for k,v in data.items() if isinstance(v, dict)], key=lambda x: x.get("ts", 0))
    return jsonify({"ok": True, "messages": msgs})

@app.route("/api/send", methods=["POST"])
def send():
    token = session.get("token"); uid = session.get("uid")
    if not token: return jsonify({"ok": False})
    d = request.json
    me = db_get(f"users/{uid}", token) or {}
    msg = {"uid": uid, "nickname": me.get("nickname","?"), "text": d["text"],
           "ts": int(time.time()), "avatar": me.get("avatar",""), "type": "text"}
    key = db_push(f"chats/{d['chat_id']}", msg, token)
    return jsonify({"ok": bool(key)})

@app.route("/api/friends")
def friends():
    token = session.get("token"); uid = session.get("uid")
    if not token: return jsonify({"ok": False})
    data = db_get(f"friends/{uid}", token) or {}
    return jsonify({"ok": True, "friends": data})

@app.route("/api/requests")
def friend_requests():
    token = session.get("token"); uid = session.get("uid")
    if not token: return jsonify({"ok": False})
    data = db_get(f"friend_requests/{uid}", token) or {}
    return jsonify({"ok": True, "requests": data})

@app.route("/api/add_friend", methods=["POST"])
def add_friend():
    token = session.get("token"); uid = session.get("uid")
    if not token: return jsonify({"ok": False})
    code = request.json.get("code","").strip().upper()
    tuid = db_get(f"friend_codes/{code}", token)
    if not tuid or tuid == uid: return jsonify({"ok": False, "error": "Код не найден"})
    me = db_get(f"users/{uid}", token) or {}
    db_set(f"friend_requests/{tuid}/{uid}", {"nickname": me.get("nickname","?"), "avatar": me.get("avatar",""), "ts": int(time.time())}, token)
    return jsonify({"ok": True})

@app.route("/api/accept_friend", methods=["POST"])
def accept_friend():
    token = session.get("token"); uid = session.get("uid")
    if not token: return jsonify({"ok": False})
    ruid = request.json.get("uid")
    td = db_get(f"users/{ruid}", token) or {}
    me = db_get(f"users/{uid}", token) or {}
    db_set(f"friends/{uid}/{ruid}", {"nickname": td.get("nickname","?"), "avatar": td.get("avatar",""), "online": td.get("online",False)}, token)
    db_set(f"friends/{ruid}/{uid}", {"nickname": me.get("nickname","?"), "avatar": me.get("avatar",""), "online": True}, token)
    db_delete(f"friend_requests/{uid}/{ruid}", token)
    return jsonify({"ok": True})

@app.route("/api/decline_friend", methods=["POST"])
def decline_friend():
    token = session.get("token"); uid = session.get("uid")
    if not token: return jsonify({"ok": False})
    ruid = request.json.get("uid")
    db_delete(f"friend_requests/{uid}/{ruid}", token)
    return jsonify({"ok": True})

@app.route("/api/users")
def users():
    token = session.get("token")
    if not token: return jsonify({"ok": False})
    data = db_get("users", token) or {}
    return jsonify({"ok": True, "users": data})

@app.route("/api/dm_id")
def get_dm_id():
    uid = session.get("uid")
    other = request.args.get("other","")
    return jsonify({"dm_id": dm_id(uid, other)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
