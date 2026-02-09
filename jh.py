import random   #用來隨機挑一種食物
import os   #用來存取系統環境變數（這裡是讀取 BOT_TOKEN）
import sqlite3  #存取購物車資料
import requests
import difflib
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, InputMediaPhoto
from telegram.ext import MessageHandler, filters, ApplicationBuilder, CommandHandler, ConversationHandler, CallbackQueryHandler, ContextTypes, Application
from info import menu_data, fuzzy_map, eat_what, sticker_list, TAROT_CARDS

SHOP_NAME, SHOP_PRICE, SHOP_URL = range(3)  #購物車狀態定義
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
user_state = {}
menu_path = r"C:\Users\admin\Desktop\self_learning_app\store_menu"
introduced_users = set()    #記錄哪些使用者已經「啟動過」機器人、看過自我介紹

def init_db(): #初始化
    conn = sqlite3.connect("shopcart.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            user_id INTEGER,
            shop_name TEXT,
            shop_price TEXT,
            shop_url TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_item_db(user_id, item): # 新增商品到DB
    conn = sqlite3.connect("shopcart.db")
    c = conn.cursor()
    c.execute("INSERT INTO cart (user_id, shop_name, shop_price, shop_url) VALUES (?, ?, ?, ?)",
              (user_id, item["shop_name"], item["shop_price"], item["shop_url"]))
    conn.commit()
    conn.close()

def get_cart_db(user_id):   # 查詢購物車
    conn = sqlite3.connect("shopcart.db")
    c = conn.cursor()
    c.execute("SELECT shop_name, shop_price, shop_url FROM cart WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def remove_item_db(user_id, name):  # 刪除商品
    conn = sqlite3.connect("shopcart.db")
    c = conn.cursor()
    c.execute("DELETE FROM cart WHERE user_id=? AND shop_name=?", (user_id, name))
    conn.commit()
    conn.close()

#async def 代表這是一個「非同步函式」能同時被多個人呼叫 而不會阻塞整個程式
async def shopcart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cart = get_cart_db(user_id)
    if not cart:
        await update.message.reply_text(
            "目前購物車是空的\n\n"

            "使用 /addcart 來新增商品\n"
            "或使用 /cancel 取消操作")
    else:
        text_lines = []
        for name, price, url in cart:
            text_lines.append(f"{name}")
            text_lines.append(f"- 價格： {price if price else '未提供'}")
            text_lines.append(f"- 網址： {url if url else '未提供'}")
            text_lines.append("")
        text_output = "\n".join(text_lines)
        await update.message.reply_text("目前購物車的東西有：\n\n"
                                         + text_output +
                                        "\n\n使用 /addcart 來新增商品\n"
                                        "或使用 /removecart 移除購物車的商品\n"
                                        "或使用 /commandlist 檢視所有可用指令")

async def menusearch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_state[user_id] = "waiting_store"
    await update.message.reply_text(
        "餓了還是渴了? 要找哪間店的菜單?\n\n"

        "使用 /cancel 取消操作")

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
            "<b><u>關於與更新內容</u></b>: \n\n"
            
            "版本: jh 3.0 Pro\n"
            "開發者: <a href='https://t.me/hsarya'>小龜</a>\n"
            "貼圖來源: @moe_sticker_bot\n"
            "天氣資訊來源: <a href='https://openweathermap.org'>OpenWeatherMap</a>\n\n"

            "本次更新\n"
            "<b>首次大版本更新</b>\n\n"

            "<b><u>查詢菜單</u></b>\n"  #Beta4
            "- 輸入飲料店名直接傳菜單\n\n"
            
            "<b><u>查詢天氣</u></b>\n"    #Beta4
            "- 直接說地點找天氣, 但是目前只支援輸入英文\n\n"

            "<b><u>更改輸入方式</u></b>\n" #Beta2
            "- 移除按鈕的輸入方法以及清除的功能\n"
            "- 現在改用輸入指令的方式, 指令更多樣化, 在視覺上也更清楚\n\n"

            "<b><u>支援文字、貼圖輸入</u></b>\n"  #Beta1
            "- 現在可輸入文字或貼圖回覆, 而不再只是按按鈕\n\n"

            "<b><u>更新食物清單</u></b>\n\n"  #Beta2

            "<b><u>語言選擇</u></b>\n"  #Beta3
            "- 新增3種新的語言, 但不保證可以用\n\n"

            "使用 /commandlist 檢視所有可用指令"
            , parse_mode= "HTML")  #這行很重要 告訴Telegram解析HTML標籤(文字粗體跟底線) 

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_state.pop(user_id, None)
    await update.message.reply_text("OK, 已取消操作\n"
                                    "使用 /commandlist 檢視所有可用指令\n"
                                    "或使用 /help 查看常見問題")

async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_state[user_id] = "waiting_for_location"
    await update.message.reply_text(
        "你想查哪個地方的天氣?\n\n"

        "<b>請使用英文輸入</b>\n"
        "例如: Taipei\n\n"
        "使用 /cancel 取消操作",
        parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    if user_state.get(user_id) == "waiting_for_location":   #查天氣
        location = text
        params = {"q": location, "appid": WEATHER_API_KEY, "units": "metric", "lang": "zh_tw"}
        try:
            res = requests.get(BASE_URL, params=params)
            data = res.json()
            if str(data.get("cod")) != "200":
                await update.message.reply_text("查不到這個地點的天氣, 換個地方查詢試試看\n\n"
                                                
                                                "使用 /cancel 取消操作")
            else:
                name = data["name"]
                temp = data["main"]["temp"]
                desc = data["weather"][0]["description"]
                await update.message.reply_text(f"「{name}」目前的天氣:\n狀況: {desc}\n氣溫: {temp}°C\n\n"
                                                "使用 /weather 再次查詢\n"
                                                "或使用 /commandlist 檢視所有可用指令")
                user_state.pop(user_id, None)
        except Exception as e:
            await update.message.reply_text(f"查詢時發生錯誤, 請稍後再試\n錯誤內容: {e}")

    elif user_state.get(user_id) == "waiting_store":    #找菜單
        store_names = list(menu_data.keys())
        match = difflib.get_close_matches(text, store_names, n=1, cutoff=0.8)
        if user_state.get(user_id) == "waiting_store":
            found_store = None
            # 先檢查正確店名
            if text in menu_data:
                found_store = text
            else:
                # 檢查模糊拼音詞庫
                for store, fuzzy_list in fuzzy_map.items():
                    if text in fuzzy_list:
                        found_store = store
                        break
            if found_store:
                await update.message.reply_text(f"這是 <b><i>{found_store}</i></b> 的菜單", parse_mode="HTML")
                files = [os.path.join(menu_path, f) for f in menu_data[found_store]]
                for f in files:
                    if os.path.exists(f):
                        await update.message.reply_photo(open(f, "rb"))
                    else:
                        await update.message.reply_text(f"找不到檔案: {f}")
                    user_state[user_id] = None
                await update.message.reply_text("使用 /menusearch 繼續尋找菜單\n"
                                                    "或使用 /commandlist 檢視所有可用指令")
            else:
                await update.message.reply_text("沒有找到這間店的菜單, 檢查錯字或是換間店看看\n\n"
                                                
                                                "使用 /cancel 取消操作")

    else:
        await reply(update, context)

async def eatwhat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = random.choice(eat_what)
    await update.message.reply_text(f"今天吃 {choice}。\n\n"
                                    "使用 /eatwhat 再選一次要吃什麼\n"
                                    "或使用 /commandlist 檢視所有可用指令")

async def commandlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
            "這裡是我可以做的事情:\n\n"

            "/about - 關於與更新\n"
            "/menusearch - 找菜單\n"
            "/eatwhat - 吃什麼\n"
            "/weather - 查天氣\n"
            "/tarot - 抽塔羅牌\n"
            "<b><u>Beta</u></b> /shopcart - 查看你的購物車\n"
            "<b><u>Beta</u></b> /addcart - 新增東西至購物車\n"
            "<b><u>Beta</u></b> /removecart - 從購物車移除物品",
            parse_mode="HTML"
            )

async def tarot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "等等會抽三張幫你占卜\n你想要占卜什麼方面的?\n\n使用 /cancel 取消操作"
    keyboard = [[InlineKeyboardButton("感情 / 人際關係", callback_data='塔羅_感情')],
                [InlineKeyboardButton("事業 / 學業", callback_data='塔羅_事業')],
                [InlineKeyboardButton("財運 / 金錢", callback_data='塔羅_財運')],
                [InlineKeyboardButton("決策 / 選擇", callback_data='塔羅_決策')],
                [InlineKeyboardButton("整體運勢", callback_data='塔羅_整體')],
                [InlineKeyboardButton("自我成長 / 內在狀態", callback_data='塔羅_成長')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
            chat_id=update.message.chat.id,
            text=text,
            reply_markup=reply_markup
        )
    
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id  #用來取得"傳訊息給機器人的那個人"的Telegram使用者ID 辨識是不是第一次跟這個使用者互動

    keyboard = [[InlineKeyboardButton("繁體中文", callback_data='Chinese(Traditional)')],
                [InlineKeyboardButton("English", callback_data='English')],
                [InlineKeyboardButton("Español", callback_data='Spanish')],
                [InlineKeyboardButton("Deutsch", callback_data='Germany')]]  #生成按鈕
    reply_markup = InlineKeyboardMarkup(keyboard) #把按鈕排成一個可顯示的鍵盤介面（給使用者點）

    await update.message.reply_text("選擇語言\n"
                                    "Select language\n"
                                    "Seleccione el idioma\n"
                                    "Sprache auswählen",   #傳訊息給使用者 
        reply_markup=reply_markup)   #表示訊息底下附上按鈕

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "Chinese(Traditional)":
        await context.bot.send_message(
            chat_id=query.message.chat.id,
            text=
            "哈囉你好啊!\n"
            "我可以幫你做什麼?\n"
            "使用 /commandlist 檢視所有可用指令\n\n",
            parse_mode="HTML"
            )
        
    elif query.data == "English":
        await context.bot.send_message(
            chat_id=query.message.chat.id,
            text=
            "Hehe, this language is still under development.\n"
            "Stay tuned!\n"
            "Use /start to restart.")
        
    elif query.data == "Spanish":
        await context.bot.send_message(
            chat_id=query.message.chat.id,
            text=
            "Jeje, este idioma aún está en desarrollo.\n"
            "¡Estén atentos!\n"
            "Usa /start para reiniciar.")
        
    elif query.data == "Germany":
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=
            "Hehe, diese Sprache befindet sich noch in der Entwicklung.\n"
            "Bleiben Sie dran!\n"
            "Verwenden Sie /start, um neu zu starten."
        )

    elif query.data.startswith("塔羅_"):
        aspect = query.data.split("_")[1]  # 例如 '感情'、'事業'
        cards = random.sample(list(TAROT_CARDS.keys()), 3)  # 隨機抽三張牌
        text = f"你選的是「{aspect}」方面, 下面是三張你選的結果：\n\n"

        for i, card in enumerate(cards, 1):
            text += f"<b><u>{card}</u></b>\n  意思是「{TAROT_CARDS[card][aspect]}」\n\n"

        text += "! 以上占卜, 僅供參考, 請勿迷信 !\n\n使用 /tarot 再玩一次\n或使用 /commandlist 檢視所有可用指令"

        await context.bot.send_message(
            chat_id=query.message.chat.id,
            text=text, parse_mode= "HTML")

# /addcart 流程
async def addcart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("輸入商品名稱：\n\n"
                                    
                                    "或使用 /cancel 取消操作")
    return SHOP_NAME

async def get_shop_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['shop_item'] = {'shop_name': update.message.text}
    keyboard = [[InlineKeyboardButton("略過", callback_data="skip_price")]]
    await update.message.reply_text("輸入商品價格：", reply_markup=InlineKeyboardMarkup(keyboard))
    return SHOP_PRICE

async def get_shop_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['shop_item']['shop_price'] = update.message.text
    keyboard = [[InlineKeyboardButton("略過", callback_data="skip_url")]]
    await update.message.reply_text("輸入商品網址：", reply_markup=InlineKeyboardMarkup(keyboard))
    return SHOP_URL

async def skip_shop_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['shop_item']['shop_price'] = None
    keyboard = [[InlineKeyboardButton("略過", callback_data="skip_url")]]
    await update.callback_query.message.reply_text("輸入商品網址：", reply_markup=InlineKeyboardMarkup(keyboard))
    return SHOP_URL

async def get_shop_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['shop_item']['shop_url'] = update.message.text
    return await save_shop_item(update, context)

async def skip_shop_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['shop_item']['shop_url'] = None
    return await save_shop_item(update, context)

async def save_shop_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    item = context.user_data['shop_item']

    # 判斷來源：文字訊息 或 CallbackQuery
    if update.message:
        target = update.message
    elif update.callback_query:
        target = update.callback_query.message
    else:
        return ConversationHandler.END

    # 寫入 DB
    add_item_db(user_id, item)

    await target.reply_text(
        f"已新增商品：\n{item['shop_name']}\n"
        f"- 價格：{item['shop_price'] if item['shop_price'] else '未提供'}\n"
        f"- 網址：{item['shop_url'] if item['shop_url'] else '未提供'}\n\n"

        "使用 /shopcart 檢視購物車內的商品\n"
        "或使用 /commandlist 檢視所有可用指令"
    )
    return ConversationHandler.END

# /removecart 流程
async def removecart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cart = get_cart_db(user_id)

    if not cart:
        await update.message.reply_text("購物車是空的, 加個東西再刪好嗎, 急什麼?")
        return ConversationHandler.END

    items = "\n".join([f"- {name}" for name, _, _ in cart])
    await update.message.reply_text("目前購物車的商品：\n\n"
                                     + items + 
                                     "\n\n請輸入要刪除的商品名稱: \n\n"

                                     "或使用 /cancel 取消操作")
    return SHOP_NAME

async def remove_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.message.text.strip()

    cart = get_cart_db(user_id)
    found = False
    for item_name, _, _ in cart:
        if item_name.lower() == name.lower():
            found = True
            break

    if found:
        remove_item_db(user_id, name)
        await update.message.reply_text(
            f"已刪除商品：{name}\n\n"

            "使用 /removecart 刪除其他物品\n"
            "或使用 /commandlist 檢視所有可用指令"
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "購物車裡沒這東西\n"
            "你打錯字嗎?\n"
            "重新輸入看看\n\n"

            "使用 /cancel 取消操作"
        )
        return SHOP_NAME   # ← 不要結束，回到同一個狀態

async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    #偵測貼圖
    if message.sticker:
        #print(message.sticker.file_id) #需要的時候去掉井字號
        await message.reply_sticker(random.choice(sticker_list))
        return
    
    #偵測文字
    if message.text:
        text = message.text
        if text == "喔":
            await message.reply_text("喔屁喔")
            return
        elif text in ["早安", "早上好", "早ㄢ"]:
            await message.reply_text("早安!你好")
        elif "你好" in text:
            await message.reply_text("哈囉你好啊!")
            return
        else:
            await message.reply_text("我不太清楚你想要表達什麼")
    
if __name__ == "__main__":
    init_db()   # ← 確保購物車的相關資料表存在
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    #先註冊 ConversationHandler，避免被下面的 MessageHandler 攔截
    #/addcart 多步驟
    conv_add = ConversationHandler(
        entry_points=[CommandHandler("addcart", addcart)],
        states={
            SHOP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_shop_name)],
            SHOP_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_shop_price),
                CallbackQueryHandler(skip_shop_price, pattern="skip_price")],
            SHOP_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_shop_url),
                CallbackQueryHandler(skip_shop_url, pattern="skip_url")],}, fallbacks=[])
    #/removecart 多步驟
    conv_remove = ConversationHandler(
        entry_points=[CommandHandler("removecart", removecart)],
        states={
            SHOP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_item)],}, fallbacks=[])
    
    app.add_handler(conv_remove)
    app.add_handler(conv_add)
    
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("eatwhat", eatwhat))
    app.add_handler(CommandHandler("commandlist", commandlist))
    app.add_handler(CommandHandler("menusearch", menusearch))
    app.add_handler(CommandHandler("tarot", tarot))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("shopcart", shopcart))
    app.add_handler(CallbackQueryHandler(button))

    # 這些廣泛的攔截器要放在最後，避免吃掉 /addcart 等指令
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.ALL, reply))


    print("BOT IS RUNNING...")
    app.run_polling()