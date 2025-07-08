# /server/app.py (Corrected for Threading)

import os, pickle, requests, threading, secrets
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt

# --- App Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://{os.environ.get('POSTGRES_USER')}:{os.environ.get('POSTGRES_PASSWORD')}@db/{os.environ.get('POSTGRES_DB')}"
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
model = pickle.load(open('model.pkl', 'rb'))

# --- Database Models (Unchanged) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    source_agent = db.Column(db.String(120), nullable=True, default='default_agent')
    content = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

# --- Authentication & Main Routes (Unchanged) ---
@app.before_request
def require_login():
    allowed_routes = ['login', 'static', 'api_upload']
    if 'user_id' not in session and request.endpoint not in allowed_routes:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and bcrypt.check_password_hash(user.password, request.form['password']):
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/')
def dashboard():
    # Pass the API_KEY from the config to the template
    documents = Document.query.order_by(Document.created_at.desc()).limit(100).all()
    api_key = os.environ.get('API_KEY', 'Not Set')
    return render_template('dashboard.html', documents=documents, api_key=api_key)

# --- CORRECTED API & Background Processing ---
def process_document(app_context, file_content, filename, agent_name):
    """
    This function now runs with the application context passed from the main thread.
    This gives it access to the database and other app configurations.
    """
    with app_context:
        try:
            # 1. Extract content with Tika
            tika_url = os.environ.get('TIKA_SERVER_URL', 'http://tika:9998/tika')
            response = requests.put(tika_url, data=file_content, headers={"Accept": "text/plain"})
            response.raise_for_status()
            text_content = response.text.strip()

            if not text_content:
                print(f"Tika returned no content for {filename}")
                return

            # 2. Classify with ML Model
            category = model.predict([text_content])[0]

            # 3. Save to database
            new_doc = Document(
                filename=filename,
                content=text_content,
                category=category,
                source_agent=agent_name
            )
            db.session.add(new_doc)
            db.session.commit()
            print(f"SUCCESS: Processed and saved document: {filename}, Category: {category}")

        except Exception as e:
            # This will print the exact Python error to the Docker logs
            print(f"!!! ERROR processing {filename}: {e}")
            db.session.rollback() # Rollback any partial database changes

@app.route('/api/v1/upload', methods=['POST'])
def api_upload():
    api_key = request.headers.get('X-API-Key')
    if not api_key or not secrets.compare_digest(api_key, os.environ.get('API_KEY')):
        return jsonify({"error": "Unauthorized"}), 401

    file = request.files.get('document')
    if not file:
        return jsonify({"error": "No document file provided"}), 400

    agent_name = request.headers.get('X-Agent-Name', 'default_agent')
    file_content = file.read()
    filename = file.filename

    # This is the correct way to pass the app context to a thread
    thread = threading.Thread(target=process_document, args=(app.app_context(), file_content, filename, agent_name))
    thread.start()

    return jsonify({"status": "received", "filename": filename}), 202
# --- END OF CORRECTION ---

# --- One-time setup command (Unchanged) ---
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
    app.run(host='0.0.0.0', port=5000)