# /server/celery_worker.py (Definitive, Lazy-Loading Version)
import os, pickle, requests, threading
from celery import Celery
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

import chromadb
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from langchain_community.llms import Ollama
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA

# --- Celery and Flask App Setup ---
celery = Celery(__name__, broker='redis://redis:6379/0', backend='redis://redis:6379/0')
flask_app = Flask(__name__)
flask_app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://{os.environ.get('POSTGRES_USER')}:{os.environ.get('POSTGRES_PASSWORD')}@db/{os.environ.get('POSTGRES_DB')}"
flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(flask_app)

# --- Database Model Definition ---
class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False, unique=True)
    source_agent = db.Column(db.String(120), nullable=True)
    category = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, server_default=db.func.now())

# --- AI Engine Singleton (Lazy Loading) ---
ai_components = {}
ai_lock = threading.Lock()

def get_ai_components():
    with ai_lock:
        if "qa_chain" not in ai_components:
            print("--- Worker: Initializing AI Engine for the first time... ---")
            embedding_function = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
            chroma_client = chromadb.HttpClient(host="chroma", port=8000)
            vector_store = Chroma(client=chroma_client, collection_name="corpus_documents", embedding_function=embedding_function)
            llm = Ollama(model="tinyllama", base_url="http://ollama:11434")
            qa_chain = RetrievalQA.from_chain_type(llm, retriever=vector_store.as_retriever(), return_source_documents=True)
            ai_components["vector_store"] = vector_store
            ai_components["qa_chain"] = qa_chain
            print("--- Worker: AI Engine Ready. ---")
    return ai_components

# --- Celery Task Definitions ---
@celery.task
def process_document_task(file_path, filename, agent_name):
    with flask_app.app_context():
        try:
            # Get AI components, which will initialize them on the first run
            components = get_ai_components()
            vector_store = components["vector_store"]
            
            doc_record = Document.query.filter_by(filename=filename).first()
            if not doc_record:
                doc_record = Document(filename=filename, source_agent=agent_name, status='processing')
                db.session.add(doc_record)
                db.session.commit()
            elif doc_record.status == 'completed':
                print(f"SKIPPING: {filename} already processed."); os.remove(file_path); return

            with open(file_path, 'rb') as f: file_content = f.read()
            tika_url = os.environ.get('TIKA_SERVER_URL', 'http://tika:9998/tika')
            response = requests.put(tika_url, data=file_content, headers={"Accept": "text/plain", "Content-Type": "application/octet-stream"})
            response.raise_for_status()
            text_content = response.text.strip()
            if not text_content: doc_record.status = 'failed_no_content'; db.session.commit(); return

            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            docs_for_vector_db = text_splitter.create_documents([text_content], metadatas=[{"source_filename": filename}])
            vector_store.add_documents(docs_for_vector_db, ids=[f"{filename}_{i}" for i, _ in enumerate(docs_for_vector_db)])
            
            # You can add your classifier model logic here if needed
            # category = model.predict([text_content])[0]
            # doc_record.category = category
            doc_record.status = 'completed'
            db.session.commit()
            print(f"SUCCESS: Job for {filename} completed.")
        except Exception as e:
            print(f"!!! WORKER ERROR processing {filename}: {e}");
            if 'doc_record' in locals() and doc_record: doc_record.status = 'failed'; db.session.commit()
        finally:
            if os.path.exists(file_path): os.remove(file_path)

@celery.task
def answer_query_task(query):
    try:
        components = get_ai_components()
        result = components["qa_chain"].invoke({"query": query})
        source_filenames = {doc.metadata.get('source_filename', 'Unknown') for doc in result.get('source_documents', [])}
        return {"answer": result.get('result', 'Could not find an answer.'), "sources": list(source_filenames)}
    except Exception as e:
        print(f"!!! QA Chain Error in worker: {e}")
        return {"error": "Failed to process AI query."}