from typing import Dict, Any, Optional, Type, List
from langchain.tools import BaseTool, Tool, StructuredTool, tool
from pydantic import BaseModel, Field, validator
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent


class GoogleSheetsToolkit:
    def __init__(self, credentials_path: str = "path/to/credentials.json"):
        """Khởi tạo bộ công cụ Google Sheets với đường dẫn đến tệp credentials."""
        self.credentials_path = credentials_path
        self.client = None
        self.spreadsheet = None
        
    def connect(self, spreadsheet_id: str = None):
        """Kết nối với Google Sheets API và mở spreadsheet theo ID."""
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_path, scope)
        self.client = gspread.authorize(creds)
        
        if spreadsheet_id:
            self.spreadsheet = self.client.open_by_key(spreadsheet_id)
            return self.spreadsheet
        return None
    
    def create_spreadsheet(self, title: str):
        """Tạo spreadsheet mới với tiêu đề cho trước."""
        if not self.client:
            self.connect()
        self.spreadsheet = self.client.create(title)
        return self.spreadsheet
    
    def get_spreedsheet(self):
        """Trả về spreadsheet hiện tại."""
        return self.spreadsheet

toolkit = GoogleSheetsToolkit(
    credentials_path="./secret/glass-core-386002-9a86ff813d4a.json")
toolkit.connect("1g9lniOcnHfB-v8FMKZWYocavO9TLm-mr6zM6JY2XLMk")
# toolkit.create_spreadsheet("Dữ liệu mẫu LangGraph")

spreadsheet = toolkit.get_spreedsheet()

# Thêm các tool mới để đọc và ghi dữ liệu trong Google Sheets
@tool
def read_cell(sheet_name: str, cell: str) -> str:
    """
    Đọc giá trị từ ô chỉ định theo ký hiệu A1 và tên sheet.
    
    Args:
        sheet_name: Tên sheet cần đọc dữ liệu
        cell: Vị trí ô cần đọc theo ký hiệu A1 (ví dụ: "A1")
    
    Returns:
        Giá trị trong ô theo vị trí chỉ định
    """
    return spreadsheet.worksheet(sheet_name).acell(cell).value

@tool
def write_cell(sheet_name: str, cell: str, value: str) -> str:
    """
    Ghi giá trị vào ô chỉ định theo ký hiệu A1 và tên sheet.
    
    Args:
        sheet_name: Tên sheet cần ghi dữ liệu
        cell: Vị trí ô cần ghi theo ký hiệu A1 (ví dụ: "A1") 
        value: Giá trị cần ghi vào ô
    
    Returns:
        Xác nhận đã ghi thành công
    """
    spreadsheet.worksheet(sheet_name).update_acell(cell, value)
    return f"Đã ghi thành công giá trị '{value}' vào ô {cell} trong sheet {sheet_name}"

@tool
def read_values(sheet_name: str, range_str: str) -> List[List[str]]:
    """
    Đọc các giá trị từ phạm vi chỉ định theo ký hiệu A1 và tên sheet.
    
    Args:
        sheet_name: Tên sheet cần đọc dữ liệu
        range_str: Phạm vi cần đọc theo ký hiệu A1 (ví dụ: "A1:C5")
    
    Returns:
        Danh sách các giá trị trong phạm vi
    """
    return spreadsheet.worksheet(sheet_name).get(range_str)

@tool
def write_values(sheet_name: str, range_str: str, values: List[List[str]]) -> str:
    """
    Ghi các giá trị vào phạm vi chỉ định theo ký hiệu A1 và tên sheet.
    
    Args:
        sheet_name: Tên sheet cần ghi dữ liệu
        range_str: Phạm vi cần ghi theo ký hiệu A1 (ví dụ: "A1:C5")
        values: Danh sách các giá trị cần ghi (là list của list)
    
    Returns:
        Xác nhận đã ghi thành công
    """
    spreadsheet.worksheet(sheet_name).update(range_str, values)
    return f"Đã ghi thành công dữ liệu vào phạm vi {range_str} trong sheet {sheet_name}"

@tool
def suggest_data_type(data: str) -> str:
    """
    Gợi ý kiểu dữ liệu dựa trên giá trị cung cấp.
    
    Args:
        data: Chuỗi dữ liệu cần xác định kiểu
        
    Returns:
        Kiểu dữ liệu được gợi ý
    """
    if data.isdigit():
        return "Số nguyên"
    try:
        float(data)
        return "Số thực"
    except ValueError:
        pass
    
    if data.lower() in ['true', 'false', 'đúng', 'sai', 'có', 'không']:
        return "Boolean"
    
    # Kiểm tra định dạng ngày tháng đơn giản
    date_patterns = [
        r'\d{1,2}/\d{1,2}/\d{2,4}',  # dd/mm/yyyy
        r'\d{4}-\d{1,2}-\d{1,2}',    # yyyy-mm-dd
    ]
    for pattern in date_patterns:
        if re.match(pattern, data):
            return "Ngày tháng"
    
    return "Chuỗi"


# Sử dụng LangGraph ReAct agent
def example_with_react_agent():
    # Tạo và kết nối Google Sheets toolkit
    try:
        # Lấy các tool
        tools = [read_cell, write_cell, read_values, write_values, suggest_data_type]

        # Khởi tạo mô hình ngôn ngữ (LLM)
        model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        
        # Tạo ReAct agent
        graph = create_react_agent(model, tools=tools)
        
        print("Agent đã được khởi tạo thành công. Bắt đầu thử nghiệm...")
        
        # Hàm hiển thị kết quả từ stream
        def print_stream(stream):
            for s in stream:
                message = s["messages"][-1]
                if isinstance(message, tuple):
                    print(message)
                else:
                    print(f"AI: {message.content}")

        # Tạo bảng với 3 cột và thêm 5 sản phẩm
        print("\n== Yêu cầu 1: Tạo bảng với 3 cột và thêm sản phẩm ==")
        inputs = {"messages": [("user", "Tạo bảng với 3 cột: Sản phẩm, Số lượng, Giá, range từ A1 tới C6 và thêm 5 sản phẩm vào bảng")]}
        print_stream(graph.stream(inputs, stream_mode="values"))
        
        # Đọc dữ liệu và tính tổng
        print("\n== Yêu cầu 2: Đọc dữ liệu và tính tổng ==")
        inputs = {"messages": [("user", "Đọc dữ liệu ở ô A1 đến C6 và tính tổng số lượng của tất cả sản phẩm")]}
        print_stream(graph.stream(inputs, stream_mode="values"))
        
        # Tạo bảng doanh thu theo tháng
        print("\n== Yêu cầu 3: Tạo bảng doanh thu ==")
        inputs = {"messages": [("user", "Tạo một bảng dữ liệu mới với các cột: Tháng, Doanh thu, Chi phí, Lợi nhuận. Thêm dữ liệu cho các tháng từ T1-T6/2023")]}
        print_stream(graph.stream(inputs, stream_mode="values"))
        
        return "Quá trình thực thi hoàn tất!"
    
    except Exception as e:
        print(f"Lỗi khi chạy ReAct agent: {str(e)}")
        return f"Lỗi: {str(e)}"

if __name__ == "__main__":
    example_with_react_agent() 