import g4f
from g4f.client import Client
from config import serverprompt, text_model, image_model, token
import telebot
import asyncio
import time
import json
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from asyncio import WindowsSelectorEventLoopPolicy

# Set the correct event loop policy for Windows
asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())

bot = telebot.TeleBot(token)

# Persistent user modes and history
user_modes = {}
user_last_request = {}
user_history = {}  # For storing user conversation histories

HISTORY_FILE = "user_history.json"
MODES_FILE = "user_modes.json"
MAX_HISTORY_LENGTH = 10  # Maximum messages to keep in history per user


# Load user modes from a file
def load_modes():
    global user_modes
    try:
        with open(MODES_FILE, "r") as f:
            user_modes.update(json.load(f))
    except FileNotFoundError:
        pass


# Save user modes to a file
def save_modes():
    with open(MODES_FILE, "w") as f:
        json.dump(user_modes, f)


# Load user history from a file
def load_history():
    global user_history
    try:
        with open(HISTORY_FILE, "r") as f:
            user_history.update(json.load(f))
    except FileNotFoundError:
        pass


# Save user history to a file
def save_history():
    with open(HISTORY_FILE, "w") as f:
        json.dump(user_history, f)


# Load modes and history at startup
load_modes()
load_history()


def is_rate_limited(user_id, cooldown=5):
    """
    Check if the user is rate-limited based on the cooldown period.
    """
    now = time.time()
    if user_id in user_last_request and now - user_last_request[user_id] < cooldown:
        return True
    user_last_request[user_id] = now
    return False


def ask(prompt, user_id) -> str:
    """
    Function to ask the GPT model and return the answer.
    """
    try:
        print(f"Asking GPT with prompt: {prompt}")
        
        # Retrieve or initialize the user's conversation history
        history = user_history.get(str(user_id), [])
        
        # Add the system prompt if the user has no history
        if not history:
            history.append({"role": "system", "content": serverprompt})
        
        # Add the new user message
        history.append({"role": "user", "content": prompt})
        
        # Call the model with the user's history
        response = g4f.ChatCompletion.create(
            model=text_model,
            messages=history,
            stream=True,
        )
        
        # Collect the response
        ans_message = ''
        for message in response:
            if isinstance(message, str):
                ans_message += message
            elif isinstance(message, dict):
                ans_message += message.get('choices', [{}])[0].get('message', {}).get('content', '')
        
        # Add the response to the history
        history.append({"role": "assistant", "content": ans_message})
        
        # Limit history length
        user_history[str(user_id)] = history[-MAX_HISTORY_LENGTH:]
        save_history()  # Persist the updated history
        
        return ans_message
    except Exception as e:
        print(f"Error in ask function: {e}")
        return f"خطا در پردازش درخواست: {str(e)}"


def generate_image(prompt) -> str:
    """
    Function to generate an image using g4f Client and return the image URL.
    """
    try:
        print(f"Generating image with prompt: {prompt}")
        client = Client()
        response = client.images.generate(
            model=image_model,
            prompt=prompt,
            response_format="url"
        )
        if not response or not response.data:
            raise Exception("Empty or invalid response from image generation API.")
        image_url = response.data[0].url
        print(f"Generated Image URL: {image_url}")
        return image_url
    except Exception as e:
        print(f"Error in generate_image function: {e}")
        return f"خطا در ایجاد تصویر: {str(e)}"


def question(message):
    user_id = message.chat.id
    mode = user_modes.get(user_id, "text")  # Default to text mode

    if is_rate_limited(user_id):
        bot.send_message(user_id, "لطفاً کمی صبر کنید و دوباره امتحان کنید.")
        return

    msg = bot.send_message(user_id, '⏳')
    bot.send_chat_action(user_id, "typing")

    question = message.text

    if mode == "text":
        answer = ask(question, user_id)
        if not answer:
            answer = "متأسفم، نتوانستم درخواست شما را پردازش کنم."
        bot.edit_message_text(chat_id=user_id, message_id=msg.message_id, text=answer)
    elif mode == "image":
        image_url = generate_image(question)
        if not image_url.startswith("http"):
            bot.edit_message_text(chat_id=user_id, message_id=msg.message_id, text=image_url)  # Show error message
        else:
            bot.delete_message(chat_id=user_id, message_id=msg.message_id)
            bot.send_photo(chat_id=user_id, photo=image_url, caption="تصویر شما:")


@bot.message_handler(commands=['start'])
def start_message(message):
    user_id = message.chat.id
    user_modes[user_id] = "text"  # Default mode
    save_modes()

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("📝 حالت متن"), KeyboardButton("🖼️ حالت تصویر"))
    
    bot.send_message(
        message.chat.id,
        '👋 سلام! من یک ربات دارای هوش مصنوعی هستم. از من سوال بپرس یا یک تصویر ایجاد کن. با دکمه‌های زیر می‌توانید حالت خود را تغییر دهید.',
        reply_markup=markup
    )


@bot.message_handler(func=lambda message: message.text in ["📝 حالت متن", "🖼️ حالت تصویر"])
def handle_mode_change(message):
    user_id = message.chat.id
    if message.text == "📝 حالت متن":
        user_modes[user_id] = "text"
        save_modes()
        bot.send_message(user_id, "حالت شما به متن تغییر یافت.")
    elif message.text == "🖼️ حالت تصویر":
        user_modes[user_id] = "image"
        save_modes()
        bot.send_message(user_id, "حالت شما به تصویر تغییر یافت برای نتیجه بهتر به زبان انگلیسی درخواست دهید.")


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        question(message)  # Process the question
    except Exception as e:
        print(f"Error processing message: {e}")
        bot.send_message(message.chat.id, f"متأسفم، خطایی رخ داده است: {str(e)}")


if __name__ == '__main__':
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"Error during polling: {e}")
