import copy
import os
import json
import re
import subprocess
import time
from datetime import datetime

import requests
from config import BALE_TOKEN

BASE = f"https://tapi.bale.ai/bot{BALE_TOKEN}"

MAX_HISTORY_PER_USER = 30
MAX_RECENT_CHATS_SHOWN = 8
MODELS_CACHE_TTL_SECONDS = 120
MAX_MODEL_LIST = 12

THINKING_ALIASES = {
    "light": "low",
    "low": "low",
    "medium": "medium",
    "med": "medium",
    "extra": "xhigh",
    "high": "high",
    "max": "max",
    "off": "off",
    "minimal": "minimal",
}

THINKING_DISPLAY = {
    "off": "خاموش",
    "minimal": "حداقل",
    "low": "light",
    "medium": "medium",
    "high": "high",
    "xhigh": "extra",
    "adaptive": "adaptive",
    "max": "max",
}

user_states = {}
models_cache = {
    "openai": {"fetched_at": 0, "items": []},
    "all": {"fetched_at": 0, "items": []},
}
STATE_FILE = os.path.join(os.path.dirname(__file__), "history.json")


def load_persisted_states():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print("Load state error:", exc)
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def ensure_required_state_fields(state):
    normalized = {
        "active": False,
        "current_session": None,
        "recent_chats": [],
        "model": None,
        "thinking": "low",
        "session_message_ids": [],
    }
    if not isinstance(state, dict):
        return normalized

    normalized.update({
        "active": bool(state.get("active", False)),
        "current_session": state.get("current_session") if isinstance(state.get("current_session"), dict) else None,
        "recent_chats": state.get("recent_chats", []) if isinstance(state.get("recent_chats", []), list) else [],
        "model": state.get("model"),
        "thinking": state.get("thinking", "low") or "low",
        "session_message_ids": state.get("session_message_ids", []) if isinstance(state.get("session_message_ids", []), list) else [],
    })
    return normalized


def restore_message_ids():
    raw = load_persisted_states()
    for key, value in raw.items():
        user_states[int(key)] = ensure_required_state_fields(value)


def save_states():
    serializable = {
        str(k): v for k, v in user_states.items()
        if isinstance(v, dict)
    }
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print("Save state error:", exc)


def extract_message_id(payload):
    if not isinstance(payload, dict):
        return None

    if isinstance(payload.get("result"), dict):
        message_id = payload["result"].get("message_id")
        if message_id is not None:
            return int(message_id)

    message_id = payload.get("message_id")
    if message_id is not None:
        return int(message_id)

    return None


def call_bale_json(method, payload, timeout=20):
    url = BASE + "/" + method
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        data = parse_embedded_json((r.text or "").strip())
        if isinstance(data, dict):
            data["http_status"] = r.status_code
        return data
    except Exception as exc:
        print("Bale request error:", exc)
        return {"http_status": 0, "ok": False, "error": str(exc)}


def delete_messages_in_chat(chat_id, message_ids):
    if not message_ids:
        return 0

    unique = list(dict.fromkeys([int(x) for x in message_ids if isinstance(x, int)]))
    deleted = 0

    def normalize_resp(result):
        if isinstance(result, dict):
            if isinstance(result.get("ok"), bool):
                return result
            if isinstance(result.get("result"), bool):
                return {"ok": bool(result.get("result"))}
            if isinstance(result.get("result"), int):
                return {"ok": result.get("result") > 0}
            return result
        return {"ok": False}

    # حذف چندتایی (در صورت وجود)
    if len(unique) > 1:
        batch_payload = {"chat_id": chat_id, "message_ids": unique}
        result = normalize_resp(call_bale_json("deleteMessages", batch_payload))
        if result.get("ok"):
            deleted = len(unique)
            return deleted

    for mid in unique:
        result = normalize_resp(call_bale_json("deleteMessage", {
            "chat_id": chat_id,
            "message_id": mid
        }))
        if result.get("ok"):
            deleted += 1
    return deleted


def send_message(chat_id, text):
    result = call_bale_json("sendMessage", {"chat_id": chat_id, "text": text})
    print("Bale send:", result)
    if not isinstance(result, dict):
        return None
    return extract_message_id(result)


def get_updates(offset=None):
    url = BASE + "/getUpdates"
    params = {"timeout": 15}

    if offset is not None:
        params["offset"] = offset

    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print("Get updates error:", exc)
        return {"result": []}


def parse_embedded_json(text):
    if not isinstance(text, str) or not text.strip():
        return None

    try:
        return json.loads(text)
    except Exception:
        pass

    decoder = json.JSONDecoder()
    for start in ("{", "["):
        pos = text.find(start)
        while pos != -1:
            try:
                parsed, _ = decoder.raw_decode(text[pos:])
                return parsed
            except Exception:
                pos = text.find(start, pos + 1)

    return None


def run_openclaw_json_command(args, timeout=20):
    cmd = ["openclaw", *args]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
    except Exception as exc:
        print("OpenClaw command error:", exc)
        return None

    output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    if not output:
        return {"text": "", "returncode": result.returncode}

    parsed = parse_embedded_json(output)
    if parsed is not None:
        return parsed

    return {"text": output, "returncode": result.returncode}


def is_valid_model(model_id):
    if not isinstance(model_id, str):
        return False

    model_id = model_id.strip()
    if not model_id:
        return False
    if model_id.endswith("/"):
        return False
    if model_id.endswith("/.") or model_id == ".":
        return False
    if "/" not in model_id and ":" not in model_id:
        return False
    return True


def get_error_text(data):
    if not isinstance(data, dict):
        return None

    if isinstance(data.get("error"), str) and data["error"].strip():
        return data["error"].strip()
    if isinstance(data.get("message"), str) and data["message"].strip():
        return data["message"].strip()

    result = data.get("result")
    if isinstance(result, dict):
        if isinstance(result.get("error"), str) and result["error"].strip():
            return result["error"].strip()
        if isinstance(result.get("message"), str) and result["message"].strip():
            return result["message"].strip()

    return None


def _is_cache_fresh(entry):
    return (datetime.now().timestamp() - entry.get("fetched_at", 0)) < MODELS_CACHE_TTL_SECONDS


def get_models(provider="openai"):
    key = provider or "all"
    entry = models_cache.get(key, {"fetched_at": 0, "items": []})
    if _is_cache_fresh(entry) and entry["items"]:
        return entry["items"]

    cmd = ["models", "list", "--json", "--all"]
    if provider and provider.lower() != "all":
        cmd.extend(["--provider", provider])

    data = run_openclaw_json_command(cmd)
    items = []

    if isinstance(data, dict) and isinstance(data.get("models"), list):
        for item in data["models"]:
            if not isinstance(item, dict):
                continue

            model_key = (item.get("key") or "").strip()
            if not is_valid_model(model_key):
                continue

            if provider and provider.lower() != "all":
                provider_prefix = model_key.split("/", 1)[0].lower()
                if provider_prefix != provider.lower():
                    continue

            items.append({
                "key": model_key,
                "name": item.get("name") or model_key,
                "available": bool(item.get("available", True)),
                "contextWindow": item.get("contextWindow"),
            })

    models_cache[key] = {
        "fetched_at": datetime.now().timestamp(),
        "items": items
    }
    return items


def get_default_model():
    candidates = get_models("openai") or get_models("all")
    for item in candidates:
        if item.get("available", True) and is_valid_model(item.get("key", "")):
            return item["key"]
    return None


def resolve_model_selection(items, selection):
    if not selection:
        return None, "شناسه مدل وارد نشده است."

    if selection.isdigit():
        idx = int(selection)
        if idx <= 0 or idx > len(items):
            return None, "شماره انتخابی نامعتبر است."
        return items[idx - 1]["key"], None

    lowered = selection.lower()
    exact = [item["key"] for item in items if item["key"].lower() == lowered]
    if exact:
        return exact[0], None

    contains = [item["key"] for item in items if lowered in item["key"].lower() or lowered in item["name"].lower()]
    if len(contains) == 1:
        return contains[0], None
    if len(contains) > 1:
        return None, "چند مدل مشابه پیدا شد. از index استفاده کنید: `/models 2`"

    return None, "مدل پیدا نشد. اول `/models` را بزن و انتخاب کن."


def format_model_list(items, state):
    if not items:
        return "هیچ مدلی پیدا نشد."

    current = state.get("model")
    lines = []
    for idx, item in enumerate(items[:MAX_MODEL_LIST], start=1):
        marker = " ✅" if current == item["key"] else ""
        availability = "●" if item.get("available", False) else "○"
        context = f" | {item.get('contextWindow')}" if item.get("contextWindow") else ""
        lines.append(f"{idx}. {availability} {item['key']}{context}{marker}")

    if len(items) > MAX_MODEL_LIST:
        lines.append(f"... و {len(items) - MAX_MODEL_LIST} مدل دیگر.")

    return "\n".join(lines)


def set_model(state, arg):
    arg = (arg or "").strip()
    if not arg:
        return (
            "برای انتخاب مدل:\n"
            "• /models → لیست مدل‌ها\n"
            "• /models 3 → انتخاب آیتم 3\n"
            "• /models openai/gpt-5.5 → انتخاب مستقیم\n"
            "بعد از انتخاب، همین پیام را دوباره اگر خواستی با مدل جدید بزن."
        )

    models = get_models("openai")
    if not models:
        return "فعلاً لیست OpenAI دریافت نشد. دوباره /models all بزن."

    model_id, err = resolve_model_selection(models, arg)
    if err:
        return err

    state["model"] = model_id
    return (
        f"✅ مدل فعلی تنظیم شد: {model_id}\n"
        "اگر برای ادامه می‌خوای مدل دیگه‌ای بزنی: /models <id/index>."
    )


def set_thinking(state, arg):
    arg = (arg or "").strip().lower()
    if not arg:
        display = THINKING_DISPLAY.get(state.get("thinking", "low"), state.get("thinking", "low"))
        return (
            f"📌 thinking فعلی: {display}\n"
            "برای تغییر: /reasoning <توضیح>\n"
            "مثال: /reasoning light یا /reasoning medium یا /reasoning extra"
        )

    if arg not in THINKING_ALIASES:
        return (
            "⚠️ مقدار نامعتبر.\n"
            "گزینه‌های معتبر: light medium extra high max off minimal.\n"
            "مثال: /reasoning medium"
        )

    state["thinking"] = THINKING_ALIASES[arg]
    return (
        f"✅ thinking روی {THINKING_DISPLAY.get(state['thinking'], state['thinking'])} تنظیم شد.\n"
        "برای تغییر مجدد: /reasoning light / /reasoning medium / /reasoning extra"
    )


def create_state():
    return {
        "active": False,
        "current_session": None,
        "recent_chats": [],
        "model": None,
        "thinking": "low",
        "session_message_ids": [],
    }


def get_user_state(chat_id):
    if chat_id not in user_states:
        user_states[chat_id] = create_state()
    return user_states[chat_id]


def ensure_model(state):
    if state.get("model") and is_valid_model(state.get("model")):
        return state["model"]

    default_model = get_default_model()
    state["model"] = default_model
    return default_model


def create_new_session(state):
    state["current_session"] = {
        "id": f"user:{int(time.time_ns())}",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "messages": [],
        "message_ids": [],
    }
    state["active"] = True

    pending = state.get("session_message_ids")
    if isinstance(pending, list) and pending:
        for mid in pending:
            if isinstance(mid, int) and mid not in state["current_session"]["message_ids"]:
                state["current_session"]["message_ids"].append(mid)
        state["session_message_ids"] = []


def _add_message_id_to_session(state, message_id):
    if not isinstance(message_id, int):
        return

    container = None
    if state.get("current_session") and isinstance(state.get("current_session"), dict):
        container = state["current_session"].setdefault("message_ids", [])
    else:
        container = state.setdefault("session_message_ids", [])

    if isinstance(container, list) and message_id not in container:
        container.append(message_id)


def append_user_message_id(state, message_id):
    _add_message_id_to_session(state, message_id)


def append_assistant_message_id(state, message_id):
    _add_message_id_to_session(state, message_id)


def build_session_key(state):
    session = state.get("current_session")
    if not session:
        return None
    return f"agent:main:{session['id']}"


def summarize_chat(session):
    for msg in session.get("messages", []):
        if msg.get("role") == "user" and msg.get("text"):
            return f"{session['id']} | {msg['text'].replace('\\n', ' ')[:45]}"
    return f"{session['id']} | (بدون پیام)"


def archive_current_session(state, reason="manual"):
    current = state.get("current_session")
    if not current:
        return

    if current.get("messages"):
        archived = copy.deepcopy(current)
        archived["closed_at"] = datetime.now().isoformat(timespec="seconds")
        archived["reason"] = reason
        archived["summary"] = summarize_chat(current)
        state["recent_chats"].insert(0, archived)
        state["recent_chats"] = state["recent_chats"][:MAX_HISTORY_PER_USER]

    state["session_message_ids"] = []
    state["current_session"] = None


def clear_current_chat_history(state):
    current = state.get("current_session")
    if current:
        ids_to_clear = [mid for mid in current.get("message_ids", []) if isinstance(mid, int)]
        current["message_ids"] = []
        current["messages"] = []
    else:
        ids_to_clear = []

    pending = state.get("session_message_ids", [])
    if isinstance(pending, list):
        ids_to_clear.extend([mid for mid in pending if isinstance(mid, int)])
        state["session_message_ids"] = []
    return list(dict.fromkeys(ids_to_clear))


def remove_recent_chats_message_ids(state):
    ids_to_clear = []
    for item in state.get("recent_chats", []):
        for mid in item.get("message_ids", []):
            if isinstance(mid, int):
                ids_to_clear.append(mid)
        item["message_ids"] = []
    state["recent_chats"] = []
    return list(dict.fromkeys(ids_to_clear))


def clear_all_state_history(state):
    pending_ids = list(dict.fromkeys([mid for mid in state.get("session_message_ids", []) if isinstance(mid, int)]))
    state["session_message_ids"] = []
    state["recent_chats"] = []

    current = state.get("current_session")
    if current:
        for mid in current.get("message_ids", []):
            if isinstance(mid, int):
                pending_ids.append(mid)
        current["message_ids"] = []
        current["messages"] = []
        return list(dict.fromkeys(pending_ids))

    return pending_ids
    return ids_to_clear


def list_recent_chats_text(state):
    if not state.get("recent_chats"):
        return "هیچ هیستوری ذخیره‌ای موجود نیست."

    lines = []
    for idx, item in enumerate(state["recent_chats"][:MAX_RECENT_CHATS_SHOWN], start=1):
        created = item.get("closed_at", item.get("created_at", ""))
        lines.append(f"{idx}. {created} | {item.get('summary', '---')}")
    return "\n".join(lines)


def delete_recent_chats(state, arg):
    if not state.get("recent_chats"):
        return "هیچ هیستوری برای حذف وجود ندارد."

    action = (arg or "").strip().lower()
    if action == "all":
        count = len(state["recent_chats"])
        state["recent_chats"] = []
        return f"✅ همه هیستوری‌ها ({count}) حذف شد."

    if not action:
        return (
            "برای حذف هیستوری:\n"
            "1) حذف همه: /deletehistory all\n"
            "2) حذف یک مورد: /deletehistory 2\n"
            "برای دیدن لیست: /recentchats"
        )

    if action.isdigit():
        idx = int(action)
        if idx <= 0 or idx > len(state["recent_chats"]):
            return "شماره نامعتبر است. برای لیست: /recentchats"
        removed = state["recent_chats"].pop(idx - 1)
        summary = removed.get("summary", removed.get("id", ""))
        return f"✅ آیتم {idx} حذف شد: {summary}"

    return "فرمت نامعتبر. مثال: /deletehistory all یا /deletehistory 2"


def set_active_from_history(state, index):
    if index <= 0 or index > len(state.get("recent_chats", [])):
        return False

    selected = copy.deepcopy(state["recent_chats"][index - 1])
    selected.pop("summary", None)
    selected.pop("closed_at", None)
    selected.pop("reason", None)
    state["current_session"] = selected
    state["active"] = True
    return True


def _pick_number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        m = re.search(r"\d+[\d,]*", value.replace(",", ""))
        if m:
            return int(m.group(0).replace(",", ""))
    return None


def _find_usage_numbers(data, path=""):
    remaining_keys = {"remaining", "left", "balance", "available"}
    total_keys = {"total", "quota", "limit", "capacity", "max", "allotted", "budget"}
    snapshots = []

    if isinstance(data, dict):
        current = {}
        for key, value in data.items():
            low = str(key).lower()
            num = _pick_number(value)
            if num is not None and any(k in low for k in remaining_keys):
                current["remaining"] = num
            if num is not None and any(k in low for k in total_keys):
                current["total"] = num
            nested = _find_usage_numbers(value, f"{path}.{low}" if path else low)
            snapshots.extend(nested)

        if "remaining" in current:
            snapshots.append(current)
        return snapshots

    if isinstance(data, list):
        for item in data:
            snapshots.extend(_find_usage_numbers(item, path))
        return snapshots

    return []


def _format_usage_graph(value, total=None):
    if value is None:
        return "⚪️ مقدار معتبر یافت نشد."

    value_num = int(value)
    if value_num < 0:
        return "⚪️ مقدار نامعتبر."

    if total and total > 0:
        ratio = min(1.0, value_num / total)
        bars = 14
        fill = int(ratio * bars)
        bar = "🟩" * fill + "⬜" * (bars - fill)
        percent = int(ratio * 100)
        return f"{bar} {percent}%\nباقی‌مانده: {value_num:,} / {int(total):,}"

    if value_num >= 1_000_000:
        bars = 14
    elif value_num >= 200_000:
        bars = 11
    elif value_num >= 50_000:
        bars = 8
    elif value_num > 10_000:
        bars = 5
    else:
        bars = 2

    full = min(14, bars)
    bar = "🟩" * full + "⬜" * (14 - full)
    return f"{bar}\nباقی‌مانده: {value_num:,}"


def get_remaining_usage():
    candidate_commands = [
        ["status", "--json", "--usage"],
        ["models", "status", "--json"],
    ]

    for cmd in candidate_commands:
        data = run_openclaw_json_command(cmd)
        if not data:
            continue
        snapshots = _find_usage_numbers(data)
        if snapshots:
            first = snapshots[0]
            return _format_usage_graph(first.get("remaining"), first.get("total"))

    if isinstance(data, dict):
        text = data.get("text")
        if isinstance(text, str) and text.strip():
            return text[:400]

    return "نتوانستم میزان باقی‌مانده توکن را دریافت کنم."


def ask_openclaw(message, session_key, model_id, thinking_level):
    model_id = model_id if is_valid_model(model_id) else None

    cmd = [
        "agent",
        "--session-key",
        session_key,
        "--thinking",
        thinking_level,
        "-m",
        message,
        "--json"
    ]
    if model_id:
        cmd.extend(["--model", model_id])

    data = run_openclaw_json_command(cmd)
    if not data:
        return "خطا در دریافت پاسخ هوش مصنوعی"

    error = get_error_text(data)
    if error:
        if "unknown model" in error.lower() or "unknownprovider" in error.lower():
            return (
                "⚠️ مدل انتخابی معتبر نیست (`openai/.` می‌تواند علت باشد).\n"
                "دستور `/models` را بزن و یک مدل معتبر انتخاب کن."
            )
        return error

    if isinstance(data, dict):
        answer = data.get("result", {}).get("payloads", [{}])[0].get("text")
        if not answer:
            answer = data.get("text")
        if isinstance(answer, str) and answer.strip():
            return answer.strip()

    return "پاسخ خالی دریافت شد."


def ensure_openclaw_ready():
    model = get_default_model()
    if not model:
        return None
    return True


def help_text():
    return """
دستورات:

/start                     شروع بات
/end یا /exit           توقف گفتگو و ذخیره در هیستوری
/newchat یا /new  گفتگو جدید
/recentchats         لیست هیستوری
/Continuechat       ادامه از هیستوری (مثال: /Continuechat 2)
/clear                     حذف تمامی پیام‌های همین چت در بله + ریست هیستوری فعلی
/deletehistory        حذف یک مورد یا همه هیستوری
/models                 لیست مدل‌های OpenAI
/models                 انتخاب مدل
/reasoning             تنظیم سختی
light|medium|extra|high|max|off|minimal
/remainingusage   مانده توکن (گرافیکی)
/help                      راهنما
""".strip()


def main():
    print("🚀 Bale + OpenClaw running")
    restore_message_ids()
    ensure_openclaw_ready()
    offset = None

    while True:
        data = get_updates(offset)

        for item in data.get("result", []):
            offset = item.get("update_id", 0) + 1

            msg = item.get("message")
            if not msg:
                continue

            chat_id = msg["chat"]["id"]
            text = (msg.get("text") or "").strip()
            if not text:
                continue

            state = get_user_state(chat_id)
            if not ensure_model(state):
                send_message(chat_id, "❗ تنظیم مدل انجام نشد؛ `openclaw models list` را بررسی کن.")
                save_states()
                continue

            parts = text.split(" ", 1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            append_user_message_id(state, msg.get("message_id"))

            if cmd == "/start":
                if not state["current_session"]:
                    create_new_session(state)
                else:
                    state["active"] = True

                send_message(
                    chat_id,
                    "🤖 OpenClaw فعال شد!\n\n"
                    "الان پیام بده.\n"
                    "/end برای خاموش کردن\n"
                    "/newchat برای چت جدید\n"
                    "/recentchats برای هیستوری\n"
                    "/Continuechat 1 برای ادامه از هیستوری\n"
                    "/deletehistory all برای پاک‌سازی کل هیستوری\n"
                    "/clear برای حذف پیام‌های همین چت داخل بله\n"
                    "/models برای انتخاب مدل\n"
                    "/reasoning برای thinking\n"
                    "/help برای راهنما"
                )
                save_states()
                continue

            if cmd == "/help":
                mid = send_message(chat_id, help_text())
                append_assistant_message_id(state, mid)
                save_states()
                continue

            if cmd in ("/end", "/exit"):
                archive_current_session(state, reason="exit")
                state["active"] = False
                mid = send_message(
                    chat_id,
                    "⛔ گفتگو متوقف شد و به هیستوری رفت.\n"
                    "برای حذف همه هیستوری: /deletehistory all"
                )
                append_assistant_message_id(state, mid)
                save_states()
                continue

            if cmd in ("/new", "/newchat"):
                archive_current_session(state, reason="new_chat")
                create_new_session(state)
                send_message(
                    chat_id,
                    "✅ چت جدید ساخته شد.\n"
                    "برای ادامه از گفت‌وگوی قبل: /Continuechat 1\n"
                    "برای دیدن لیست: /recentchats"
                )
                append_assistant_message_id(state, mid)
                save_states()
                continue

            if cmd == "/clear":
                ids_to_clear = clear_current_chat_history(state)
                deleted = delete_messages_in_chat(chat_id, ids_to_clear)
                mid = send_message(
                    chat_id,
                    f"🧹 عملیات پاک‌سازی انجام شد.\n"
                    f"🗑️ {len(ids_to_clear)} پیام حذف‌شده در این چت\n"
                    f"🧾 حذف موفق: {deleted}\n"
                    "برای شروع مجدد: /newchat\n"
                    "برای هیستوری: /recentchats"
                )
                append_assistant_message_id(state, mid)
                save_states()
                continue

            if cmd == "/recentchats":
                mid = send_message(
                    chat_id,
                    "📌 هیستوری چت‌ها:\n"
                    f"{list_recent_chats_text(state)}\n\n"
                    "برای ادامه: /Continuechat <index>\n"
                    "برای حذف: /deletehistory <all|index>"
                )
                append_assistant_message_id(state, mid)
                save_states()
                continue

            if cmd == "/continuechat":
                if arg.strip().isdigit():
                    idx = int(arg.strip())
                    if set_active_from_history(state, idx):
                        mid = send_message(
                            chat_id,
                            f"✅ چت هیستوری {idx} انتخاب شد.\n"
                            "حالا پیام جدید بفرست تا ادامه شود."
                        )
                        append_assistant_message_id(state, mid)
                    else:
                        mid = send_message(
                            chat_id,
                            "شماره نامعتبر است. برای دیدن لیست: /recentchats"
                        )
                        append_assistant_message_id(state, mid)
                else:
                    mid = send_message(
                        chat_id,
                        "برای ادامه باید index بفرستی. مثال: /Continuechat 2"
                    )
                    append_assistant_message_id(state, mid)
                save_states()
                continue

            if cmd == "/deletehistory":
                mid = send_message(
                    chat_id,
                    f"{delete_recent_chats(state, arg)}\n"
                    "برای دیدن لیست جدید: /recentchats\n"
                    "برای مدیریت مدل: /models\n"
                    "برای تنظیم سختی: /reasoning"
                )
                append_assistant_message_id(state, mid)
                save_states()
                continue

            if cmd == "/models":
                if arg.strip().lower() == "all":
                    all_models = get_models("all")
                    mid = send_message(
                        chat_id,
                        "📡 لیست کلی مدل‌ها:\n"
                        f"{format_model_list(all_models, state)}\n"
                        "انتخاب: /models 3 یا /models openai/gpt-5.5"
                    )
                elif arg:
                    mid = send_message(chat_id, set_model(state, arg))
                else:
                    openai_models = get_models("openai")
                    mid = send_message(
                        chat_id,
                        "📡 مدل‌های OpenAI:\n"
                        f"{format_model_list(openai_models, state)}\n"
                        "برای انتخاب مدل: /models 3 یا /models openai/gpt-5.5"
                    )
                append_assistant_message_id(state, mid)
                save_states()
                continue

            if cmd in ("/reasoning", "/thinking"):
                mid = send_message(
                    chat_id,
                    set_thinking(state, arg) + "\n"
                    "برای راهنما: light | medium | extra | high | max | off | minimal"
                )
                append_assistant_message_id(state, mid)
                save_states()
                continue

            if cmd == "/remainingusage":
                mid = send_message(
                    chat_id,
                    f"🔋 مانده توکن:\n{get_remaining_usage()}\n"
                    "در هر لحظه برای چک: /remainingusage\n"
                    "توضیح: openclaw status --usage --json"
                )
                append_assistant_message_id(state, mid)
                save_states()
                continue

            if cmd == "/model":
                mid = send_message(
                    chat_id,
                    f"🧭 مدل فعلی: {state.get('model')}\n"
                    "برای انتخاب مدل جدید: /models 3 یا /models openai/gpt-5.5"
                )
                append_assistant_message_id(state, mid)
                save_states()
                continue

            if not state.get("active"):
                mid = send_message(chat_id, "برای شروع اول /start را بزنید.\n برای راهنمایی /help را بزنید")
                append_assistant_message_id(state, mid)
                save_states()
                continue

            if not state.get("current_session"):
                create_new_session(state)

            state["current_session"]["messages"].append({"role": "user", "text": text})
            session_key = build_session_key(state)
            answer = ask_openclaw(
                text,
                session_key,
                state.get("model"),
                state.get("thinking", "low")
            )
            state["current_session"]["messages"].append({"role": "assistant", "text": answer})
            mid = send_message(chat_id, answer)
            append_assistant_message_id(state, mid)
            save_states()

            continue

        time.sleep(0.2)


if __name__ == "__main__":
    main()
