import streamlit as st
import pandas as pd
import sqlite3

# PDF Processing
from PyPDF2 import PdfReader

# NEW: Text splitting is now often in langchain_text_splitters 
# or still accessible via community
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

# Vector & Embeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

# LLM & Core
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from tools import save_to_db, send_email_tool, extract_details
import json

import os
from dotenv import load_dotenv

# Load the variables from .env
load_dotenv()

# Get the key safely
api_key = os.getenv("GROQ_API_KEY")


# Initialize session state for booking details
if "booking_data" not in st.session_state:
    st.session_state.booking_data = {
        "name": None, 
        "email": None, 
        "phone": None, 
        "service": None,
        "confirmed": False,
        "date": "TBD",  # <--- Add this
        "time": "TBD"
    }

# Function to format the history for the LLM (Requirement: Last 20-25 messages)
def get_chat_history():
    history = []
    for msg in st.session_state.messages[-20:]:
        if msg["role"] == "user":
            history.append(HumanMessage(content=msg["content"]))
        else:
            history.append(AIMessage(content=msg["content"]))
    return history

st.set_page_config(page_title="AI Booking Assistant", layout="wide")

# Sidebar Navigation [cite: 123]
page = st.sidebar.radio("Navigation", ["Chatbot", "Admin Dashboard"])

if page == "Chatbot":
    st.title("🤖 AI Booking Assistant")
    
    # PDF Upload Section [cite: 14, 80]
    uploaded_files = st.file_uploader("Upload Knowledge Base (PDFs)", type="pdf", accept_multiple_files=True)
    
    # Chat Interface [cite: 79, 82]
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("How can I help?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.booking_data = extract_details(prompt, st.session_state.booking_data)
        # 1. Search the PDF (RAG)
        context = ""
        if "vector_store" in st.session_state:
            docs = st.session_state.vector_store.similarity_search(prompt, k=3)
            context = "\n".join([d.page_content for d in docs])

        # 2. Define the Brain (LLM)
        llm = ChatGroq(api_key=api_key, model_name="llama-3.1-8b-instant")

        # 3. System Instructions
        system_msg = SystemMessage(content=f"""
        You are an AI Booking Assistant. 
        Context from PDFs: {context}

        Current internal data state: {st.session_state.booking_data}

        Rules:
        1. If the user provides a detail (Name, Email, Phone, or Service), update your internal knowledge.
        2. Ask for missing info one by one. 
        3. When you have all 4 details, summarize them and ask for confirmation.
        4. If the user confirms, your response MUST contain the word "CONFIRMED".

        CRITICAL: At the end of EVERY response, you MUST provide the current data in this exact JSON format. 
        If a value is unknown, use null (no quotes). 
        Example: UPDATE_DATA: {{"name": "Raunak", "email": "test@gmail.com", "phone": null, "service": null}}

        UPDATE_DATA: 
        """)

        # 4. Generate Response
        with st.chat_message("assistant"):
            messages = [system_msg] + get_chat_history()
            response = llm.invoke(messages)
            st.markdown(response.content)
            st.session_state.messages.append({"role": "assistant", "content": response.content})

            # Inside your st.chat_input block, after getting 'response' from LLM:
            # --- IMPROVED CATCHER ---
            if "UPDATE_DATA:" in response.content:
                try:
                    # Get the string after the tag
                    parts = response.content.split("UPDATE_DATA:")
                    json_str = parts[-1].strip()
                    
                    import json
                    # Clean the string in case the LLM added extra text after the JSON
                    json_str = json_str.split('}')[0] + '}' 
                    
                    new_data = json.loads(json_str)
                    
                    # Only update if the LLM actually found a real value
                    for key in ["name", "email", "phone", "service", "date", "time"]:
                        val = new_data.get(key)
                        # Ensure we don't overwrite good data with "null" or placeholders
                        if val and val not in ["null", "None", f"extracted_{key}"]:
                            st.session_state.booking_data[key] = val
                            
                except Exception as e:
                    st.error(f"Data Sync Error: {e}") 
            # ------------------------
# Simple logic: If LLM output contains "CONFIRMED", trigger the tools
            if "CONFIRMED" in response.content.upper():
                success, b_id = save_to_db(st.session_state.booking_data)
                if success:
                    email_status = send_email_tool(st.session_state.booking_data['email'], b_id, st.session_state.booking_data)
                    st.success(f"Booking Saved! ID: {b_id} [cite: 145]")
                    if not email_status:
                        st.warning("Booking saved, but email failed to send. [cite: 103]")
                    # Reset booking state for next time
                    st.session_state.booking_data = {k: None for k in st.session_state.booking_data}

elif page == "Admin Dashboard":
    if page == "Admin Dashboard":
        st.title("📊 Admin Dashboard")
        conn = sqlite3.connect('bookings.db')
    
        st.subheader("Customers Table")
        df_cust = pd.read_sql_query("SELECT * FROM customers", conn)
        st.dataframe(df_cust)

        st.subheader("Bookings Table")
        df_book = pd.read_sql_query("SELECT * FROM bookings", conn)
        st.dataframe(df_book)
    
    conn.close()
def process_pdfs(pdf_docs):
    text = ""
    # 1. Extract text from all uploaded PDFs
    for pdf in pdf_docs:
        pdf_reader = PdfReader(pdf)
        for page in pdf_reader.pages:
            text += page.extract_text()
            
    # 2. Split text into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, 
        chunk_overlap=200
    )
    chunks = text_splitter.split_text(text)
    
    # 3. Create Vector Store (using free local embeddings)
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vectorstore = FAISS.from_texts(texts=chunks, embedding=embeddings)
    
    return vectorstore