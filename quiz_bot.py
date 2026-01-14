import telebot
from telebot import types
from docx import Document
import os

TOKEN = os.getenv("8492824131:AAGnhTLsUbIfgxF9HpfB-zMxWQALLoKZ20Y")  # 🔐 token yashirin
bot = telebot.TeleBot(TOKEN)

users = {}

def parse_docx(file_name):
    doc = Document(file_name)
    questions = []
    q = {}

    for p in doc.paragraphs:
        t = p.text.strip()
        if not t:
            continue

        if t[0].isdigit() and "." in t:
            if q:
                questions.append(q)
            q = {"q": t, "opts": {}, "ans": ""}
        elif t.startswith(("A)", "B)", "C)", "D)")):
            key = t[0]
            if "*" in t:
                q["ans"] = key
                t = t.replace("*", "")
            q["opts"][key] = t[3:].strip()

    if q:
        questions.append(q)
    return questions

@bot.message_handler(commands=['start'])
def start(msg):
    bot.send_message(
        msg.chat.id,
        "👋 Salom!\n📄 Word test tashla — men QUIZ qilib beraman."
    )

@bot.message_handler(content_types=['document'])
def load_test(msg):
    if not msg.document.file_name.endswith(".docx"):
        bot.send_message(msg.chat.id, "❌ Faqat Word (.docx) fayl.")
        return

    file_info = bot.get_file(msg.document.file_id)
    data = bot.download_file(file_info.file_path)

    fname = msg.document.file_name
    with open(fname, "wb") as f:
        f.write(data)

    questions = parse_docx(fname)
    os.remove(fname)

    if not questions:
        bot.send_message(msg.chat.id, "❌ Test topilmadi.")
        return

    users[msg.chat.id] = {
        "questions": questions,
        "i": 0,
        "correct": 0
    }

    send_question(msg.chat.id)

def send_question(chat_id):
    u = users[chat_id]
    q = u["questions"][u["i"]]

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for k in q["opts"]:
        kb.add(k)

    text = q["q"] + "\n\n"
    for k, v in q["opts"].items():
        text += f"{k}) {v}\n"

    bot.send_message(chat_id, text, reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["A", "B", "C", "D"])
def answer(msg):
    u = users.get(msg.chat.id)
    if not u:
        return

    q = u["questions"][u["i"]]
    if msg.text == q["ans"]:
        u["correct"] += 1

    u["i"] += 1

    if u["i"] >= len(u["questions"]):
        total = len(u["questions"])
        percent = round((u["correct"] / total) * 100)
        bot.send_message(
            msg.chat.id,
            f"🏁 Test tugadi!\n\n"
            f"📊 Savollar: {total}\n"
            f"✔ To‘g‘ri: {u['correct']}\n"
            f"📈 Natija: {percent}%",
            reply_markup=types.ReplyKeyboardRemove()
        )
        users.pop(msg.chat.id)
    else:
        send_question(msg.chat.id)

bot.polling()
