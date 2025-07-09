# /server/app.py

import os
import secrets
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from celery import Celery
import celery_worker

# --- App Initialization ---
# This pattern allows the app and extensions to be imported by other modules (like the worker)
app = Flask(__name__)
app.config.from_mapping(
    SECRET_KEY=os.environ.get('FLASK_SECRET_KEY'),
    API_KEY=os.environ.get('API_KEY'),
    SQLALCHEMY_DATABASE_URI=f"postgresql://{os.environ.get('POSTGRES_USER')}:{os.environ.get('POSTGRES_PASSWORD')}@db/{os.environ.get('POSTGRES_DB')}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    CELERY_BROKER_URL='redis://redis:6379/0',
    CELERY_RESULT_BACKEND='redis://redis:6379/0'
)

# --- Celery Integration ---
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# --- Extensions and DB Models ---
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    source_agent = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(50), default='queued') # queued, processing, completed, failed
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())


# --- App Factory (for Gunicorn) ---
def create_app():
    return app

# --- Routes ---
@app.before_request
def require_login():
    if (request.endpoint and 'static' not in request.endpoint and 'api_upload' != request.endpoint and
        'user_id' not in session and request.endpoint != 'login'):
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
    documents = Document.query.order_by(Document.created_at.desc()).limit(100).all()
    return render_template('dashboard.html', documents=documents, api_key=app.config['API_KEY'])

@app.route('/api/v1/query', methods=['POST'])
def api_query():
    if 'user_id' not in session: return "Unauthorized", 401
    query = request.json.get('query')
    if not query: return "Query is required", 400
    
    task = celery_worker.answer_query_task.delay(query)
    try:
        result = task.get(timeout=60)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"AI task timed out or failed: {e}"}), 500

@app.route('/api/v1/upload', methods=['POST'])
def api_upload():
    # <<< FIX: Entire logic updated for robustness >>>
    api_key = request.headers.get('X-API-Key')
    if not api_key or not secrets.compare_digest(api_key, app.config['API_KEY']):
        return jsonify({"error": "Unauthorized"}), 401
    
    file = request.files.get('document')
    if not file or not file.filename: return jsonify({"error": "No document file provided"}), 400

    filename = secure_filename(file.filename)
    save_path = os.path.join('/app/uploads', filename)
    
    # Avoid overwriting; add a timestamp if file exists
    if os.path.exists(save_path):
        name, ext = os.path.splitext(filename)
        timestamp = secrets.token_hex(4)
        filename = f"{name}_{timestamp}{ext}"
        save_path = os.path.join('/app/uploads', filename)

    os.makedirs('/app/uploads', exist_ok=True)
    file.save(save_path)

    # 1. Create the DB record immediately
    try:
        agent_name = request.headers.get('X-Agent-Name', 'default_agent')
        new_doc = Document(filename=filename, source_agent=agent_name, status='queued')
        db.session.add(new_doc)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Database error on record creation: {e}"}), 500
    
    # 2. Queue the background job with the document's ID
    celery_worker.process_document_task.delay(new_doc.id, save_path)
    print(f"WEB APP: Queued job for {filename} (ID: {new_doc.id})")
    return jsonify({"status": "queued for processing", "filename": filename}), 202

# --- CLI Command ---
@app.cli.command("init-db")
def init_db_command():
    db.create_all()
    admin_user = os.environ.get('ADMIN_USERNAME')
    admin_pass = os.environ.get('ADMIN_PASSWORD')
    if not User.query.filter_by(username=admin_user).first():
        hashed_password = bcrypt.generate_password_hash(admin_pass).decode('utf-8')
        db.session.add(User(username=admin_user, password=hashed_password))
        db.session.commit()
        print("Admin user created.")
    else:
        print("Admin user already exists.")