# /server/app.py

import os
import secrets
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from celery import Celery

# --- Global Extension Instances ---
# We initialize the extensions here but will configure them inside the app factory.
db = SQLAlchemy()
bcrypt = Bcrypt()

# --- Application Factory Function ---
def create_app():
    """Creates and configures an instance of the Flask application."""
    app = Flask(__name__)

    # Load configuration from environment variables
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('FLASK_SECRET_KEY'),
        API_KEY=os.environ.get('API_KEY'),
        SQLALCHEMY_DATABASE_URI=f"postgresql://{os.environ.get('POSTGRES_USER')}:{os.environ.get('POSTGRES_PASSWORD')}@db/{os.environ.get('POSTGRES_DB')}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False
    )
    
    # Associate extensions with the app instance
    db.init_app(app)
    bcrypt.init_app(app)

    # --- Database Models ---
    # It's good practice to define models before the routes that use them.
    # Note: These are defined globally but will be associated with the app context.
    class User(db.Model):
        __tablename__ = 'users'
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(80), unique=True, nullable=False)
        password = db.Column(db.String(120), nullable=False)

    class Document(db.Model):
        __tablename__ = 'documents'
        id = db.Column(db.Integer, primary_key=True)
        filename = db.Column(db.String(255), nullable=False, unique=True)
        source_agent = db.Column(db.String(120), nullable=True)
        category = db.Column(db.String(120), nullable=True)
        status = db.Column(db.String(50), default='queued') # Status of processing
        created_at = db.Column(db.DateTime, server_default=db.func.now())


    # --- Routes ---
    @app.before_request
    def require_login():
        # Allow access to login, static files, and the API upload endpoint without a session
        if (
            request.endpoint and
            'static' not in request.endpoint and
            'api_upload' != request.endpoint and
            'user_id' not in session and
            request.endpoint != 'login'
        ):
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
        return render_template('dashboard.html', documents=documents)

    @app.route('/api/v1/query', methods=['POST'])
    def api_query():
        # In this architecture, the query would also be a job for the worker.
        # This keeps the web app lightweight.
        if 'user_id' not in session: return "Unauthorized", 401
        
        query = request.json.get('query')
        if not query: return "Query is required", 400

        # We will implement this part later, for now, return a placeholder.
        # To make it work, you'd create a Celery task for querying.
        from celery_worker import answer_query_task
        task = answer_query_task.delay(query)

        # For a more advanced setup, you'd return a task ID and poll for results.
        # For simplicity, we'll just wait for the result here.
        try:
            result = task.get(timeout=60) # Wait up to 60 seconds for an answer
            return jsonify(result)
        except Exception as e:
            print(f"Error getting task result: {e}")
            return jsonify({"error": "AI task timed out or failed."}), 500


    @app.route('/api/v1/upload', methods=['POST'])
    def api_upload():
        api_key = request.headers.get('X-API-Key')
        if not api_key or not secrets.compare_digest(api_key, app.config.get('API_KEY')):
            return jsonify({"error": "Unauthorized"}), 401
        
        file = request.files.get('document')
        if not file: return jsonify({"error": "No document file provided"}), 400

        filename = secure_filename(file.filename)
        # Ensure the uploads directory exists
        os.makedirs('/app/uploads', exist_ok=True)
        save_path = os.path.join('/app/uploads', filename)
        
        # Save the file to a shared volume for the worker to access
        file.save(save_path)

        # Import the task from the worker file and send it to the Celery queue
        from celery_worker import process_document_task
        process_document_task.delay(save_path, filename, request.headers.get('X-Agent-Name', 'default_agent'))
        
        print(f"WEB APP: Queued job for {filename}")
        return jsonify({"status": "queued for processing", "filename": filename}), 202


    # --- One-time setup command ---
    with app.app_context():
        @app.cli.command("init-db")
        def init_db_command():
            """Creates the database tables and the admin user."""
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

    return app

# This part is only for direct `flask run`, not for gunicorn
if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000)