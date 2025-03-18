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
                st.error(f"Lỗi khi kết nối: {str(e)}")
        else:
            st.error("Vui lòng tải lên file credentials.json")
    
    # Check if toolkit is connected
    if "toolkit" in st.session_state:
        st.subheader("ReAct Agent")
        
        # Input for user query
        user_query = st.text_area("Nhập yêu cầu của bạn:", height=100)
        
        if st.button("Thực thi"):
            if user_query:
                with st.spinner("Đang xử lý yêu cầu..."):
                    try:
                        # Get tools from toolkit
                        tools = st.session_state["toolkit"].get_tools()
                        
                        # Initialize language model
                        model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
                        
                        # Create ReAct agent
                        graph = create_react_agent(model, tools=tools)
                        
                        # Execute agent
                        result_container = st.empty()
                        
                        # Process stream
                        inputs = {"messages": [("user", user_query)]}
                        output = []
                        
                        # Collect and display stream results
                        for s in graph.stream(inputs, stream_mode="values"):
                            message = s["messages"][-1]
                            if isinstance(message, tuple):
                                output.append(f"User: {message[1]}")
                            else:
                                output.append(f"AI: {message.content}")
                            result_container.markdown("\n".join(output))
                        
                        st.success("Hoàn thành!")
                    except Exception as e:
                        st.error(f"Lỗi khi thực thi: {str(e)}")
            else:
                st.warning("Vui lòng nhập yêu cầu")