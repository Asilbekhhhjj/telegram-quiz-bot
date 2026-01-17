import telebot
from telebot import types
from docx import Document
import os
import random
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise SystemExit("TELEGRAM_TOKEN yo‘q")

bot = telebot.TeleBot(TOKEN)

# =========================
# STATE STORAGE
# =========================
users = {}

# =========================
# HELPERS
# =========================
def reset_user(uid):
    users[uid] = {
        "stage": "title",
        "title": "",
        "questions": [],
        "time": 10,
        "shuffle_q": False,
        "shuffle_a": False
    }

# =========================
# START
# =========================
@bot.message_handler(commands=["start"])
def start(msg):
    reset_user(msg.chat.id)
    bot.send_message(
        msg.chat.id,
        "📝 Keling, yangi test tuzamiz.\n"
        "Iltimos, test sarlavhasini yuboring."
    )

# =========================
# TEXT HANDLER (STATE BASED)
# =========================
@bot.message_handler(content_types=["text"])
def text_handler(msg):
    u = users.get(msg.chat.id)
    if not u:
        return

    # 1️⃣ TITLE
    if u["stage"] == "title":
        u["title"] = msg.text
        u["stage"] = "method"

        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("📝 Qo‘lda kiritish", "📄 Word fayl yuborish")

        bot.send_message(
            msg.chat.id,
            "Test qanday kiritiladi?",
            reply_markup=kb
        )

    # 3️⃣ MANUAL QUESTION
    elif u["stage"] == "manual_question":
        u["current_q"] = msg.text
        u["current_opts"] = []
        u["stage"] = "manual_opts"
        bot.send_message(msg.chat.id, "Variantlarni yuboring (A;B;C;D):")

    elif u["stage"] == "manual_opts":
        opts = msg.text.split(";")
        if len(opts) < 2:
            bot.send_message(msg.chat.id, "Kamida 2 ta variant kerak.")
            return
        u["current_opts"] = opts
        u["stage"] = "manual_correct"
        bot.send_message(msg.chat.id, "To‘g‘ri javob raqamini yuboring (1-4):")

    elif u["stage"] == "manual_correct":
        idx = int(msg.text) - 1
        q = {
            "q": u["current_q"],
            "opts": u["current_opts"],
            "ans": idx
        }
        u["questions"].append(q)

        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("➕ Yana savol", "▶️ Davom etish")
        u["stage"] = "after_manual"

        bot.send_message(msg.chat.id, "Savol qo‘shildi", reply_markup=kb)

# =========================
# BUTTON HANDLER
# =========================
@bot.message_handler(func=lambda m: True)
def buttons(msg):
    u = users.get(msg.chat.id)
    if not u:
        return

    # 2️⃣ METHOD
    if msg.text == "📄 Word fayl yuborish":
        u["stage"] = "word"
        bot.send_message(msg.chat.id, "Word (.docx) fayl yuboring")
        return

    if msg.text == "📝 Qo‘lda kiritish":
        u["stage"] = "manual_question"
        bot.send_message(msg.chat.id, "Savolni yuboring:")
        return

    if msg.text == "➕ Yana savol":
        u["stage"] = "manual_question"
        bot.send_message(msg.chat.id, "Keyingi savolni yuboring:")
        return

    if msg.text == "▶️ Davom etish":
        ask_time(msg.chat.id)
        return

# =========================
# WORD UPLOAD
# =========================
@bot.message_handler(content_types=["document"])
def load_word(msg):
    u = users.get(msg.chat.id)
    if not u or u["stage"] != "word":
        return

    file_info = bot.get_file(msg.document.file_id)
    data = bot.download_file(file_info.file_path)

    fname = "temp.docx"
    with open(fname, "wb") as f:
        f.write(data)

    doc = Document(fname)
    os.remove(fname)

    q = None
    for p in doc.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        if t[0].isdigit():
            if q:
                u["questions"].append(q)
            q = {"q": t, "opts": [], "ans": 0}
        elif t.startswith(("A)", "B)", "C)", "D)")):
            if "*" in t:
                q["ans"] = len(q["opts"])
                t = t.replace("*", "")
            q["opts"].append(t[3:])
    if q:
        u["questions"].append(q)

    ask_time(msg.chat.id)

# =========================
# TIME
# =========================
def ask_time(chat_id):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("10", "15", "30", "60")
    users[chat_id]["stage"] = "time"
    bot.send_message(chat_id, "Har savol uchun vaqt (soniya):", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text.isdigit())
def set_time(msg):
    u = users.get(msg.chat.id)
    if not u or u["stage"] != "time":
        return

    u["time"] = int(msg.text)
    ask_shuffle(msg.chat.id)

# =========================
# SHUFFLE
# =========================
def ask_shuffle(chat_id):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔀 Barchasi", "❓ Faqat savollar", "🅰️ Faqat javoblar", "🚫 Aralashtirmaslik")
    users[chat_id]["stage"] = "shuffle"
    bot.send_message(chat_id, "Aralashtirish:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text.startswith(("🔀", "❓", "🅰️", "🚫")))
def set_shuffle(msg):
    u = users.get(msg.chat.id)
    if not u:
        return

    if "Barchasi" in msg.text:
        u["shuffle_q"] = u["shuffle_a"] = True
    elif "Faqat savollar" in msg.text:
        u["shuffle_q"] = True
    elif "Faqat javoblar" in msg.text:
        u["shuffle_a"] = True

    launch_quiz(msg.chat.id)

# =========================
# QUIZ
# =========================
def launch_quiz(chat_id):
    u = users[chat_id]

    qs = u["questions"].copy()
    if u["shuffle_q"]:
        random.shuffle(qs)

    for q in qs:
        opts = q["opts"].copy()
        correct = q["ans"]

        if u["shuffle_a"]:
            combined = list(enumerate(opts))
            random.shuffle(combined)
            opts = [o for _, o in combined]
            correct = [i for i, (idx, _) in enumerate(combined) if idx == q["ans"]][0]

        bot.send_poll(
            chat_id,
            question=q["q"],
            options=opts,
            type="quiz",
            correct_option_id=correct,
            open_period=u["time"],
            is_anonymous=False
        )

    bot.send_message(chat_id, "🏁 Test yakunlandi")

# =========================
bot.polling()
