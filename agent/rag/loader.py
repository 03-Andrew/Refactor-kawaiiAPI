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

pdf_path = "agent/rag/resort_policies.pdf"


if not os.path.exists(pdf_path):
    raise FileNotFoundError(f"PDF NOT FOUND: {pdf_path}")


pdf_loader = UnstructuredLoader(pdf_path)

try:
    pages = pdf_loader.load()
    for doc in pages:
        doc.metadata.pop("coordinates", None)
    print(f"PDF HAS BEEN LOADED AND HAS {len(pages)} elements")
except Exception as e:
    print(f"ERROR LOADING PDF: {e}")
    raise

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size = 1000,
    chunk_overlap = 200
)

pages_split = text_splitter.split_documents(pages)

# persist_dir = r"C:\Users\Lenovo\Documents\Andrew\Refactor_proj\Refactor-kawaiiAPI\agent\rag"
persist_dir = "./agent/rag/chroma"
collection_name = "policy"


if not os.path.exists(persist_dir):
    os.makedirs(persist_dir)

try:
    vectorstore = Chroma.from_documents(
        documents=pages_split,
        embedding=embeddings,
        persist_directory=persist_dir,
        collection_name=collection_name
    )
    print(f"Created ChromaDB vector store!")
except Exception as e:
    print(f"ERROR: {e}")
    raise