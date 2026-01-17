import telebot
from telebot import types
import sqlite3
import os
from PyPDF2 import PdfReader

TOKEN = "8492824131:AAGnhTLsUbIfgxF9HpfB-zMxWQALLoKZ20Y"
bot = telebot.TeleBot(TOKEN)

# ================= DATABASE =================
db = sqlite3.connect("quiz.db", check_same_thread=False)
sql = db.cursor()

sql.executescript("""
CREATE TABLE IF NOT EXISTS tests(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 title TEXT,
 owner INTEGER
);

CREATE TABLE IF NOT EXISTS questions(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 test_id INTEGER,
 text TEXT,
 correct INTEGER
);

CREATE TABLE IF NOT EXISTS options(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 question_id INTEGER,
 text TEXT
);

CREATE TABLE IF NOT EXISTS results(
 user INTEGER,
 username TEXT,
 test INTEGER,
 score INTEGER,
 total INTEGER
);
""")
db.commit()

users = {}

# ================= START =================
@bot.message_handler(commands=["start"])
def start(msg):
    args = msg.text.split()

    # link orqali test
    if len(args) > 1 and args[1].startswith("test_"):
        start_test(msg.chat.id, msg.from_user, int(args[1].split("_")[1]))
        return

    users[msg.chat.id] = {"stage": "title"}
    bot.send_message(
        msg.chat.id,
        "📝 Test nomini yuboring:\n"
        "❗ Keyingi bosqichda PDF yuklaysiz"
    )

# ================= TEXT =================
@bot.message_handler(content_types=["text"])
def text_handler(msg):
    uid = msg.chat.id
    if uid not in users:
        return

    u = users[uid]

    if u["stage"] == "title":
        sql.execute("INSERT INTO tests(title,owner) VALUES(?,?)", (msg.text, uid))
        db.commit()
        u["test_id"] = sql.lastrowid
        u["stage"] = "pdf"

        bot.send_message(
            uid,
            "📄 Endi PDF faylni yuboring\n"
            "❗ Har savolda A–D va bitta * bo‘lishi shart"
        )

# ================= PDF LOADER =================
@bot.message_handler(content_types=["document"])
def load_pdf(msg):
    uid = msg.chat.id
    if uid not in users or users[uid]["stage"] != "pdf":
        return

    file = bot.get_file(msg.document.file_id)
    data = bot.download_file(file.file_path)

    with open("temp.pdf", "wb") as f:
        f.write(data)

    reader = PdfReader("temp.pdf")
    os.remove("temp.pdf")

    full_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"

    lines = [l.strip() for l in full_text.splitlines() if l.strip()]

    test_id = users[uid]["test_id"]
    saved = 0

    q_text = None
    opts = []
    correct = None

    for t in lines:
        # SAVOL
        if t[0].isdigit():
            q_text = t
            opts = []
            correct = None

        # VARIANTLAR
        elif t[:2] in ("A)", "B)", "C)", "D)"):
            if "*" in t:
                correct = len(opts)
                t = t.replace("*", "")
            opts.append(t[3:].strip())

        # SAQLASH SHARTI
        if q_text and correct is not None and len(opts) >= 4:
            sql.execute(
                "INSERT INTO questions(test_id,text,correct) VALUES(?,?,?)",
                (test_id, q_text, correct)
            )
            qid = sql.lastrowid

            for o in opts[:4]:
                sql.execute(
                    "INSERT INTO options(question_id,text) VALUES(?,?)",
                    (qid, o)
                )

            db.commit()
            saved += 1
            q_text = None

    link = f"https://t.me/{bot.get_me().username}?start=test_{test_id}"

    bot.send_message(
        uid,
        f"✅ PDF yuklandi\n"
        f"📌 Saqlangan savollar: {saved}\n"
        f"🔗 Test link:\n{link}"
    )

    del users[uid]

# ================= START TEST =================
def start_test(uid, user, tid):
    sql.execute("SELECT title FROM tests WHERE id=?", (tid,))
    t = sql.fetchone()
    if not t:
        bot.send_message(uid, "❌ Test topilmadi")
        return

    users[uid] = {
        "test": tid,
        "index": 0,
        "score": 0,
        "username": user.username or user.first_name
    }

    bot.send_message(uid, f"🧠 Test: {t[0]}")
    send_question(uid)

def send_question(uid):
    u = users[uid]

    sql.execute(
        "SELECT id,text,correct FROM questions WHERE test_id=? LIMIT 1 OFFSET ?",
        (u["test"], u["index"])
    )
    q = sql.fetchone()

    if not q:
        finish(uid)
        return

    qid, text, correct = q
    sql.execute("SELECT text FROM options WHERE question_id=?", (qid,))
    opts = [o[0] for o in sql.fetchall()]

    # HIMOYA
    if len(opts) < 4:
        u["index"] += 1
        send_question(uid)
        return

    bot.send_poll(
        uid,
        text,
        opts[:4],
        type="quiz",
        correct_option_id=correct,
        is_anonymous=False
    )

    u["index"] += 1

# ================= SCORE =================
@bot.poll_answer_handler()
def handle_poll_answer(poll):
    uid = poll.user.id
    if uid not in users:
        return

    u = users[uid]

    poll_id = poll.poll_id
    chosen = poll.option_ids[0]

    correct = u.get("polls", {}).get(poll_id)

    if correct is None:
        return

    if chosen == correct:
        u["score"] += 1

# ================= FINISH =================
def finish(uid):
    u = users[uid]

    sql.execute(
        "INSERT INTO results VALUES(?,?,?,?,?)",
        (uid, u["username"], u["test"], u["score"], u["index"])
    )
    db.commit()

    percent = int(u["score"] / u["index"] * 100)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📊 Reyting jadvali", callback_data=f"rating_{u['test']}"))

    bot.send_message(
        uid,
        f"🏁 NATIJA\n\n"
        f"🎯 Ball: {u['score']}/{u['index']}\n"
        f"📊 Foiz: {percent}%\n"
        f"🏆 Baho: {'A' if percent>=80 else 'B' if percent>=60 else 'C'}",
        reply_markup=kb
    )

    del users[uid]

# ================= LEADERBOARD =================
@bot.callback_query_handler(func=lambda c: c.data.startswith("rating_"))
def rating(call):
    tid = int(call.data.split("_")[1])

    sql.execute("""
        SELECT username, score, total,
               CAST(score * 100 / total AS INT) AS percent
        FROM results
        WHERE test=?
        ORDER BY percent DESC, score DESC
        LIMIT 10
    """, (tid,))
    rows = sql.fetchall()

    if not rows:
        bot.send_message(call.message.chat.id, "📊 Reyting hali yo‘q")
        return

    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 REYTING JADVALI (TOP 10)\n\n"

    for i, r in enumerate(rows):
        medal = medals[i] if i < 3 else f"{i+1}."
        name, score, total, percent = r
        text += f"{medal} 🧑‍🎓 {name}\n   🎯 {score}/{total} | 📊 {percent}%\n\n"

    bot.send_message(call.message.chat.id, text)

# ================= RUN =================
bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)

