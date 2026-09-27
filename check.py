import telebot
from telebot import types
import sqlite3
import threading
import time
import requests
from datetime import datetime
import pytz

# ================= CẤU HÌNH =================
BOT_TOKEN = '8980258440:AAH7rUh3P5bq96hrVO112ACzqpuTJ4CBd-g'
ADMIN_ID = 7793220145
YOUTUBE_API_KEY = 'AIzaSyCj9XYGc7MNlMJAeBhTkc7Q8Vl7A6h5G8k'

# Ép múi giờ chuẩn Việt Nam (Asia/Ho_Chi_Minh)
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

bot = telebot.TeleBot(BOT_TOKEN)

# Set Menu 3 gạch góc trái bàn phím Telegram
bot.set_my_commands([
    telebot.types.BotCommand('start', 'Bảng điều khiển & Hiện Menu'),
    telebot.types.BotCommand('add', 'Thêm tài nguyên mới'),
    telebot.types.BotCommand('list', 'Xem danh sách kênh'),
    telebot.types.BotCommand('xoa', 'Xem danh sách & xóa kênh')
])

# ================= TẠO BÀN PHÍM MENU BẤM DƯỚI KHUNG CHAT =================
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_add = types.KeyboardButton('➕ Thêm kênh')
    btn_list = types.KeyboardButton('📋 Danh sách kênh')
    btn_del = types.KeyboardButton('🗑 Xóa kênh')
    
    markup.row(btn_add)
    markup.row(btn_list, btn_del)
    return markup

# ================= DATABASE =================
db_lock = threading.Lock()

def init_db():
    with db_lock:
        conn = sqlite3.connect('youtube_check.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link TEXT,
                name_note TEXT,
                price TEXT,
                status TEXT,
                status_time TEXT
            )
        ''')
        conn.commit()
        conn.close()

init_db()

# ================= HÀM TÍNH THỜI GIAN THỰC =================
def get_vn_now():
    return datetime.now(VN_TZ)

def get_vn_now_str():
    return get_vn_now().strftime("%Y-%m-%d %H:%M:%S")

def calculate_duration(status_time_str):
    try:
        start_time = datetime.strptime(status_time_str, "%Y-%m-%d %H:%M:%S")
        start_time = VN_TZ.localize(start_time)
        now = get_vn_now()
        
        diff = now - start_time
        days = diff.days
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        res = []
        if days > 0:
            res.append(f"{days}d")
        if hours > 0 or days > 0:
            res.append(f"{hours}h")
        res.append(f"{minutes}p")
        
        return " ".join(res)
    except Exception:
        return "0p"

# ================= CHECK YOUTUBE API V3 =================
def check_ytb_status(url):
    try:
        channel_id = None
        handle = None
        
        if '/channel/' in url:
            channel_id = url.split('/channel/')[1].split('/')[0].split('?')[0]
        elif '/@' in url:
            handle = url.split('/@')[1].split('/')[0].split('?')[0]
        else:
            handle = url.split('/')[-1].split('?')[0]

        base_api_url = f"https://www.googleapis.com/youtube/v3/channels?part=id&key={YOUTUBE_API_KEY}"
        
        if channel_id:
            api_url = f"{base_api_url}&id={channel_id}"
        else:
            if not handle.startswith('@'):
                handle = '@' + handle
            api_url = f"{base_api_url}&forHandle={handle}"

        res = requests.get(api_url, timeout=10).json()
        
        if 'error' in res or not res.get('items'):
            return 'DIE' if 'items' in res and not res.get('items') else 'LIVE'
            
        return 'LIVE'
    except Exception:
        return 'LIVE'

# ================= FORM THÔNG BÁO =================
def send_channel_info(chat_id, ch_id, link, name_note, price, status, status_time):
    duration_str = calculate_duration(status_time)
    short_id = link.split('/')[-1].split('?')[0]

    if status == 'LIVE':
        status_text = "🟢 LIVE ✅"
        time_label = f"⏱ Thời gian Live: {duration_str}"
    else:
        status_text = "🔴 DIE ❌"
        time_label = f"⏱ Thời gian Die: {duration_str}"

    text = (
        f"🔸 #{ch_id} 🆔 {short_id}\n"
        f"👤 Tên ytb: {name_note}\n"
        f"📝 Ghi chú: {name_note}\n"
        f"💰 Giá: {price}\n"
        f"📊 Trạng thái: {status_text}\n"
        f"{time_label}\n"
        f"🔎 Check: {link}\n"
        f"-------------------"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"🗑 Xóa kênh #{ch_id}", callback_data=f"del_{ch_id}"))
    
    bot.send_message(chat_id, text, disable_web_page_preview=True, reply_markup=markup)

# ================= LỆNH BẢNG ĐIỀU KHIỂN (/start) =================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    text = (
        "🏠 Bảng điều khiển Bot Check YouTube!\n\n"
        "Sử dụng các nút bấm bên dưới bàn phím để thao tác nhanh:"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu())

# ================= LUỒNG THÊM KÊNH (/add hoặc Nút "➕ Thêm kênh") =================
user_data = {}

@bot.message_handler(commands=['add'])
@bot.message_handler(func=lambda msg: msg.text == '➕ Thêm kênh')
def add_cmd(message):
    text = (
        "➕ THÊM TÀI NGUYÊN MỚI\n"
        "──────────────────\n"
        "Vui lòng gửi Link youtube:"
    )
    msg = bot.send_message(message.chat.id, text)
    bot.register_next_step_handler(msg, process_link)

def process_link(message):
    if message.text in ['➕ Thêm kênh', '📋 Danh sách kênh', '🗑 Xóa kênh'] or message.text.startswith('/'):
        bot.send_message(message.chat.id, "❌ Đã hủy thao tác thêm kênh.", reply_markup=main_menu())
        return
    
    link = message.text.strip()
    user_data[message.chat.id] = {'link': link}
    
    text = (
        f"✅ Đã nhận: {link}\n\n"
        "👤 Vui lòng nhập TÊN kèm GHI CHÚ (Gộp chung 1 dòng):\n"
        "Ví dụ: Nguyễn Văn A kèo của B"
    )
    msg = bot.send_message(message.chat.id, text)
    bot.register_next_step_handler(msg, process_name_note)

def process_name_note(message):
    if message.text in ['➕ Thêm kênh', '📋 Danh sách kênh', '🗑 Xóa kênh'] or message.text.startswith('/'):
        bot.send_message(message.chat.id, "❌ Đã hủy thao tác thêm kênh.", reply_markup=main_menu())
        return
    
    name_note = message.text
    user_data[message.chat.id]['name_note'] = name_note
    
    text = (
        f"👤 Tên & Ghi chú: {name_note}\n\n"
        "💰 Vui lòng nhập GIÁ TIỀN (VNĐ):\n"
        "(Nhập 0 nếu không cần ghi giá)"
    )
    msg = bot.send_message(message.chat.id, text)
    bot.register_next_step_handler(msg, process_price)

def process_price(message):
    if message.text in ['➕ Thêm kênh', '📋 Danh sách kênh', '🗑 Xóa kênh'] or message.text.startswith('/'):
        bot.send_message(message.chat.id, "❌ Đã hủy thao tác thêm kênh.", reply_markup=main_menu())
        return
    
    price = message.text
    data = user_data.get(message.chat.id, {})
    link = data.get('link')
    name_note = data.get('name_note')
    
    now_vn_str = get_vn_now_str()
    status = check_ytb_status(link)
    
    with db_lock:
        conn = sqlite3.connect('youtube_check.db')
        c = conn.cursor()
        c.execute("INSERT INTO channels (link, name_note, price, status, status_time) VALUES (?, ?, ?, ?, ?)",
                  (link, name_note, price, status, now_vn_str))
        channel_id = c.lastrowid
        conn.commit()
        conn.close()
    
    bot.send_message(message.chat.id, "✅ Đã lưu dữ liệu thành công vào hệ thống!", reply_markup=main_menu())
    
    if message.chat.id in user_data:
        del user_data[message.chat.id]
        
    send_channel_info(message.chat.id, channel_id, link, name_note, price, status, now_vn_str)

# ================= TẠO MENU XÓA KÊNH =================
def build_delete_menu():
    with db_lock:
        conn = sqlite3.connect('youtube_check.db')
        c = conn.cursor()
        c.execute("SELECT id, name_note, status FROM channels")
        channels = c.fetchall()
        conn.close()
        
    if not channels:
        return "📭 Danh sách trống! Chưa có kênh nào trong hệ thống.", None
        
    text = "🗑 DANH SÁCH KÊNH HỆ THỐNG\n"
    text += "──────────────────\n"
    
    markup = types.InlineKeyboardMarkup()
    for ch_id, name_note, status in channels:
        icon = "🟢" if status == 'LIVE' else "🔴"
        text += f"{icon} #{ch_id} - {name_note}\n"
        markup.add(types.InlineKeyboardButton(f"❌ Xóa #{ch_id} - {name_note}", callback_data=f"del_{ch_id}"))
        
    text += "\n👇 Bấm vào nút tương ứng bên dưới để xóa:"
    return text, markup

# ================= LỆNH XÓA (/xoa hoặc Nút "🗑 Xóa kênh") =================
@bot.message_handler(commands=['xoa'])
@bot.message_handler(func=lambda msg: msg.text == '🗑 Xóa kênh')
def xoa_cmd(message):
    text, markup = build_delete_menu()
    if markup:
        bot.send_message(message.chat.id, text, reply_markup=markup)
    else:
        bot.send_message(message.chat.id, text, reply_markup=main_menu())

# ================= XỬ LÝ CLICK NÚT XÓA KÊNH =================
@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def handle_delete_callback(call):
    ch_id = int(call.data.split('_')[1])
    
    with db_lock:
        conn = sqlite3.connect('youtube_check.db')
        c = conn.cursor()
        c.execute("DELETE FROM channels WHERE id = ?", (ch_id,))
        conn.commit()
        conn.close()
        
    bot.answer_callback_query(call.id, f"✅ Đã xóa thành công kênh #{ch_id}!")
    
    text, markup = build_delete_menu()
    if markup:
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
    else:
        bot.edit_message_text("✅ Đã xóa toàn bộ kênh! Danh sách hiện đang trống.", chat_id=call.message.chat.id, message_id=call.message.message_id)

# ================= LỆNH XEM DANH SÁCH (/list hoặc Nút "📋 Danh sách kênh") =================
@bot.message_handler(commands=['list'])
@bot.message_handler(func=lambda msg: msg.text == '📋 Danh sách kênh')
def list_cmd(message):
    with db_lock:
        conn = sqlite3.connect('youtube_check.db')
        c = conn.cursor()
        c.execute("SELECT id, link, name_note, price, status, status_time FROM channels")
        channels = c.fetchall()
        conn.close()
        
    if not channels:
        bot.send_message(message.chat.id, "Trống! Chưa có kênh nào được thêm.", reply_markup=main_menu())
        return
        
    bot.send_message(message.chat.id, f"📋 Đang theo dõi {len(channels)} kênh...", reply_markup=main_menu())
    
    for ch in channels:
        ch_id, link, name_note, price, status, status_time = ch
        send_channel_info(message.chat.id, ch_id, link, name_note, price, status, status_time)
        time.sleep(0.2)

# ================= AUTO CHECK BACKGROUND =================
def auto_checker():
    while True:
        try:
            with db_lock:
                conn = sqlite3.connect('youtube_check.db')
                c = conn.cursor()
                c.execute("SELECT id, link, name_note, price, status, status_time FROM channels WHERE status = 'LIVE'")
                live_channels = c.fetchall()
                conn.close()
                
            for ch in live_channels:
                ch_id, link, name_note, price, old_status, status_time = ch
                
                new_status = check_ytb_status(link)
                
                if new_status == 'DIE':
                    now_vn_str = get_vn_now_str()
                    with db_lock:
                        conn = sqlite3.connect('youtube_check.db')
                        c = conn.cursor()
                        c.execute("UPDATE channels SET status = 'DIE', status_time = ? WHERE id = ?", (now_vn_str, ch_id))
                        conn.commit()
                        conn.close()
                        
                    send_channel_info(ADMIN_ID, ch_id, link, name_note, price, new_status, now_vn_str)
                
                time.sleep(0.5)
                
        except Exception as e:
            print(f"Lỗi auto_check: {e}")
            
        time.sleep(300)

# ================= KHỞI CHẠY =================
if __name__ == '__main__':
    checker_thread = threading.Thread(target=auto_checker, daemon=True)
    checker_thread.start()
    
    print("Bot check YouTube (Có Bàn Phím Menu) đang chạy...")
    bot.infinity_polling()
