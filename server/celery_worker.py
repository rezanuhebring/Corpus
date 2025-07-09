# /server/celery_worker.py

import os, pickle, requests
from celery import Celery
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Import AI/RAG Libraries
import chromadb
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from langchain_community.llms import Ollama
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA

# --- Celery and Flask App Setup ---
# This mirrors the setup in app.py so the worker has the same context
celery = Celery(__name__, broker='redis://redis:6379/0', backend='redis://redis:6379/0')
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://{os.environ.get('POSTGRES_USER')}:{os.environ.get('POSTGRES_PASSWORD')}@db/{os.environ.get('POSTGRES_DB')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Must redefine the model here so Celery knows about the table structure
class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False, unique=True)
    source_agent = db.Column(db.String(120), nullable=True)
    category = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, server_default=db.func.now())

# --- Initialize AI Components ---
# This happens once when the worker starts.
print("--- Worker Initializing AI Engine... ---")
embedding_function = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
chroma_client = chromadb.HttpClient(host="chroma", port=8000)
vector_store = Chroma(client=chroma_client, collection_name="corpus_documents", embedding_function=embedding_function)
# model = pickle.load(open('model.pkl', 'rb')) # You can load your classifier here if needed
print("--- Worker AI Engine Ready. ---")

# --- Celery Task Definition ---
@celery.task
def process_document_task(file_path, filename, agent_name):
    with app.app_context():
        try:
            print(f"WORKER: Processing job for {filename}")
            
            # 1. Read file content
            with open(file_path, 'rb') as f:
                file_content = f.read()

            # 2. Check if metadata record already exists
            doc_record = Document.query.filter_by(filename=filename).first()
            if not doc_record:
                # Create a placeholder record
                doc_record = Document(filename=filename, source_agent=agent_name, status='processing')
                db.session.add(doc_record)
                db.session.commit()
            elif doc_record.status == 'completed':
                print(f"SKIPPING: Document '{filename}' already processed.")
                os.remove(file_path) # Clean up the uploaded file
                return

            # 3. Tika Extraction
            tika_url = os.environ.get('TIKA_SERVER_URL', 'http://tika:9998/tika')
            response = requests.put(tika_url, data=file_content, headers={"Accept": "text/plain", "Content-Type": "application/octet-stream"})
            response.raise_for_status()
            text_content = response.text.strip()
            if not text_content:
                doc_record.status = 'failed_no_content'
                db.session.commit()
                return

            # 4. Ingest into Vector Store
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            docs_for_vector_db = text_splitter.create_documents([text_content], metadatas=[{"source_filename": filename}])
            vector_store.add_documents(docs_for_vector_db, ids=[f"{filename}_{i}" for i, _ in enumerate(docs_for_vector_db)])
            
            # 5. Update the record in PostgreSQL
            # category = model.predict([text_content])[0] # You can add classification back here
            # doc_record.category = category
            doc_record.status = 'completed'
            db.session.commit()

            print(f"SUCCESS: Job for {filename} completed.")

        except Exception as e:
            print(f"!!! WORKER ERROR processing {filename}: {e}")
            if 'doc_record' in locals() and doc_record:
                doc_record.status = 'failed'
                db.session.commit()
        finally:
            # Clean up the uploaded file from the shared volume
            if os.path.exists(file_path):
                os.remove(file_path)