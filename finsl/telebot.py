from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
import sqlite3
from werkzeug.security import check_password_hash
import google.generativeai as genai
import json
import re

# Define conversation states
USERNAME, PASSWORD = range(2)

# Dictionary to track authenticated users
AUTHENTICATED_USERS = {}

# Configure Gemini API Key
genai.configure(api_key="AIzaSyC5NDxnN7-b3gYV4kRh3fV7lYVw2rmGa-I")

# Load the Gemini model
model = genai.GenerativeModel("gemini-2.0-flash")

# Function to authenticate users
def authenticate_user(username, password):
    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user_data = cursor.fetchone()
    conn.close()

    if user_data and check_password_hash(user_data[2], password):  # user_data[2] is password_hash
        return {
            "id": user_data[0],
            "username": user_data[1],
            "role": user_data[3],
            "mentor_id": user_data[4] if user_data[4] else None,
            "class_assigned": user_data[5] if user_data[5] else None,
            "student_id": user_data[6] if user_data[6] else None,
        }
    return None

# Load students.db into a JSON string
def load_students_db():
    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students")
    columns = [column[0] for column in cursor.description]  # Get column names
    students = [dict(zip(columns, row)) for row in cursor.fetchall()]  # Convert rows to dictionaries
    conn.close()
    return json.dumps(students, indent=2)  # Convert to JSON string

# Function to clean Gemini's response
def clean_response(response):
    """
    Remove unwanted formatting (e.g., JSON, markdown) from Gemini's response.
    """
    # Remove JSON formatting
    response = re.sub(r"```json.*?```", "", response, flags=re.DOTALL)
    # Remove markdown symbols (e.g., **)
    response = re.sub(r"\*\*", "", response)
    # Remove extra whitespace
    response = response.strip()
    return response

# Function to generate chatbot response
def get_chatbot_response(user_input, students_data):
    """
    Generate a response using Gemini based on the user's input and students data.
    """
    try:
        # Construct the prompt for Gemini
        prompt = f"""
        You are a helpful assistant that analyzes student data. Below is the student database in JSON format:

        {students_data}

        Analyze the data and answer the following question in a concise and plain-text format:
        {user_input}

        Do not use JSON, markdown, or any special formatting. Provide only the requested information.
        """

        # Get response from Gemini
        response = model.generate_content(prompt)
        # Clean the response
        cleaned_response = clean_response(response.text)
        return cleaned_response
    except Exception as e:
        return f"Error: {str(e)}"

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Please enter your username.")
    return USERNAME  # Move to the USERNAME state

# Handle username input
async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text
    context.user_data["username"] = username  # Store username in context
    await update.message.reply_text("Please enter your password.")
    return PASSWORD  # Move to the PASSWORD state

# Handle password input
async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text
    username = context.user_data.get("username")  # Retrieve username from context

    user = authenticate_user(username, password)
    if user:
        AUTHENTICATED_USERS[update.message.from_user.id] = user
        await update.message.reply_text("Authentication successful! You can now use the bot.")
        return ConversationHandler.END  # End the conversation
    else:
        await update.message.reply_text("Invalid username or password. Please try again.")
        return USERNAME  # Go back to the USERNAME state

# Handle user queries
async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = AUTHENTICATED_USERS.get(user_id)

    if not user:
        await update.message.reply_text("Please authenticate using /start.")
        return

    user_input = update.message.text
    students_data = load_students_db()
    students = json.loads(students_data)

    # Filter students data based on the user's role
    filtered_students = []
    if user["role"] == "hod":
        # HOD has access to all data
        filtered_students = students
    elif user["role"] == "mentor":
        # Mentors can only access their assigned students
        filtered_students = [s for s in students if s["mentor_id"] == user["mentor_id"]]
    elif user["role"] == "class_teacher":
        # Class teachers can only access students in their assigned class
        filtered_students = [s for s in students if s["class_assigned"] == user["class_assigned"]]
    elif user["role"] == "student":
        # Students can only access their own data
        filtered_students = [s for s in students if s["roll_number"] == user["student_id"]]

    # If no students are found for the user's role, return "No student found"
    if not filtered_students:
        await update.message.reply_text("No student found.")
        return

    # Convert filtered students back to JSON
    filtered_students_json = json.dumps(filtered_students, indent=2)

    # Get the chatbot's response
    chatbot_response = get_chatbot_response(user_input, filtered_students_json)
    await update.message.reply_text(chatbot_response)

# Cancel command
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Authentication canceled.")
    return ConversationHandler.END  # End the conversation

# Main function
if __name__ == "__main__":
    # Replace with your actual Telegram bot token
    TELEGRAM_BOT_TOKEN = "7973993133:AAE2ombOAhldLyLU9LbpszsW-buu9WoEJ0E"

    # Set up the application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Define the conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],  # Start command
        states={
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username)],  # Handle username
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password)],  # Handle password
        },
        fallbacks=[CommandHandler("cancel", cancel)],  # Cancel command
    )

    # Add the conversation handler to the application
    app.add_handler(conv_handler)

    # Add a handler for user queries
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_query))

    # Start the bot
    print("Bot is running...")
    app.run_polling()