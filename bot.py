import os, json, logging, gspread, threading, asyncio
from oauth2client.service_account import ServiceAccountCredentials
from github import Github
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from flask import Flask

# --- 1. CẤU HÌNH ---
TOKEN = os.getenv('BOT_TOKEN')
SHEET_ID = os.getenv('SHEET_ID')
GH_TOKEN = os.getenv('GH_TOKEN')
ADMIN_ID = 7346983056
REPO_NAME = "NgDanhThanhTrung/locket_"
PORT = int(os.environ.get("PORT", 8000))

CONTACT_URL = "https://t.me/NgDanhThanhTrung"
DONATE_URL = "https://ngdanhthanhtrung.github.io/Bank/"
WEB_URL = "https://ngdanhthanhtrung.github.io/Modules-NDTT-Premium/"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 2. TEMPLATES ---
JS_TEMPLATE = """// ========= ID ========= //
const mapping = {{ 'Locket': ['Gold'] }};
var ua=$request.headers["User-Agent"]||$request.headers["user-agent"],obj=JSON.parse($response.body);
obj.Attention="Chúc mừng bạn! Vui lòng không bán hoặc chia sẻ cho người khác!";
var {user}={{ is_sandbox:!1, ownership_type:"PURCHASED", billing_issues_detected_at:null, period_type:"normal", expires_date:"2999-12-18T01:04:17Z", grace_period_expires_date:null, unsubscribe_detected_at:null, original_purchase_date:\"{date}T01:04:18Z\", purchase_date:\"{date}T01:04:17Z\", store:\"app_store\" }};
var {user}_sub={{ grace_period_expires_date:null, purchase_date:\"{date}T01:04:17Z\", product_identifier:\"com.{user}.premium.yearly\", expires_date:\"2999-12-18T01:04:17Z\" }};
const match=Object.keys(mapping).find(e=>ua.includes(e));
if(match){{ let[e,s]=mapping[match]; s?({user}_sub.product_identifier=s,obj.subscriber.subscriptions[s]={user}):obj.subscriber.subscriptions[\"com.{user}.premium.yearly\"]={user},obj.subscriber.entitlements[e]={user}_sub }}else{{ obj.subscriber.subscriptions[\"com.{user}.premium.yearly\"]={user}; obj.subscriber.entitlements.pro={user}_sub }}
$done({{body:JSON.stringify(obj)}});"""

MODULE_TEMPLATE = """#!name=Locket-Gold ({user})
#!desc=Crack By NgDanhThanhTrung
[Script]
revenuecat = type=http-response, pattern=^https:\\/\\/api\\.revenuecat\\.com\\/.+\\/(receipts$|subscribers\\/[^/]+$), script-path={js_url}, requires-body=true, max-size=-1, timeout=60
deleteHeader = type=http-request, pattern=^https:\\/\\/api\\.revenuecat\\.com\\/.+\\/(receipts|subscribers), script-path=https://raw.githubusercontent.com/NgDanhThanhTrung/locket_/main/Locket_NDTT/deleteHeader.js, timeout=60
[MITM]
hostname = %APPEND% api.revenuecat.com"""

# --- 3. HÀM HỖ TRỢ ---
def get_sheets():
    try:
        creds_json = os.getenv('GOOGLE_CREDS')
        if not creds_json: return None, None
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(creds_json), scope)
        client = gspread.authorize(creds)
        ss = client.open_by_key(SHEET_ID)
        return ss.worksheet("modules"), ss.worksheet("users")
    except Exception as e:
        logging.error(f"Lỗi Google Sheets: {e}")
        return None, None

def get_combined_kb(include_list=False):
    kb = []
    if include_list:
        kb.append([InlineKeyboardButton("📂 Danh sách Module", callback_data="show_list")])
    kb.append([InlineKeyboardButton("💬 Liên hệ", url=CONTACT_URL), InlineKeyboardButton("☕ Donate", url=DONATE_URL)])
    kb.append([InlineKeyboardButton("✨ Web Hướng Dẫn", url=WEB_URL)])
    return InlineKeyboardMarkup(kb)

async def auto_reg(u: Update):
    user = u.effective_user
    if not user: return
    _, s_u = get_sheets()
    if not s_u: return
    try:
        user_ids = s_u.col_values(1)
        if str(user.id) not in user_ids:
            s_u.append_row([str(user.id), user.full_name, f"@{user.username}" if user.username else "N/A"])
    except Exception as e:
        logging.error(f"Lỗi đăng ký user: {e}")

# --- 4. LỆNH BOT ---
async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await auto_reg(u)
    txt = f"👋 Chào <b>{u.effective_user.first_name}</b>!\n\nBot hỗ trợ tạo Module Locket cá nhân hóa và cung cấp Script Premium."
    await u.message.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=get_combined_kb(include_list=True))

async def hdsd(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await auto_reg(u)
    user_id = u.effective_user.id
    txt = (
        "📖 <b>HƯỚNG DẪN SỬ DỤNG:</b>\n\n"
        "🔹 <b>MODULE CÓ SẴN:</b>\n"
        "Gõ /list để xem danh sách. Sau đó gõ <code>/[tên_module]</code> để lấy link.\n\n"
        "🔹 <b>TẠO MODULE LOCKET RIÊNG:</b>\n"
        "Cú pháp: <code>/get tên_user | yyyy-mm-dd</code>\n"
        "<i>Ví dụ: /get ndtt | 2025-01-16</i>\n"
        "• Tên user: viết liền không dấu.\n"
        "• Ngày: Năm-Tháng-Ngày (ngày đăng ký hiển thị)."
    )
    if user_id == ADMIN_ID:
        txt += "\n\n⚡ <b>ADMIN TOOLS:</b> /broadcast, /setlink"
    
    await u.message.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=get_combined_kb())

async def send_module_list(u: Update, c: ContextTypes.DEFAULT_TYPE):
    s_m, _ = get_sheets()
    if not s_m:
        return await u.effective_message.reply_text("❌ Không thể kết nối dữ liệu Module.")
    
    records = s_m.get_all_records()
    if not records:
        return await u.effective_message.reply_text("📂 Hiện tại chưa có module nào trong danh sách.")

    m_list = "<b>📂 DANH SÁCH MODULE HỆ THỐNG:</b>\n\n"
    for r in records:
        m_list += f"🔹 <code>/{r['key']}</code> - {r['title']}\n"
    
    target = u.message if u.message else u.callback_query.message
    await target.reply_text(m_list, parse_mode=ParseMode.HTML)

async def get_bundle(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await auto_reg(u)
    if not c.args or "|" not in " ".join(c.args):
        return await u.message.reply_text("⚠️ Sai cú pháp! /get user | yyyy-mm-dd")
    
    try:
        raw_text = " ".join(c.args)
        user, date = [p.strip() for p in raw_text.split("|")]
        status_msg = await u.message.reply_text("⏳ Đang khởi tạo script trên GitHub...")
        
        gh = Github(GH_TOKEN)
        repo = gh.get_repo(REPO_NAME)
        
        js_path = f"{user}/Locket_Gold.js"
        mod_path = f"{user}/Locket_{user}.sgmodule"
        js_url = f"https://raw.githubusercontent.com/{REPO_NAME}/main/{js_path}"

        files = [
            (js_path, JS_TEMPLATE.format(user=user, date=date)),
            (mod_path, MODULE_TEMPLATE.format(user=user, js_url=js_url))
        ]

        for path, content in files:
            try:
                f = repo.get_contents(path, ref="main")
                repo.update_file(path, f"Update {user}", content, f.sha, branch="main")
            except:
                repo.create_file(path, f"Create {user}", content, branch="main")

        await status_msg.edit_text(
            f"✅ <b>Thành công!</b>\n\nLink Module của bạn:\n<code>https://raw.githubusercontent.com/{REPO_NAME}/main/{mod_path}</code>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await u.message.reply_text(f"❌ Lỗi GitHub: {e}")

async def handle_callback(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    if u.callback_query.data == "show_list":
        await send_module_list(u, c)

async def handle_msg(u: Update, c: ContextTypes.DEFAULT_TYPE):
    text = u.message.text
    if not text or not text.startswith('/'): return
    
    cmd = text.replace("/", "").lower().split('@')[0]
    if cmd in ["start", "hdsd", "get", "list"]: return

    s_m, _ = get_sheets()
    if not s_m: return
    
    db = {str(r['key']).lower(): r for r in s_m.get_all_records()}
    if cmd in db:
        item = db[cmd]
        guide = f"✨ <b>HƯỚNG DẪN: {item['title']}</b>\n\nLink Module:\n<code>{item['url']}</code>"
        await u.message.reply_text(guide, parse_mode=ParseMode.HTML, reply_markup=get_combined_kb())

# --- 5. KHỞI CHẠY ---
server = Flask(__name__)
@server.route('/')
def ping(): return "Bot is Live!", 200

async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Khởi động"),
        BotCommand("list", "Danh sách Module"),
        BotCommand("hdsd", "Hướng dẫn sử dụng")
    ])

if __name__ == "__main__":
    threading.Thread(target=lambda: server.run(host="0.0.0.0", port=PORT), daemon=True).start()
    
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hdsd", hdsd))
    app.add_handler(CommandHandler("list", send_module_list))
    app.add_handler(CommandHandler("get", get_bundle))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.COMMAND, handle_msg))
    
    print("Bot đang chạy...")
    app.run_polling(drop_pending_updates=True)
