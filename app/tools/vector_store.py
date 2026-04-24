import os
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from app.core.config import get_settings

settings = get_settings()

class VectorStoreManager:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.persist_directory = f"./db/chroma_{session_id}"
        self.embeddings = OpenAIEmbeddings(openai_api_key=settings.openai_api_key)

    def get_vector_store(self):
        return Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
            collection_name=f"session_{self.session_id}"
        )

    def add_documents(self, chunks: List[str], metadata: Dict[str, Any]):
        """
        Adds chunks to the vector store with metadata to ensure 
        the LLM knows the source and page.
        """
        documents = [
            Document(page_content=chunk, metadata=metadata) 
            for chunk in chunks
        ]
        vector_store = self.get_vector_store()
        vector_store.add_documents(documents)
        return f"Successfully indexed {len(chunks)} chunks."

    def similarity_search(self, query: str, k: int = 5):
        """
        Performs a search. To prevent 'disasters', we return more 
        results (k=5) and include full metadata.
        """
        vector_store = self.get_vector_store()
        results = vector_store.similarity_search(query, k=k)
        
        context = ""
        for doc in results:
            source = doc.metadata.get("filename", "Unknown")
            page = doc.metadata.get("page", "Unknown")
            context += f"\n--- Source: {source} (Page {page}) ---\n"
            context += doc.page_content + "\n"
            
        return context