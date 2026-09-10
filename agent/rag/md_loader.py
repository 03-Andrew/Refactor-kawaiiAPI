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


md_path = Path("agent/rag/resort_policies.md")

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
persist_dir = "./agent/rag/chroma"
collection_name = "policy"

try:
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_dir,
        collection_name=collection_name
    )

    print("Created ChromaDB vector store!")

except Exception as e:
    print(f"ERROR: {e}")
    raise
