from langchain_core.documents import Document
from pathlib import Path
from dotenv import load_dotenv
import os
from langchain_unstructured import UnstructuredLoader 
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

load_dotenv()

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small"
)

llm  = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0, 
    max_retries=2,    
)

dir_path = Path("agent") /  "rag" 
md_path = dir_path / "resort_policies.md"

persist_dir = dir_path / "chroma"
collection_name = "policy"

sqlite_file = persist_dir / "chroma.sqlite3"

split_on = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    # ("###", "Header 3")
]

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

    summary_prompt = ChatPromptTemplate.from_template("Write a concise, 1-sentence summary of this section to serve as background context: \n\n{text}")
    summary_chain = summary_prompt | llm

    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=split_on,
        strip_headers=False
    )
    raw_chunks = header_splitter.split_text(md_path.read_text(encoding="utf-8"))                                                                                                      
    valid_chunks = []

    for doc in raw_chunks:
        content = doc.page_content.strip()
        if len(content) < 30 and not any(c.isalnum() for c in content.splitlines()[-1:]):                                                                                             
            continue   

        # 3. Create a breadcrumb path from metadata headers                                                                                                                           
        headers = [doc.metadata[h] for _, h in split_on if h in doc.metadata]                                                                                                         
        breadcrumb = " > ".join(headers) if headers else "General"

        # 4. Generate summary                                                                                                                                                         
        summary_resp = summary_chain.invoke({"text": content})                                                                                                                        
        summary = summary_resp.content if hasattr(summary_resp, "content") else str(summary_resp)     

        # Attach clean metadata                                                                                                                                                       
        doc.metadata["source"] = md_path.name                                                                                                                                         
        doc.metadata["section_path"] = breadcrumb                                                                                                                                     
        doc.metadata["summary"] = summary   

        # Format page content with rich context for vector search
        doc.page_content = f"Section: {breadcrumb}\nSummary: {summary}\n\n{content}"
        valid_chunks.append(doc)
    

    try:
        vectorstore = Chroma.from_documents(
            documents=valid_chunks,
            embedding=embeddings,
            persist_directory=str(persist_dir),
            collection_name=collection_name
        )
        print("Created ChromaDB vector store!")
    except Exception as e:
        print(f"ERROR: {e}")
        raise
