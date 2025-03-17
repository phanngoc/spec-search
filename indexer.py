import gspread
from oauth2client.service_account import ServiceAccountCredentials
import chromadb
from langchain.text_splitter import RecursiveCharacterTextSplitter  # Changed import to concrete class
from typing import List, Dict, Tuple
from chromadb.utils import embedding_functions

# Khởi tạo Chroma với thư mục lưu trữ
persist_directory = "./chroma_db"
clientDB = chromadb.PersistentClient(path=persist_directory)
default_ef = embedding_functions.DefaultEmbeddingFunction()
collection = clientDB.get_or_create_collection(name="spec_collection", embedding_function=default_ef)
                                             
def index_spreadsheet(file_info: Dict, collection, text_splitter, clientGS) -> None:
    """Index một Google Spreadsheet vào Chroma DB"""
    file_id = file_info['id']
    file_name = file_info['name']
    
    # Mở spreadsheet
    spreadsheet = clientGS.open_by_key(file_id)
    print('index_spreadsheet:', file_id, file_name, spreadsheet)
    sheets = spreadsheet.worksheets()
    
    # Index từng sheet
    for sheet in sheets:
        tab_name = sheet.title
        sheet_id = sheet.id
        print('index_spreadsheet:', tab_name, sheet_id)
        data = sheet.get_all_values()
        print('index_spreadsheet:', data)
        for row_index, row in enumerate(data):
            for col_index, cell_value in enumerate(row):
                if not cell_value:
                    continue
                
                if not isinstance(cell_value, str):
                    cell_value = str(cell_value)
                
                sentences = text_splitter.split_text(cell_value)
                
                # Convert column index to letter (e.g., 0->A, 1->B)
                col_letter = chr(65 + col_index) if col_index < 26 else chr(64 + col_index // 26) + chr(65 + col_index % 26)
                
                # Add documents to the ChromaDB collection
                for i, sentence in enumerate(sentences):
                    collection.add(
                        documents=[sentence],
                        metadatas=[{
                            "file_name": file_name,
                            "file_id": file_id,
                            "tab_name": tab_name,
                            "sheet_id": str(sheet_id),
                            "col": col_letter,
                            "row": str(row_index + 2)  # +2 because of header row and 0-indexing
                        }],
                        ids=[f"{file_id}_{sheet_id}_{col_letter}{row_index+2}_{i}"]
                    )

def handle_new_file(file_info: Dict) -> Dict:
    """Xử lý file mới được thêm vào folder"""
    # Create a concrete text splitter instance
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
    )
    
    try:
        index_spreadsheet(file_info, collection, text_splitter)
        return {
            "success": True,
            "message": f"Đã index thành công file {file_info['name']}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Lỗi khi index file {file_info['name']}: {str(e)}"
        }

def get_spreadsheets_in_folder(folder_id: str, credentials_path: str) -> Tuple[List[Dict], gspread.Client]:
    """Lấy tất cả các Google Spreadsheets trong một folder"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
    client = gspread.authorize(creds)
    
    # Lấy danh sách tất cả các file
    file_list = client.list_spreadsheet_files(folder_id=folder_id)
    print('file_list:', file_list)

    return file_list, client

def index_folder(folder_id: str, credentials_path: str) -> Dict:
    """Index tất cả các Google Spreadsheets trong một folder"""
    # Create a concrete text splitter instance
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
    )
    
    try:
        # Lấy tất cả các spreadsheets trong folder
        spreadsheets, clientGs = get_spreadsheets_in_folder(folder_id, credentials_path)
        
        results = {
            "total": len(spreadsheets),
            "successful": 0,
            "failed": 0,
            "errors": []
        }
        
        # Index từng spreadsheet
        for spreadsheet in spreadsheets:
            try:
                index_spreadsheet(spreadsheet, collection, text_splitter, clientGs)
                results["successful"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "file_name": spreadsheet.get("name", "Unknown"),
                    "error": str(e)
                })
        
        return {
            "success": True,
            "message": f"Đã index {results['successful']}/{results['total']} files thành công",
            "details": results
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Lỗi khi index folder: {str(e)}"
        }