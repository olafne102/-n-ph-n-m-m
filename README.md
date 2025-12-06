# 🌸 Personal Schedule Assistant – Trợ lý lịch trình cá nhân (NLP Tiếng Việt)

Ứng dụng desktop giúp quản lý lịch trình cá nhân bằng **câu tiếng Việt tự nhiên**, với giao diện **hồng pastel dễ thương**, lưu trữ cục bộ bằng **SQLite** và hỗ trợ **nhắc nhở tự động**.

Người dùng có thể gõ các câu như:

> “Nhắc tôi họp nhóm lúc 10h sáng mai ở phòng 302, nhắc trước 15 phút”

Ứng dụng sẽ tự động trích xuất:
- **Tên sự kiện** (event)
- **Thời gian bắt đầu** (start_time)
- **Địa điểm** (location)
- **Thời gian nhắc trước** (reminder_minutes)

và lưu lại trong hệ thống, đồng thời nhắc nhở khi đến giờ.

---

## ✨ Tính năng chính

- 🧠 **NLP tiếng Việt (rule-based)**  
  - Hiểu các cụm thời gian cơ bản:
    - `10h`, `10 giờ`, `10:30`, `10 h 30`, …
    - `sáng`, `chiều`, `tối`
    - `hôm nay`, `ngày mai`, `cuối tuần`, `thứ hai`, …  
  - Tự động trích xuất:
    - **Tên sự kiện**
    - **Thời gian bắt đầu**
    - **Địa điểm** (sau các từ khóa `ở`, `tại`)
    - **Nhắc trước** (ví dụ: “nhắc trước 15 phút”, “nhắc trước 30p”)

- 📅 **Quản lý lịch trình**
  - Thêm sự kiện từ câu tiếng Việt tự nhiên
  - Xem danh sách sự kiện theo bảng
  - Sửa / xóa sự kiện
  - Tìm kiếm theo từ khóa (theo tên / địa điểm)
  - (Tuỳ phiên bản) Lọc theo: *tất cả / hôm nay / tuần / tháng*

- ⏰ **Nhắc nhở tự động**
  - Luồng (thread) chạy ngầm kiểm tra sự kiện **mỗi 60 giây**
  - Tính toán `remind_time = start_time - reminder_minutes`
  - Khi đến khoảng thời gian nhắc → hiện **popup thông báo**

- 💾 **Lưu trữ cục bộ**
  - Sử dụng **SQLite** (`events.db`)
  - Không cần cài thêm server, chạy hoàn toàn **offline**

- 📤 **Xuất dữ liệu**
  - Xuất danh sách sự kiện ra **JSON**
  - Xuất ra file **ICS (iCalendar)** có thể import vào Google Calendar, Outlook, v.v.

- 🎀 **Giao diện pastel hồng dễ thương**
  - Giao diện dùng **Tkinter + ttk.Style**
  - Tông màu **hồng pastel**, font chữ **Comic Sans MS** (hoặc tương tự)
  - Bố cục:
    - Panel trái: nhập câu, các nút Thêm/Sửa/Xóa, tìm kiếm, export
    - Panel phải: bảng Treeview hiển thị sự kiện

---

## 🛠 Công nghệ sử dụng

- **Ngôn ngữ:** Python 3.10+
- **Giao diện:** Tkinter (ttk, style)
- **Cơ sở dữ liệu:** SQLite3
- **Xử lý NLP tiếng Việt:** Regex + rule-based (không cần thư viện nặng)
- **Khác:** threading, datetime, json

---

## 📁 Cấu trúc thư mục (gợi ý)

Tuỳ cách bạn tách file, repo có thể tổ chức như sau:

```bash
.
├── README.md
├── requirements.txt        # (tuỳ chọn, có thể để trống hoặc chỉ cần python>=3.10)
├── events.db               # sẽ được tạo tự động sau khi chạy app lần đầu
└── src/
    ├── main.py             # Giao diện Tkinter + logic nhắc nhở
    ├── nlp_vi.py           # Xử lý câu tiếng Việt (NLP rule-based)
    └── db.py               # Hàm thao tác SQLite (CRUD sự kiện)
