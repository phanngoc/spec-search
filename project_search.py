import gspread
from oauth2client.service_account import ServiceAccountCredentials
from langchain import Chroma
from langchain.text_splitter import TextSplitter

# Xác thực và kết nối với Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('path/to/credentials.json', scope)
client = gspread.authorize(creds)

# Lấy danh sách tất cả các file trong folder
folder_id = "ID_của_folder"  # Thay thế bằng ID folder thực tế
file_list = client.list_spreadsheet_files()
spreadsheets = [file for file in file_list if file.get('parents') and folder_id in file.get('parents')]

# In danh sách các file
for file in spreadsheets:
    print(f"Tên file: {file['name']}, ID: {file['id']}")
# Khởi tạo Chroma với thư mục lưu trữ
persist_directory = "./chroma_db"
chroma = Chroma(persist_directory=persist_directory)

# Khởi tạo TextSplitter
text_splitter = TextSplitter()

# Lặp qua từng file spreadsheet
for file in spreadsheets:
    # Lấy thông tin file
    file_id = file['id']
    file_name = file['name']
    
    # Mở spreadsheet
    spreadsheet = client.open_by_key(file_id)
    
    # Lấy danh sách tất cả các sheet
    sheets = spreadsheet.worksheets()
    
    # Lặp qua từng sheet
    for sheet in sheets:
        # Lấy thông tin sheet
        tab_name = sheet.title
        sheet_id = sheet.id  # Lấy sheet_id để tạo link
        
        # Lấy tất cả dữ liệu từ sheet
        data = sheet.get_all_records()
        
        # Lưu trữ từng dòng dữ liệu với thông tin chi tiết
        for row_index, row in enumerate(data):
            for col_index, (col_name, cell_value) in enumerate(row.items()):
                # Bỏ qua các ô trống
                if not cell_value:
                    continue
                    
                # Chuyển đổi cell_value thành chuỗi nếu không phải
                if not isinstance(cell_value, str):
                    cell_value = str(cell_value)
                
                # Tách câu từ giá trị ô
                sentences = text_splitter.split(cell_value)
                
                # Lưu trữ từng câu với thông tin chi tiết
                for sentence in sentences:
                    chroma.add_document({
                        "content": sentence,
                        "file_name": file_name,
                        "file_id": file_id,
                        "tab_name": tab_name,
                        "sheet_id": sheet_id,
                        "col": col_name,
                        "row": row_index + 1  # Hàng bắt đầu từ 1
                    })
