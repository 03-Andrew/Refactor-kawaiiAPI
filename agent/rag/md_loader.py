from langchain_core.documents import Document
from pathlib import Path
from dotenv import load_dotenv
import os
from langchain_unstructured import UnstructuredLoader 
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

load_dotenv()

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small"
)

dir_path = Path("agent") /  "rag" 
md_path = dir_path / "resort_policies.md"

persist_dir = dir_path / "chroma"
collection_name = "policy"

sqlite_file = persist_dir / "chroma.sqlite3"

if persist_dir.exists() and sqlite_file.exists():
    print("Loading existing ChromaDB vector store...")
    vectorstore = Chroma(
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
        collection_name=collection_name,
    )
else:
    print("ChromaDB vector store not found. Creating and indexing...")
    try:
        text = md_path.read_text(encoding="utf-8")
        documents = [
            Document(
                page_content=text,
                metadata={"source": md_path.name}
            )
        ]
        print(f"MARKDOWN HAS BEEN LOADED: {len(text)} characters")
    except Exception as e:
        print(f"ERROR LOADING MARKDOWN: {e}")
        raise

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )
    chunks = text_splitter.split_documents(documents)

    try:
        vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=str(persist_dir),
            collection_name=collection_name
        )
        print("Created ChromaDB vector store!")
    except Exception as e:
        print(f"ERROR: {e}")
        raise
