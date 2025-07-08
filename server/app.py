# /server/app.py

import os, json, pickle, requests, threading, secrets
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename

# --- App Initialization ---
app = Flask(__name__)
# Load configuration from environment variables
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://{os.environ.get('POSTGRES_USER')}:{os.environ.get('POSTGRES_PASSWORD')}@db/{os.environ.get('POSTGRES_DB')}"
app.config['API_KEY'] = os.environ.get('API_KEY') # Make API Key accessible in the app config

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
model = pickle.load(open('model.pkl', 'rb'))

# --- Database Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    source_agent = db.Column(db.String(120), nullable=True)
    content = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

# --- Authentication ---
@app.before_request
def require_login():
    # Define routes that don't require login
    allowed_routes = ['login', 'static', 'api_upload']
    # If the user is not logged in and is trying to access a protected route
    if 'user_id' not in session and request.endpoint not in allowed_routes:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and bcrypt.check_password_hash(user.password, request.form['password']):
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
        # You might want to add an error message for failed logins here
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

# --- Main Dashboard ---
@app.route('/')
def dashboard():
    documents = Document.query.order_by(Document.created_at.desc()).all()
    # --- THIS IS THE FIX ---
    # We pass the entire app.config object to the template.
    # This makes all config variables, including API_KEY, available in the HTML.
    return render_template('dashboard.html', documents=documents, config=app.config)

# --- API for Agents ---
@app.route('/api/v1/upload', methods=['POST'])
def api_upload():
    api_key = request.headers.get('X-API-Key')
    # Use the app.config value for comparison
    if not api_key or not secrets.compare_digest(api_key, app.config['API_KEY']):
        return jsonify({"error": "Unauthorized"}), 401
    
    file = request.files.get('document')
    if not file:
        return jsonify({"error": "No document file provided"}), 400
    
    # Process the file in a background thread to not block the agent
    # We pass the file content and filename to the thread
    thread = threading.Thread(target=process_document, args=(file.read(), file.filename, app._get_current_object()))
    thread.start()
    
    return jsonify({"status": "received", "filename": file.filename}), 202

def process_document(file_content, filename, app_context):
    # The background thread needs the application context to work with the database
    with app_context.app_context():
        # 1. Extract content with Tika
        tika_url = os.environ.get('TIKA_SERVER_URL', 'http://tika:9998/tika')
        try:
            response = requests.put(tika_url, data=file_content, headers={"Accept": "text/plain"})
            response.raise_for_status()
            text_content = response.text.strip()
        except requests.exceptions.RequestException as e:
            print(f"Tika processing failed for {filename}: {e}")
            return

        # 2. Classify with ML Model
        category = model.predict([text_content])[0]

        # 3. Save to database
        doc = Document(filename=filename, content=text_content, category=category)
        db.session.add(doc)
        db.session.commit()
        print(f"Processed and saved document: {filename}, Category: {category}")

# --- One-time setup command ---
@app.cli.command("init-db")
def init_db_command():
    """Creates the database tables and the admin user."""
    with app.app_context():
        db.create_all()
        admin_user = os.environ.get('ADMIN_USERNAME')
        admin_pass = os.environ.get('ADMIN_PASSWORD')
        if not User.query.filter_by(username=admin_user).first():
            hashed_password = bcrypt.generate_password_hash(admin_pass).decode('utf-8')
            new_user = User(username=admin_user, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            print("Admin user created.")
        else:
            print("Admin user already exists.")

if __name__ == '__main__':
    # This block is for direct execution, e.g., 'python app.py'
    app.run(host='0.0.0.0', port=5000)