import os
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings

os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

def create_vector_store(dialogues, embeddings):
    try:
        text_splitter = CharacterTextSplitter(chunk_size=200, chunk_overlap=20)
        texts = text_splitter.split_text("\n".join(dialogues))
        
        # embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        vectorstore = Chroma.from_texts(texts, embeddings, persist_directory="./chroma_db")
        print('----------数据库已记录完成------------')
        return vectorstore
    except Exception as e:
        print(f'数据库初始化出错:{e}')

def start_retrieval(retriever, query):
    retrieved_docs = retriever.invoke(query)
    context = "\n---\n".join([doc.page_content for doc in retrieved_docs])
    return(context)


def init_db(url, key):
    try:
        embeddings = OpenAIEmbeddings(
            model="BAAI/bge-m3",
            openai_api_base=url,
            openai_api_key=key,
            chunk_size=64,
        )
        if os.path.exists("./chroma_db"):
            print('发现向量数据库')
            # embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            vectorstore = Chroma(
                embedding_function=embeddings,  
                persist_directory="./chroma_db"
            )
        else:
            print('未发现向量数据库，尝试初始化...')
            dialog = []
            with open('./txt.list', 'r', encoding='utf-8') as file:
                for l in file.readlines():
                    dialog.append(l)
            print(f"对话记录共计 {len(dialog)} 行。")
            vectorstore = create_vector_store(dialog, embeddings)

        retriever = vectorstore.as_retriever(search_kwargs={"k": 10})
        print('rag设置完成。')
        return retriever
    except Exception as e:
        print(e)
        return '<<ERROR>>'
