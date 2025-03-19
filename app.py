import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import chromadb
import pandas as pd
from fastapi import FastAPI, HTTPException
from indexer import handle_new_file, index_folder
import os
from dotenv import load_dotenv
from sheet_creator_tool import GoogleSheetsToolkit
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
# Import the streamlit-chat package
from streamlit_chat import message

# Load environment variables

# Load .env file variables
load_dotenv()

# Set page to full width
st.set_page_config(layout="wide")

# Tiêu đề ứng dụng
st.title("Công cụ tìm kiếm Google Sheets")

# Tab đầu tiên cho tìm kiếm, Tab thứ hai cho indexing, Tab thứ ba cho Sheet Creator Tool
tab1, tab2, tab3 = st.tabs(["Tìm kiếm", "Index từ Google Drive", "Sheet Creator Tool"])


# Khởi tạo Chroma với thư mục lưu trữ
persist_directory = "./chroma_db"
client = chromadb.PersistentClient(path=persist_directory)

from chromadb.utils import embedding_functions
default_ef = embedding_functions.DefaultEmbeddingFunction()

# Create collection with OpenAI embeddings
collection = client.get_or_create_collection(name="spec_collection", embedding_function=default_ef)


with tab1:

    # Tạo ô nhập liệu cho truy vấn tìm kiếm
    query = st.text_input("Nhập truy vấn tìm kiếm:")

    # Xử lý tìm kiếm khi người dùng nhập truy vấn
    if query:
        # Thực hiện tìm kiếm với Chroma
        results = collection.query(
            query_texts=[query],
        )
        
        # Hiển thị số lượng kết quả tìm thấy
        st.write(f"Tìm thấy {len(results)} kết quả:")
        print('results:', results)
        # Hiển thị kết quả
        for index, doc in enumerate(results['documents'][0]):
            # Lấy thông tin từ kết quả

            metaInfo = results['metadatas'][0][index]

            # Tạo link trỏ tới vị trí cụ thể trong Google Sheets
            # Format: https://docs.google.com/spreadsheets/d/{file_id}/edit#gid={sheet_id}&range={col}{row}
            file_id = metaInfo.get("file_id", "")
            sheet_id = metaInfo.get("sheet_id", "")
            col = metaInfo.get("col", "")
            row = metaInfo.get("row", "")
            link = f"https://docs.google.com/spreadsheets/d/{file_id}/edit#gid={sheet_id}&range={col}{row}"
            
            # Hiển thị thông tin trong một container
            with st.container():
                st.markdown(f"**Nội dung:** {doc}")
                st.markdown(f"**File:** {file_id}")
                st.markdown(f"**Sheet:** {sheet_id}")
                st.markdown(f"**Vị trí:** Cột {col}, Hàng {row}")
                st.markdown(f"[Mở trong Google Sheets]({link})")
                st.markdown("---")  # Đường kẻ phân cách giữa các kết quả 

with tab2:
    st.header("Index Google Sheets từ Google Drive")
    
    # Input cho Google Drive folder ID
    folder_id = st.text_input("Nhập ID của thư mục Google Drive chứa các Google Sheets:", 
                            help="ID của thư mục là phần cuối của URL khi bạn mở thư mục trong Google Drive")
    
    # Upload credentials file
    uploaded_file = st.file_uploader("Tải lên file credentials.json để xác thực Google API:", type=['json'])
    
    # Nếu file được tải lên, lưu tạm thời
    temp_credentials_path = None
    if uploaded_file is not None:
        temp_dir = "./temp"
        os.makedirs(temp_dir, exist_ok=True)
        temp_credentials_path = f"{temp_dir}/temp_credentials.json"
        with open(temp_credentials_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success("File credentials đã được tải lên thành công!")
    
    # Button để bắt đầu indexing
    if st.button("Bắt đầu index"):
        if not folder_id:
            st.error("Vui lòng nhập ID của thư mục Google Drive")
        elif temp_credentials_path is None:
            st.error("Vui lòng tải lên file credentials.json")
        else:
            # Thực hiện indexing
            with st.spinner("Đang tiến hành index..."):
                result = index_folder(folder_id, temp_credentials_path)
                
                if result["success"]:
                    st.success(result["message"])
                    
                    # Hiển thị chi tiết
                    details = result.get("details", {})
                    st.write(f"Tổng số files: {details.get('total', 0)}")
                    st.write(f"Files đã xử lý thành công: {details.get('successful', 0)}")
                    st.write(f"Files bị lỗi: {details.get('failed', 0)}")
                    
                    # Hiển thị các lỗi nếu có
                    errors = details.get("errors", [])
                    if errors:
                        st.subheader("Chi tiết lỗi:")
                        for error in errors:
                            st.error(f"File: {error.get('file_name')} - Lỗi: {error.get('error')}")
                else:
                    st.error(result["message"])

with tab3:
    st.header("Sheet Creator Tool")
    
    # Create two columns
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Kết nối với Google Sheets")
        
        # File uploader for Google credentials
        uploaded_creds = st.file_uploader("Tải lên file credentials.json:", type=['json'], key="sheet_creator_creds")
        
        # Input fields for spreadsheet
        spreadsheet_option = st.radio("Chọn hành động:", ["Kết nối với Spreadsheet hiện có", "Tạo Spreadsheet mới"])
        
        if spreadsheet_option == "Kết nối với Spreadsheet hiện có":
            spreadsheet_id = st.text_input("Nhập Spreadsheet ID:")
        else:
            spreadsheet_title = st.text_input("Nhập tiêu đề cho Spreadsheet mới:")
        
        # Execute button
        if st.button("Kết nối"):
            if uploaded_creds is not None:
                # Save uploaded credentials temporarily
                temp_dir = "./temp"
                os.makedirs(temp_dir, exist_ok=True)
                temp_credentials_path = f"{temp_dir}/sheet_creator_creds.json"
                with open(temp_credentials_path, "wb") as f:
                    f.write(uploaded_creds.getbuffer())
                
                # Initialize toolkit
                try:
                    print('temp_credentials_path:', temp_credentials_path)
                    print('cat temp_credentials_path', open(temp_credentials_path).read())
                    toolkit = GoogleSheetsToolkit(credentials_path=temp_credentials_path)
                    
                    if spreadsheet_option == "Kết nối với Spreadsheet hiện có":
                        if spreadsheet_id:
                            spreadsheet = toolkit.connect(spreadsheet_id)
                            st.session_state["toolkit"] = toolkit
                            st.success(f"Đã kết nối thành công với Spreadsheet")
                        else:
                            st.error("Vui lòng nhập Spreadsheet ID")
                    else:
                        if spreadsheet_title:
                            spreadsheet = toolkit.create_spreadsheet(spreadsheet_title)
                            st.session_state["toolkit"] = toolkit
                            st.success(f"Đã tạo và kết nối thành công với Spreadsheet: {spreadsheet_title}")
                        else:
                            st.error("Vui lòng nhập tiêu đề cho Spreadsheet mới")
                except Exception as e:
                    print('error:', e)
                    st.error(f"Lỗi khi kết nối: {str(e)}")
            else:
                st.error("Vui lòng tải lên file credentials.json")
    
    with col2:
        st.subheader("Chat với ReAct Agent")
        
        # Initialize chat history
        if "messages" not in st.session_state:
            st.session_state.messages = []
        
        # Container for chat messages
        chat_container = st.container()
        
        # Check if toolkit is connected
        if "toolkit" in st.session_state:
            # Chat input area
            user_input = st.text_input("Nhập yêu cầu của bạn:", key="user_input")
            
            if st.button("Gửi", key="send_button"):
                if user_input:
                    # Add user message to chat history
                    st.session_state.messages.append({"role": "user", "content": user_input})
                    
                    with st.spinner("Đang xử lý yêu cầu..."):
                        try:
                            # Get tools from toolkit
                            tools = st.session_state["toolkit"].get_tools()
                            
                            # Initialize language model
                            model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
                            
                            # Create ReAct agent
                            graph = create_react_agent(model, tools=tools)
                            
                            # Process request
                            inputs = {"messages": [("user", user_input)]}
                            full_response = ""
                            
                            # Collect stream results
                            for s in graph.stream(inputs, stream_mode="values"):
                                response_message = s["messages"][-1]
                                if not isinstance(response_message, tuple):  # Only show assistant messages
                                    current_response = response_message.content
                                    full_response += current_response + "\n"
                            
                            # Add assistant response to chat history
                            st.session_state.messages.append({"role": "assistant", "content": full_response.strip()})
                            
                        except Exception as e:
                            error_message = f"Lỗi khi thực thi: {str(e)}"
                            st.session_state.messages.append({"role": "assistant", "content": error_message})
            
            # Hiển thị tin nhắn chat sử dụng st.chat_message
            with chat_container:
                # Tạo container với chiều cao cố định
                chat_area = st.container()
                
                if st.session_state.messages:
                    for msg in st.session_state.messages:
                        if msg["role"] == "user":
                            with st.chat_message("user"):
                                st.write(msg["content"])
                        else:
                            with st.chat_message("assistant"):
                                st.write(msg["content"])
                
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Vui lòng kết nối với Google Sheets trước khi sử dụng chat")

# app = FastAPI()

# @app.post("/index-file")
# async def index_new_file(file_info: dict):
#     result = handle_new_file(file_info)
#     if not result["success"]:
#         raise HTTPException(status_code=500, detail=result["message"])
#     return result