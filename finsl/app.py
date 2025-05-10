from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import sqlite3
import google.generativeai as genai
import json
import re
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Required for Flask-Login

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, role, mentor_id=None, class_assigned=None, student_id=None):
        self.id = id
        self.username = username
        self.role = role
        self.mentor_id = mentor_id
        self.class_assigned = class_assigned
        self.student_id = student_id

# Load user from the database
@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    if user_data:
        return User(
            id=user_data[0],
            username=user_data[1],
            role=user_data[3],
            mentor_id=user_data[4],
            class_assigned=user_data[5],
            student_id=user_data[6]
        )
    return None

# Configure API Key
genai.configure(api_key="AIzaSyCYfPR6NW1cCO9KklIcl4vIPIEoKRLyQZM")

# Load the Gemini model
model = genai.GenerativeModel("gemini-2.0-flash")

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

# Function to add chat memory
def add_to_chat_memory(role, content):
    conn = sqlite3.connect("chat_memory.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO memory (role, content) VALUES (?, ?)", (role, content))
    conn.commit()
    conn.close()

# Function to retrieve chat memory
def get_chat_memory():
    conn = sqlite3.connect("chat_memory.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM memory")
    memory = cursor.fetchall()
    conn.close()
    return memory

# Function to clear chat memory
def clear_chat_memory():
    conn = sqlite3.connect("chat_memory.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM memory")
    conn.commit()
    conn.close()

# Load students.db into memory when the app starts
students_data = load_students_db()

# Routes for authentication
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = sqlite3.connect("students.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user_data = cursor.fetchone()
        conn.close()

        if user_data and check_password_hash(user_data[2], password):
            user = User(
                id=user_data[0],
                username=user_data[1],
                role=user_data[3],
                mentor_id=user_data[4],
                class_assigned=user_data[5],
                student_id=user_data[6]
            )
            login_user(user)

            # Redirect based on role
            if user.role == "hod":
                return redirect(url_for("hod"))
            elif user.role == "mentor":
                if user.mentor_id == 1:
                    return redirect(url_for("mentor1"))
                elif user.mentor_id == 2:
                    return redirect(url_for("mentor2"))
                elif user.mentor_id == 3:
                    return redirect(url_for("mentor3"))
            elif user.role == "class_teacher":
                if user.class_assigned == "A":
                    return redirect(url_for("teacherA"))
                elif user.class_assigned == "B":
                    return redirect(url_for("teacherB"))
                elif user.class_assigned == "C":
                    return redirect(url_for("teacherC"))
            elif user.role == "student":
                return redirect(url_for("student"))

        else:
            flash("Invalid username or password")
    return render_template("login.html")

# Logout route
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route('/hod_dashboard')
def hod_dashboard():
    return render_template('hod_dashboard.html')

# Root route
@app.route("/")
@login_required
def home():
    # Redirect users to their respective role-specific pages after login
    if current_user.role == "hod":
        return redirect(url_for("hod"))
    elif current_user.role == "mentor":
        if current_user.mentor_id == 1:
            return redirect(url_for("mentor1"))
        elif current_user.mentor_id == 2:
            return redirect(url_for("mentor2"))
        elif current_user.mentor_id == 3:
            return redirect(url_for("mentor3"))
    elif current_user.role == "class_teacher":
        if current_user.class_assigned == "A":
            return redirect(url_for("teacherA"))
        elif current_user.class_assigned == "B":
            return redirect(url_for("teacherB"))
        elif current_user.class_assigned == "C":
            return redirect(url_for("teacherC"))
    elif current_user.role == "student":
        return redirect(url_for("student"))
    else:
        return redirect(url_for("login"))

# Role-specific routes
@app.route("/hod")
@login_required
def hod():
    if current_user.role != "hod":
        return redirect(url_for("login"))
    return render_template("hod.html")

@app.route("/mentor1")
@login_required
def mentor1():
    if current_user.role != "mentor" or current_user.mentor_id != 1:
        return redirect(url_for("login"))
    return render_template("mentor1.html")

@app.route("/mentor2")
@login_required
def mentor2():
    if current_user.role != "mentor" or current_user.mentor_id != 2:
        return redirect(url_for("login"))
    return render_template("mentor2.html")

@app.route("/mentor3")
@login_required
def mentor3():
    if current_user.role != "mentor" or current_user.mentor_id != 3:
        return redirect(url_for("login"))
    return render_template("mentor3.html")

@app.route("/teacherA")
@login_required
def teacherA():
    if current_user.role != "class_teacher" or current_user.class_assigned != "A":
        return redirect(url_for("login"))
    return render_template("teacherA.html")

@app.route("/teacherB")
@login_required
def teacherB():
    if current_user.role != "class_teacher" or current_user.class_assigned != "B":
        return redirect(url_for("login"))
    return render_template("teacherB.html")

@app.route("/teacherC")
@login_required
def teacherC():
    if current_user.role != "class_teacher" or current_user.class_assigned != "C":
        return redirect(url_for("login"))
    return render_template("teacherC.html")

@app.route("/student")
@login_required
def student():
    if current_user.role != "student":
        return redirect(url_for("login"))
    return render_template("student.html")

# Chatbot routes
@app.route("/chat", methods=["POST"])
@login_required
def chat():
    user_input = request.json.get("message")
    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    # Load the latest data from the database
    students_data = load_students_db()
    students = json.loads(students_data)

    # Filter students data based on the user's role
    filtered_students = []
    if current_user.role == "hod":
        # HOD has access to all data
        filtered_students = students
    elif current_user.role == "mentor":
        # Mentors can only access their assigned students
        filtered_students = [s for s in students if s["mentor_id"] == current_user.mentor_id]
    elif current_user.role == "class_teacher":
        # Class teachers can only access students in their assigned class
        filtered_students = [s for s in students if s["class_assigned"] == current_user.class_assigned]
    elif current_user.role == "student":
        # Students can only access their own data
        filtered_students = [s for s in students if s["roll_number"] == current_user.student_id]

    # If no students are found for the user's role, return "No student found"
    if not filtered_students:
        return jsonify({"response": "No student found."})

    # Convert filtered students back to JSON
    filtered_students_json = json.dumps(filtered_students, indent=2)

    # Get the chatbot's response
    chatbot_response = get_chatbot_response(user_input, filtered_students_json)

    # Add user input and chatbot response to chat memory
    add_to_chat_memory("User", user_input)
    add_to_chat_memory("Chatbot", chatbot_response)

    return jsonify({"response": chatbot_response})

@app.route("/view_memory", methods=["GET"])
@login_required
def view_memory():
    """
    Display the current conversation memory.
    """
    memory = get_chat_memory()
    return jsonify({"memory": memory})

@app.route("/clear", methods=["POST"])
@login_required
def clear_memory():
    """
    Clear the conversation memory.
    """
    clear_chat_memory()
    return jsonify({"status": "Memory cleared"})

if __name__ == "__main__":
    app.run(debug=True)