import os, pickle, requests, threading, secrets
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt

import chromadb
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from langchain_community.llms import Ollama
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
app.config['API_KEY'] = os.environ.get('API_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://{os.environ.get('POSTGRES_USER')}:{os.environ.get('POSTGRES_PASSWORD')}@db/{os.environ.get('POSTGRES_DB')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
model = pickle.load(open('model.pkl', 'rb'))

qa_chain_instance = None
vector_store = None

def get_qa_chain():
    global qa_chain_instance, vector_store
    if qa_chain_instance is None:
        print("Initializing AI components for the first time...")
        embedding_function = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
        chroma_client = chromadb.HttpClient(host="chroma", port=8000)
        vector_store = Chroma(
            client=chroma_client,
            collection_name="corpus_documents",
            embedding_function=embedding_function,
        )
        llm = Ollama(model="tinyllama", base_url="http://ollama:11434")
        qa_chain_instance = RetrievalQA.from_chain_type(
            llm,
            retriever=vector_store.as_retriever(search_kwargs={"k": 5}),
            return_source_documents=True
        )
        print("AI components initialized successfully.")
    return qa_chain_instance

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False, unique=True)
    source_agent = db.Column(db.String(120), nullable=True, default='default_agent')
    category = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

@app.before_request
def require_login():
    if request.endpoint and 'static' not in request.endpoint and 'api_upload' != request.endpoint and 'user_id' not in session and request.endpoint != 'login':
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
    if 'user_id' not in session: return "Unauthorized", 401
    query = request.json.get('query')
    if not query: return "Query is required", 400
    try:
        chain = get_qa_chain()
        result = chain.invoke({"query": query})
        source_filenames = {doc.metadata.get('source_filename', 'Unknown') for doc in result.get('source_documents', [])}
        response_data = {"answer": result.get('result', 'No answer found.'), "sources": list(source_filenames)}
        return jsonify(response_data)
    except Exception as e:
        print(f"QA Chain Error: {e}")
        return jsonify({"error": "Failed to process AI query. The AI services may still be initializing."}), 500

def process_document(app_context, file_content, filename, agent_name):
    with app_context:
        try:
            global vector_store
            if vector_store is None: get_qa_chain()
            if Document.query.filter_by(filename=filename).first():
                print(f"SKIPPING: Document '{filename}' already exists.")
                return

            tika_url = os.environ.get('TIKA_SERVER_URL', 'http://tika:9998/tika')
            response = requests.put(tika_url, data=file_content, headers={"Accept": "text/plain", "Content-Type": "application/octet-stream"})
            response.raise_for_status()
            text_content = response.text.strip()
            if not text_content: return

            category = model.predict([text_content])[0]
            new_doc = Document(filename=filename, category=category, source_agent=agent_name)
            db.session.add(new_doc)
            db.session.commit()
            print(f"SUCCESS: Saved metadata for {filename}")

            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            docs_for_vector_db = text_splitter.create_documents([text_content], metadatas=[{"source_filename": filename}])
            vector_store.add_documents(docs_for_vector_db, ids=[f"{filename}_{i}" for i, _ in enumerate(docs_for_vector_db)])
            print(f"SUCCESS: Ingested {filename} into vector store.")
        except Exception as e:
            print(f"!!! ERROR processing {filename}: {e}")
            db.session.rollback()

@app.route('/api/v1/upload', methods=['POST'])
def api_upload():
    api_key = request.headers.get('X-API-Key')
    if not api_key or not secrets.compare_digest(api_key, app.config.get('API_KEY')):
        return jsonify({"error": "Unauthorized"}), 401
    
    file = request.files.get('document')
    if not file: return jsonify({"error": "No document file provided"}), 400

    agent_name = request.headers.get('X-Agent-Name', 'default_agent')
    file_content = file.read()
    filename = file.filename
    
    thread = threading.Thread(target=process_document, args=(app.app_context(), file_content, filename, agent_name))
    thread.start()
    return jsonify({"status": "received", "filename": filename}), 202

@app.cli.command("init-db")
def init_db_command():
    with app.app_context():
        db.create_all()
        admin_user = os.environ.get('ADMIN_USERNAME')
        admin_pass = os.environ.get('ADMIN_PASSWORD')
        if not User.query.filter_by(username=admin_user).first():
            hashed_password = bcrypt.generate_password_hash(admin_pass).decode('utf-8')
            db.session.add(User(username=admin_user, password=hashed_password))
            db.session.commit()
            print("Admin user created.")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)