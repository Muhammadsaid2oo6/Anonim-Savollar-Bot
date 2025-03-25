import os
import logging
import datetime
from datetime import timezone
import hashlib
import secrets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineQueryResultArticle, InputTextMessageContent, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, InlineQueryHandler
from telegram.error import TimedOut, NetworkError
from dotenv import load_dotenv
import pymongo
from bson import ObjectId
import asyncio
from uuid import uuid4
from pymongo import MongoClient
import ssl
import certifi

# Load environment variables
load_dotenv()

# Admin user ID (your Telegram user ID)
ADMIN_USER_ID = 1153468531

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Set event loop policy at the start
asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

def get_utc_now():
    """Get current UTC time in a timezone-aware way"""
    return datetime.datetime.now(timezone.utc)

# MongoDB setup with increased timeout
try:
    mongodb_uri = os.getenv('MONGODB_URI')
    if not mongodb_uri:
        raise ValueError("MONGODB_URI environment variable is not set")
    
    client = MongoClient(mongodb_uri,
                        serverSelectionTimeoutMS=30000,
                        connectTimeoutMS=20000,
                        socketTimeoutMS=20000)
    
    # Test the connection
    client.admin.command('ping')
    logger.info("Successfully connected to MongoDB!")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    raise
db = client['hushtalkbot']
users_collection = db['users']
messages_collection = db['messages']
blocked_collection = db['blocked']

def generate_unique_code():
    """Generate a unique code for user links"""
    return secrets.token_urlsafe(8)

def get_user_stats(user_id: int) -> dict:
    """Get user statistics and ranking"""
    today = get_utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Today's stats
    today_received = messages_collection.count_documents({
        'recipient_id': user_id,
        'timestamp': {'$gte': today}
    })
    today_link_visits = messages_collection.count_documents({
        'sender_id': user_id,
        'timestamp': {'$gte': today}
    })
    
    # All time stats
    total_received = messages_collection.count_documents({'recipient_id': user_id})
    total_link_visits = messages_collection.count_documents({'sender_id': user_id})
    
    # Calculate user's rank based on total activity
    user_total_activity = total_received + total_link_visits
    
    # Get all users' activity for ranking
    all_users = users_collection.find({})
    user_activities = []
    
    for u in all_users:
        u_received = messages_collection.count_documents({'recipient_id': u['user_id']})
        u_visits = messages_collection.count_documents({'sender_id': u['user_id']})
        total_activity = u_received + u_visits
        user_activities.append(total_activity)
    
    # Sort activities in descending order
    user_activities.sort(reverse=True)
    
    # Find user's rank (1-based index)
    try:
        rank = user_activities.index(user_total_activity) + 1
    except ValueError:
        rank = len(user_activities) + 1
    
    total_users = len(user_activities) if user_activities else 1
    
    # Calculate rank percentage
    rank_percentage = (rank / total_users) * 100
    
    # Determine popularity level
    if rank_percentage <= 1:
        popularity = "🏆 ТОП-1%"
    elif rank_percentage <= 5:
        popularity = "💫 ТОП-5%"
    elif rank_percentage <= 10:
        popularity = "⭐️ ТОП-10%"
    elif rank_percentage <= 25:
        popularity = "🌟 ТОП-25%"
    elif rank_percentage <= 50:
        popularity = "✨ ТОП-50%"
    else:
        popularity = "💭 ТОП-100%"
    
    return {
        'today': {
            'messages': today_received,
            'link_visits': today_link_visits
        },
        'total': {
            'messages': total_received,
            'link_visits': total_link_visits
        },
        'rank': {
            'position': rank,
            'total_users': total_users,
            'popularity': popularity
        }
    }

def create_share_text(link_code: str) -> str:
    """Create share text without bot username mention"""
    return (
        "**Bu havola orqali menga anonim xabar yuborish mumkin:**\n\n"
        f"t.me/AskinAnonbot?start={link_code}"
    )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    try:
        user = update.effective_user
        start_param = context.args[0] if context.args else None

        if start_param:
            # Someone clicked a share link
            target_user = users_collection.find_one({'link_code': start_param})
            if target_user:
                context.user_data['reply_to'] = target_user['user_id']
                await update.message.reply_text(
                    "<i>Javobingizni yuboring. Bu matn, ovozli xabar yoki media bo'lishi mumkin 🎭</i>",
                    reply_markup=ReplyKeyboardRemove(),
                    parse_mode='HTML'
                )
                return

        # Regular start command
        # Generate unique link code if user doesn't have one
        user_data = users_collection.find_one({'user_id': user.id})
        if not user_data or 'link_code' not in user_data:
            link_code = generate_unique_code()
        else:
            link_code = user_data['link_code']

        users_collection.update_one(
            {'user_id': user.id},
            {
                '$set': {
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_active': get_utc_now(),
                    'link_code': link_code
                }
            },
            upsert=True
        )
        
        # Create the anonymous message link
        user_link = f"t.me/AskinAnonbot?start={link_code}"
        share_text = f"**Bu havola orqali menga anonim xabar yuborish mumkin:**\n\n{user_link}"
        
        welcome_message = (
            "<b>🚀 Hoziroq anonim xabarlar qabul qilishni boshlang!</b>\n\n"
            "<b>Sizning havolangiz:</b>\n"
            f"{user_link}\n\n"
            "👆 Anonim xabarlar qabul qilishni boshlash uchun ushbu havolani "
            "<b>Telegram/TikTok/Instagram</b> profil tavsifiga joylashtiring 💭"
        )
        
        share_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Havola ulashish", switch_inline_query=share_text)]
        ])
        
        await update.message.reply_text(
            welcome_message,
            reply_markup=share_button,
            parse_mode='HTML'
        )

    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text(
            "Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring."
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /mystats command"""
    try:
        user_id = update.effective_user.id
        stats = get_user_stats(user_id)
        user = users_collection.find_one({'user_id': user_id})
        link_code = user.get('link_code', generate_unique_code())
        
        user_link = f"t.me/AskinAnonbot?start={link_code}"
        share_text = f"**Bu havola orqali menga anonim xabar yuborish mumkin:**\n\n{user_link}"
        
        stats_message = (
            "<b>📊 Profil statistikasi</b>\n\n"
            "━ Bugun:\n"
            f"💬 Xabarlar: {stats['today']['messages']}\n"
            f"👥 Havola tashrifi: {stats['today']['link_visits']}\n"
            f"{stats['rank']['popularity']}\n\n"
            "━ Jami:\n"
            f"💬 Xabarlar: {stats['total']['messages']}\n"
            f"👥 Havola tashrifi: {stats['total']['link_visits']}\n"
            f"📈 Reytingdagi o'rni: {stats['rank']['position']}/{stats['rank']['total_users']}\n\n"
            "Reytingni oshirish uchun shaxsiy havolangizni tarqating:\n"
            f"👉 {user_link}"
        )
        
        share_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Havola ulashish", switch_inline_query=share_text)]
        ])
        
        await update.message.reply_text(
            stats_message,
            reply_markup=share_button,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await update.message.reply_text(
            "Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring."
        )

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle blocking a user"""
    try:
        user_id = update.effective_user.id
        message_id = context.user_data.get('last_received_message_id')
        
        if not message_id:
            await update.message.reply_text("No message to block sender from.")
            return
            
        message = messages_collection.find_one({'_id': ObjectId(message_id)})
        if message:
            blocked_collection.update_one(
                {'user_id': user_id},
                {'$addToSet': {'blocked_users': message['sender_id']}},
                upsert=True
            )
            await update.message.reply_text("✅ User has been blocked.")
    except Exception as e:
        logger.error(f"Error in block command: {e}")
        await update.message.reply_text("An error occurred. Please try again later.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    try:
        user_id = update.effective_user.id
        
        # If there's no reply_to in context, it means it's a direct message to bot
        if 'reply_to' not in context.user_data and not update.message.reply_to_message:
            # Generate or get existing link code for the user
            user_data = users_collection.find_one({'user_id': user_id})
            if not user_data or 'link_code' not in user_data:
                link_code = generate_unique_code()
            else:
                link_code = user_data['link_code']

            # Update user data
            users_collection.update_one(
                {'user_id': user_id},
                {
                    '$set': {
                        'username': update.effective_user.username,
                        'first_name': update.effective_user.first_name,
                        'last_active': get_utc_now(),
                        'link_code': link_code
                    }
                },
                upsert=True
            )
            
            # Create the anonymous message link
            user_link = f"t.me/AskinAnonbot?start={link_code}"
            share_text = f"**Bu havola orqali menga anonim xabar yuborish mumkin:**\n\n{user_link}"
            
            welcome_message = (
                "<b>🚀 Hoziroq anonim xabarlar qabul qilishni boshlang!</b>\n\n"
                "<b>Sizning havolangiz:</b>\n"
                f"{user_link}\n\n"
                "👆 Anonim xabarlar qabul qilishni boshlash uchun ushbu havolani "
                "<b>Telegram/TikTok/Instagram</b> profil tavsifiga joylashtiring 💭"
            )
            
            share_button = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Havola ulashish", switch_inline_query=share_text)]
            ])
            
            await update.message.reply_text(
                welcome_message,
                reply_markup=share_button,
                parse_mode='HTML'
            )
            return

        # Check if this is a reply to an anonymous message
        if update.message.reply_to_message:
            # Get the original message ID from the replied message
            replied_message = update.message.reply_to_message
            if replied_message and replied_message.text and ("📨 Sizga yangi anonim xabar keldi!" in replied_message.text or 
                                                          "📨 У тебя новое анонимное сообщение!" in replied_message.text):
                # Find the exact message being replied to
                original_message = messages_collection.find_one({
                    'telegram_message_id': replied_message.message_id
                })
                
                if original_message:
                    # Set recipient as the original sender
                    recipient_id = original_message['sender_id']
                    
                    # Check if user is blocked
                    blocked = blocked_collection.find_one({
                        'user_id': recipient_id,
                        'blocked_users': user_id
                    })
                    if blocked:
                        await update.message.reply_text(
                            "<i>Siz ushbu foydalanuvchiga xabar yubora olmaysiz.</i>",
                            parse_mode='HTML'
                        )
                        return
                    
                    # Store the message with reference to the message being replied to
                    message_data = {
                        'sender_id': user_id,
                        'recipient_id': recipient_id,
                        'timestamp': get_utc_now(),
                        'read': False,
                        'reply_to_message_id': replied_message.message_id  # Store the ID of the message being replied to
                    }
                    
                    # Handle different message types
                    if update.message.text:
                        message_data['content'] = update.message.text
                        message_data['type'] = 'text'
                    elif update.message.voice:
                        message_data['file_id'] = update.message.voice.file_id
                        message_data['type'] = 'voice'
                    elif update.message.photo:
                        message_data['file_id'] = update.message.photo[-1].file_id
                        message_data['type'] = 'photo'
                        if update.message.caption:
                            message_data['caption'] = update.message.caption
                    elif update.message.animation:
                        message_data['file_id'] = update.message.animation.file_id
                        message_data['type'] = 'animation'
                        if update.message.caption:
                            message_data['caption'] = update.message.caption
                    
                    message_id = messages_collection.insert_one(message_data).inserted_id
                    
                    # Create reply markup for recipient
                    reply_markup = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🚫 Bloklash", callback_data=f"block_{message_id}")
                    ]])
                    
                    try:
                        # For new messages (not replies), don't set reply_to_message_id
                        reply_to_message_id = None

                        if message_data['type'] == 'text':
                            message_text = (
                                "<b>📨 Sizga yangi anonim xabar keldi!</b>\n\n"
                                f"{message_data['content']}\n\n"
                                "↩️ Javob berish uchun xabarni chapga suring"
                            )
                            
                            sent_message = await context.bot.send_message(
                                chat_id=recipient_id,
                                text=message_text,
                                reply_markup=reply_markup,
                                parse_mode='HTML'
                            )
                            
                        elif message_data['type'] == 'voice':
                            caption = (
                                "<b>📨 Sizga yangi anonim ovozli xabar keldi!</b>\n\n"
                                "↩️ Javob berish uchun xabarni chapga suring"
                            )
                            
                            sent_message = await context.bot.send_voice(
                                chat_id=recipient_id,
                                voice=message_data['file_id'],
                                caption=caption,
                                reply_markup=reply_markup,
                                parse_mode='HTML'
                            )
                            
                        elif message_data['type'] == 'photo':
                            caption = message_data.get('caption', '')
                            photo_caption = (
                                "<b>📨 Sizga yangi anonim rasm keldi!</b>\n\n"
                                f"{caption}\n\n"
                                "↩️ Javob berish uchun xabarni chapga suring"
                            )
                            
                            sent_message = await context.bot.send_photo(
                                chat_id=recipient_id,
                                photo=message_data['file_id'],
                                caption=photo_caption,
                                reply_markup=reply_markup,
                                parse_mode='HTML'
                            )

                        elif message_data['type'] == 'animation':
                            caption = message_data.get('caption', '')
                            gif_caption = (
                                "<b>📨 Sizga yangi anonim GIF keldi!</b>\n\n"
                                f"{caption}\n\n"
                                "↩️ Javob berish uchun xabarni chapga suring"
                            )
                            
                            sent_message = await context.bot.send_animation(
                                chat_id=recipient_id,
                                animation=message_data['file_id'],
                                caption=gif_caption,
                                reply_markup=reply_markup,
                                parse_mode='HTML'
                            )
                        
                        # Store the Telegram message ID
                        messages_collection.update_one(
                            {'_id': message_id},
                            {'$set': {'telegram_message_id': sent_message.message_id}}
                        )
                        
                        # Send success message
                        success_message = (
                            "<b>✅ Xabaringiz yuborildi</b>\n"
                            "<i>Statistika — /mystats</i>"
                        )
                        await update.message.reply_text(success_message, parse_mode='HTML')
                        
                    except Exception as e:
                        logger.error(f"Failed to send reply: {e}")
                        await update.message.reply_text(
                            "<i>Xabarni yuborib bo'lmadi. Iltimos, keyinroq qayta urinib ko'ring.</i>",
                            parse_mode='HTML'
                        )
                    return
        
        # If we get here, it's a new message or not a valid reply
        if 'reply_to' in context.user_data:
            recipient_id = context.user_data['reply_to']
            
            # Check if user is trying to send message to themselves
            if recipient_id == user_id:
                await update.message.reply_text(
                    "<i>⚠️ O'zingizga xabar yubora olmaysiz.</i>",
                    parse_mode='HTML'
                )
                context.user_data.clear()
                return
            
            # Check if user is blocked
            blocked = blocked_collection.find_one({
                'user_id': recipient_id,
                'blocked_users': user_id
            })
            if blocked:
                await update.message.reply_text(
                    "<i>Вы не можете отправлять сообщения этому пользователю.</i>",
                    parse_mode='HTML'
                )
                return
            
            # Store the message
            message_data = {
                'sender_id': user_id,
                'recipient_id': recipient_id,
                'timestamp': get_utc_now(),
                'read': False
            }
            
            # Handle different message types
            if update.message.text:
                message_data['content'] = update.message.text
                message_data['type'] = 'text'
            elif update.message.voice:
                message_data['file_id'] = update.message.voice.file_id
                message_data['type'] = 'voice'
            elif update.message.photo:
                message_data['file_id'] = update.message.photo[-1].file_id
                message_data['type'] = 'photo'
                if update.message.caption:
                    message_data['caption'] = update.message.caption
            elif update.message.animation:
                message_data['file_id'] = update.message.animation.file_id
                message_data['type'] = 'animation'
                if update.message.caption:
                    message_data['caption'] = update.message.caption
            
            message_id = messages_collection.insert_one(message_data).inserted_id
            
            # Create reply markup for recipient
            reply_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("🚫 Bloklash", callback_data=f"block_{message_id}")
            ]])
            
            try:
                # For new messages (not replies), don't set reply_to_message_id
                reply_to_message_id = None

                if message_data['type'] == 'text':
                    message_text = (
                        "<b>📨 Sizga yangi anonim xabar keldi!</b>\n\n"
                        f"{message_data['content']}\n\n"
                        "↩️ Javob berish uchun xabarni chapga suring"
                    )
                    
                    sent_message = await context.bot.send_message(
                        chat_id=recipient_id,
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                    
                elif message_data['type'] == 'voice':
                    caption = (
                        "<b>📨 Sizga yangi anonim ovozli xabar keldi!</b>\n\n"
                        "↩️ Javob berish uchun xabarni chapga suring"
                    )
                    
                    sent_message = await context.bot.send_voice(
                        chat_id=recipient_id,
                        voice=message_data['file_id'],
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                    
                elif message_data['type'] == 'photo':
                    caption = message_data.get('caption', '')
                    photo_caption = (
                        "<b>📨 Sizga yangi anonim rasm keldi!</b>\n\n"
                        f"{caption}\n\n"
                        "↩️ Javob berish uchun xabarni chapga suring"
                    )
                    
                    sent_message = await context.bot.send_photo(
                        chat_id=recipient_id,
                        photo=message_data['file_id'],
                        caption=photo_caption,
                        reply_markup=reply_markup
                    )

                elif message_data['type'] == 'animation':
                    caption = message_data.get('caption', '')
                    gif_caption = (
                        "<b>📨 Sizga yangi anonim GIF keldi!</b>\n\n"
                        f"{caption}\n\n"
                        "↩️ Javob berish uchun xabarni chapga suring"
                    )
                    
                    sent_message = await context.bot.send_animation(
                        chat_id=recipient_id,
                        animation=message_data['file_id'],
                        caption=gif_caption,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                
                # Store the Telegram message ID
                messages_collection.update_one(
                    {'_id': message_id},
                    {'$set': {'telegram_message_id': sent_message.message_id}}
                )
                
                # Send success message
                success_message = (
                    "<b>✅ Xabaringiz yuborildi</b>\n"
                    "<i>Statistika — /mystats</i>"
                )
                await update.message.reply_text(success_message, parse_mode='HTML')
                context.user_data.clear()
                
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
                await update.message.reply_text(
                    "<i>Xabarni yuborib bo'lmadi. Iltimos, keyinroq qayta urinib ko'ring.</i>",
                    parse_mode='HTML'
                )
    
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text(
            "<i>Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.</i>",
            parse_mode='HTML'
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    try:
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith('forward_'):
            # Get the link code from the callback data
            link_code = query.data.split('_')[1]
            user_link = f"t.me/AskinAnonbot?start={link_code}"
            
            # Create the message that will be forwarded
            share_text = (
                "**Bu havola orqali menga anonim xabar yuborish mumkin:**\n\n"
                f"{user_link}"
            )
            
            # Send a temporary message that will be forwarded
            temp_message = await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=share_text,
                parse_mode='Markdown'
            )
            
            # Delete the "Forwarding..." message after a short delay
            await asyncio.sleep(0.5)
            await temp_message.delete()
            
            await query.answer("Выберите, куда переслать сообщение")
            
        elif query.data.startswith('block_'):
            message_id = query.data.split('_')[1]
            user_id = query.from_user.id
            
            # Find the message
            message = messages_collection.find_one({'_id': ObjectId(message_id)})
            if message:
                sender_id = message['sender_id']
                
                # Add sender to blocked users
                blocked_collection.update_one(
                    {'user_id': user_id},
                    {
                        '$addToSet': {'blocked_users': sender_id},
                        '$set': {'last_updated': get_utc_now()}
                    },
                    upsert=True
                )
                
                await query.edit_message_text(
                    "✅ Foydalanuvchi bloklandi.\n"
                    "Endi u sizga xabar yubora olmaydi.\n\n"
                    "Blokdan chiqarish uchun /blacklist buyrug'ini ishlating."
                )
                
        elif query.data.startswith('unblock_'):
            sender_id = int(query.data.split('_')[1])
            user_id = update.effective_user.id
            
            # Remove user from blocked list
            result = blocked_collection.update_one(
                {'user_id': user_id},
                {'$pull': {'blocked_users': sender_id}}
            )
            
            if result.modified_count > 0:
                await query.message.reply_text(
                    "✅ Foydalanuvchi blokdan chiqarildi va endi sizga xabar yubora oladi."
                )
            else:
                await query.message.reply_text(
                    "❌ Foydalanuvchi bloklash ro'yxatida topilmadi."
                )
            
    except Exception as e:
        logger.error(f"Error in button callback: {e}")
        await query.edit_message_text("Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    try:
        if isinstance(context.error, (TimedOut, NetworkError)):
            logger.warning(f"Network error: {context.error}")
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring."
                )
        else:
            logger.error(f"Update {update} caused error {context.error}")
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring."
                )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

async def url_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /url command"""
    try:
        user_id = update.effective_user.id
        
        # Generate new link code
        new_link_code = generate_unique_code()
        
        # Update user data with new link code
        users_collection.update_one(
            {'user_id': user_id},
            {
                '$set': {
                    'link_code': new_link_code,
                    'last_active': get_utc_now()
                }
            },
            upsert=True
        )
        
        # Create the new anonymous message link
        user_link = f"t.me/AskinAnonbot?start={new_link_code}"
        
        await update.message.reply_text(
            f"✅ Sizning yangi havolangiz:\n\n{user_link}"
        )
        
    except Exception as e:
        logger.error(f"Error in url command: {e}")
        await update.message.reply_text("Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.")

async def issue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /issue command"""
    try:
        await update.message.reply_text(
            "Botni yaxshilash uchun taklif yoki fikringizni @hasanboev_m ga yuboring",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error in issue command: {e}")
        await update.message.reply_text("Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline queries"""
    try:
        query = update.inline_query.query
        user_id = update.effective_user.id
        
        # Get user's link code
        user_data = users_collection.find_one({'user_id': user_id})
        if not user_data or 'link_code' not in user_data:
            link_code = generate_unique_code()
            users_collection.update_one(
                {'user_id': user_id},
                {
                    '$set': {
                        'link_code': link_code,
                        'last_active': get_utc_now()
                    }
                },
                upsert=True
            )
        else:
            link_code = user_data['link_code']
        
        user_link = f"t.me/AskinAnonbot?start={link_code}"
        share_text = f"**Bu havola orqali menga anonim xabar yuborish mumkin:**\n\n{user_link}"
        
        results = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="Anonim xabarlar havolasini ulashish",
                description=user_link,
                input_message_content=InputTextMessageContent(
                    share_text,
                    parse_mode='Markdown'
                ),
                thumb_url="https://example.com/anonymous_icon.png"
            )
        ]
        
        await update.inline_query.answer(results, cache_time=300)
        
    except Exception as e:
        logger.error(f"Error in inline query: {e}")

async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle edited messages"""
    try:
        await update.edited_message.reply_text(
            "<i>⚠️ Yuborilgan xabarlarni o'zgartirib bo'lmaydi. Yangi xabar yuboring.</i>",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error handling edited message: {e}")
        await update.edited_message.reply_text(
            "<i>Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.</i>",
            parse_mode='HTML'
        )

async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /blacklist command"""
    try:
        user_id = update.effective_user.id
        
        # Clear user's blacklist
        result = blocked_collection.update_one(
            {'user_id': user_id},
            {'$set': {'blocked_users': []}}
        )
        
        if result.modified_count > 0:
            await update.message.reply_text("✅ Bloklangan foydalanuvchilar ro'yxati tozalandi.")
        else:
            await update.message.reply_text("ℹ️ Bloklangan foydalanuvchilar ro'yxati bo'sh.")
            
    except Exception as e:
        logger.error(f"Error in blacklist command: {e}")
        await update.message.reply_text("Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.")

async def clear_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /cleardb command - only available to admin"""
    try:
        # Check if user is admin (you can replace this with your user ID)
        if update.effective_user.id != ADMIN_USER_ID:
            await update.message.reply_text(
                "❌ Bu buyruq faqat admin uchun."
            )
            return

        # Clear messages collection
        messages_collection.delete_many({})
        
        # Clear blocked users
        blocked_collection.delete_many({})
        
        # Clear user data except link codes
        users_collection.update_many(
            {},
            {
                '$unset': {
                    'last_active': "",
                    'username': "",
                    'first_name': ""
                }
            }
        )

        await update.message.reply_text(
            "✅ Bazadagi ma'lumotlar tozalandi.\n"
            "• Xabarlar\n"
            "• Bloklashlar\n"
            "• Foydalanuvchi statistikasi"
        )

    except Exception as e:
        logger.error(f"Error in clear_db command: {e}")
        await update.message.reply_text(
            "Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring."
        )

def main():
    """Start the bot"""
    try:
        # Create the Application with custom timeout settings
        application = (
            Application.builder()
            .token(os.getenv('TELEGRAM_BOT_TOKEN'))
            .build()
        )

        # Add handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("mystats", stats_command))
        application.add_handler(CommandHandler("url", url_command))
        application.add_handler(CommandHandler("issue", issue_command))
        application.add_handler(CommandHandler("blacklist", blacklist_command))
        application.add_handler(CommandHandler("cleardb", clear_db_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Add handler for edited messages
        application.add_handler(MessageHandler(
            filters.UpdateType.EDITED_MESSAGE,
            handle_edited_message
        ))
        
        # Message handler for all types of messages
        application.add_handler(MessageHandler(
            filters.ALL & ~filters.COMMAND & ~filters.UpdateType.EDITED_MESSAGE,
            handle_message
        ))

        # Error handler
        application.add_error_handler(error_handler)

        # Inline query handler
        application.add_handler(InlineQueryHandler(inline_query))

        logger.info("Starting bot...")

        # Set up bot commands
        commands = [
            BotCommand("start", "🚀 Botni ishga tushirish"),
            BotCommand("mystats", "📊 Statistikani ko'rish"),
            BotCommand("url", "🔄 Yangi havola yaratish"),
            BotCommand("blacklist", "🗑 Bloklash ro'yxatini tozalash"),
            BotCommand("issue", "💭 Taklif yuborish")
        ]
        
        # Set commands before starting polling
        asyncio.get_event_loop().run_until_complete(
            application.bot.set_my_commands(commands)
        )

        # Start the bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Critical error in main: {e}")
        raise

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped due to error: {e}")
    finally:
        # Clean up
        try:
            client.close()  # Close MongoDB connection
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}") 