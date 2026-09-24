import telebot
import sqlite3
import threading
import time
import requests
from datetime import datetime

# ================= CẤU HÌNH ĐÃ TÍCH HỢP =================
BOT_TOKEN = '8980258440:AAH7rUh3P5bq96hrVO112ACzqpuTJ4CBd-g'
ADMIN_ID = 7793220145
YOUTUBE_API_KEY = 'AIzaSyCj9XYGc7MNlMJAeBhTkc7Q8Vl7A6h5G8k'

bot = telebot.TeleBot(BOT_TOKEN)

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
                time_added TEXT
            )
        ''')
        conn.commit()
        conn.close()

init_db()

# ================= CHECK YOUTUBE API V3 =================
def check_ytb_status(url):
    """
    Check trạng thái kênh bằng YouTube Data API v3.
    """
    try:
        channel_id = None
        handle = None
        
        # 1. Bóc tách link để lấy Channel ID hoặc Handle (@)
        if '/channel/' in url:
            channel_id = url.split('/channel/')[1].split('/')[0].split('?')[0]
        elif '/@' in url:
            handle = url.split('/@')[1].split('/')[0].split('?')[0]
        else:
            handle = url.split('/')[-1].split('?')[0]

        # 2. Tạo endpoint API
        base_api_url = f"https://www.googleapis.com/youtube/v3/channels?part=id&key={YOUTUBE_API_KEY}"
        
        if channel_id:
            api_url = f"{base_api_url}&id={channel_id}"
        else:
            if not handle.startswith('@'):
                handle = '@' + handle
            api_url = f"{base_api_url}&forHandle={handle}"

        # 3. Gửi request lấy dữ liệu JSON
        res = requests.get(api_url, timeout=10).json()
        
        # Nếu gặp lỗi API (Hết Quota / Key sai) -> Tạm báo LIVE để tránh báo nhầm DIE
        if 'error' in res:
            print("[CẢNH BÁO API]:", res['error'].get('message'))
            return 'LIVE' 
            
        # Mảng 'items' rỗng đồng nghĩa kênh không tồn tại (đã bị xóa/DIE)
        if not res.get('items'):
            return 'DIE'
            
        return 'LIVE'
    except Exception as e:
        print(f"[LỖI MẠNG]: {e}")
        return 'LIVE'

# ================= FORM THÔNG BÁO =================
def send_channel_info(chat_id, ch_id, link, name_note, price, status, time_added):
    if status == 'LIVE':
        status_text = "🟢 LIVE ✅"
    else:
        status_text = "🔴 DIE ❌"
        
    short_id = link.split('/')[-1][:15] + "..." if len(link.split('/')[-1]) > 15 else link.split('/')[-1]

    text = (
        f"🔸 #{ch_id} 🆔 {short_id}\n"
        f"👤 Tên ytb: {name_note}\n"
        f"📝 Ghi chú: {name_note}\n"
        f"💰 Giá: {price}\n"
        f"📊 Trạng thái: {status_text}\n"
        f"⏱ Thời gian Live: {time_added}\n"
        f"🔎 Check: {link}"
    )
    bot.send_message(chat_id, text, disable_web_page_preview=True)

# ================= LUỒNG THÊM KÊNH (/add) =================
user_data = {}

@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(message.chat.id, "Bot check Live/Die YouTube (API v3) đang hoạt động!\n\nDanh sách lệnh:\n/add - Thêm kênh mới\n/list - Xem danh sách kênh")

@bot.message_handler(commands=['add'])
def add_cmd(message):
    text = (
        "➕ THÊM TÀI NGUYÊN MỚI\n"
        "──────────────────\n"
        "Vui lòng gửi Link youtube \n\n"
        "👇 Hoặc bấm nút bên dưới để quay lại."
    )
    msg = bot.send_message(message.chat.id, text)
    bot.register_next_step_handler(msg, process_link)

def process_link(message):
    if message.text.startswith('/'): return
    
    link = message.text
    user_data[message.chat.id] = {'link': link}
    
    text = (
        f"✅ Đã nhận: {link}\n\n"
        "👤 Vui lòng nhập TÊN kèm GHI CHÚ (Gộp chung 1 dòng):\n"
        "Ví dụ: Nguyễn Văn A kèo của B"
    )
    msg = bot.send_message(message.chat.id, text)
    bot.register_next_step_handler(msg, process_name_note)

def process_name_note(message):
    if message.text.startswith('/'): return
    
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
    if message.text.startswith('/'): return
    
    price = message.text
    data = user_data.get(message.chat.id, {})
    link = data.get('link')
    name_note = data.get('name_note')
    
    time_now = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    status = check_ytb_status(link)
    
    with db_lock:
        conn = sqlite3.connect('youtube_check.db')
        c = conn.cursor()
        c.execute("INSERT INTO channels (link, name_note, price, status, time_added) VALUES (?, ?, ?, ?, ?)",
                  (link, name_note, price, status, time_now))
        channel_id = c.lastrowid
        conn.commit()
        conn.close()
    
    bot.send_message(message.chat.id, "✅ Đã lưu dữ liệu thành công vào hệ thống!")
    
    if message.chat.id in user_data:
        del user_data[message.chat.id]
        
    send_channel_info(message.chat.id, channel_id, link, name_note, price, status, time_now)

# ================= LỆNH XEM DANH SÁCH (/list) =================
@bot.message_handler(commands=['list'])
def list_cmd(message):
    with db_lock:
        conn = sqlite3.connect('youtube_check.db')
        c = conn.cursor()
        c.execute("SELECT id, link, name_note, price, status, time_added FROM channels")
        channels = c.fetchall()
        conn.close()
        
    if not channels:
        bot.send_message(message.chat.id, "Trống! Chưa có kênh nào được thêm.")
        return
        
    bot.send_message(message.chat.id, f"📋 Đang theo dõi {len(channels)} kênh...")
    
    for ch in channels:
        ch_id, link, name_note, price, status, time_added = ch
        send_channel_info(message.chat.id, ch_id, link, name_note, price, status, time_added)
        time.sleep(0.2)

# ================= AUTO CHECK BACKGROUND =================
def auto_checker():
    while True:
        try:
            with db_lock:
                conn = sqlite3.connect('youtube_check.db')
                c = conn.cursor()
                c.execute("SELECT id, link, name_note, price, status, time_added FROM channels WHERE status = 'LIVE'")
                live_channels = c.fetchall()
                conn.close()
                
            for ch in live_channels:
                ch_id, link, name_note, price, old_status, time_added = ch
                
                new_status = check_ytb_status(link)
                
                # Khi phát hiện kênh bị DIE -> Bắn tin nhắn trực tiếp về Telegram Admin ngay
                if new_status == 'DIE':
                    with db_lock:
                        conn = sqlite3.connect('youtube_check.db')
                        c = conn.cursor()
                        c.execute("UPDATE channels SET status = 'DIE' WHERE id = ?", (ch_id,))
                        conn.commit()
                        conn.close()
                        
                    send_channel_info(ADMIN_ID, ch_id, link, name_note, price, new_status, time_added)
                
                time.sleep(0.5)
                
        except Exception as e:
            print(f"Lỗi vòng lặp auto_check: {e}")
            
        time.sleep(300) # Cứ 5 phút kiểm tra lại các kênh LIVE 1 lần

# ================= KHỞI CHẠY =================
if __name__ == '__main__':
    checker_thread = threading.Thread(target=auto_checker, daemon=True)
    checker_thread.start()
    
    print("Bot check YouTube API v3 đang chạy...")
    bot.infinity_polling()
