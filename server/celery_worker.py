# /server/celery_worker.py (Definitive, Robust Version)
import os, requests, threading
from app import celery, db, Document  # <<< FIX: Import from the main app

import chromadb
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from langchain_community.llms import Ollama
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA

# --- AI Engine Singleton (Lazy Loading) ---
ai_components = {}
ai_lock = threading.Lock()

def get_ai_components():
    with ai_lock:
        if "qa_chain" not in ai_components:
            print("--- Worker: Initializing AI Engine... ---")
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
def process_document_task(document_id, file_path):
    # <<< FIX: Entire logic updated to be ID-based and transactional >>>
    doc_record = db.session.get(Document, document_id)
    if not doc_record:
        print(f"!!! WORKER ERROR: Document with ID {document_id} not found in DB.")
        return

    try:
        # 1. Update status to 'processing'
        doc_record.status = 'processing'
        db.session.commit()
        
        # 2. Get AI components
        components = get_ai_components()
        vector_store = components["vector_store"]
        
        # 3. Extract text with Tika
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        tika_url = 'http://tika:9998/tika'
        response = requests.put(tika_url, data=file_content, headers={"Accept": "text/plain"})
        response.raise_for_status()
        text_content = response.text.strip()
        
        if not text_content:
            raise ValueError("Tika extracted no text content from the document.")

        # 4. Split text and add to ChromaDB
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs_for_vector_db = text_splitter.create_documents([text_content], metadatas=[{"source_filename": doc_record.filename}])
        vector_store.add_documents(docs_for_vector_db, ids=[f"{doc_record.filename}_{i}" for i, _ in enumerate(docs_for_vector_db)])
        
        # 5. Mark as complete
        doc_record.status = 'completed'
        db.session.commit()
        print(f"SUCCESS: Job for {doc_record.filename} (ID: {document_id}) completed.")

    except Exception as e:
        db.session.rollback() # Rollback any partial changes
        error_message = f"!!! WORKER ERROR processing {doc_record.filename}: {e}"
        print(error_message)
        if 'doc_record' in locals() and doc_record:
            doc_record.status = 'failed'
            db.session.commit()
    finally:
        # Clean up the uploaded file from the shared volume
        if os.path.exists(file_path):
            os.remove(file_path)

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