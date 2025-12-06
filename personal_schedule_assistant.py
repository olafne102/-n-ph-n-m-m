import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import sqlite3
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

DB_NAME = "events.db"

# ================== MODEL + DATABASE ==================

@dataclass
class Event:
    id: Optional[int]
    title: str
    start_time: datetime
    end_time: Optional[datetime]
    location: Optional[str]
    reminder_minutes: int


def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            location TEXT,
            reminder_minutes INTEGER DEFAULT 0,
            reminded INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def insert_event(ev: Event):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO events (title, start_time, end_time, location, reminder_minutes, reminded)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (
            ev.title,
            ev.start_time.isoformat(timespec="seconds"),
            ev.end_time.isoformat(timespec="seconds") if ev.end_time else None,
            ev.location,
            ev.reminder_minutes,
        ),
    )
    conn.commit()
    conn.close()


def get_all_events(keyword: Optional[str] = None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if keyword:
        like = f"%{keyword}%"
        c.execute(
            """
            SELECT id, title, start_time, end_time, location, reminder_minutes, reminded
            FROM events
            WHERE title LIKE ? OR location LIKE ?
            ORDER BY start_time
            """,
            (like, like),
        )
    else:
        c.execute(
            """
            SELECT id, title, start_time, end_time, location, reminder_minutes, reminded
            FROM events
            ORDER BY start_time
            """
        )
    rows = c.fetchall()
    conn.close()

    events = []
    for r in rows:
        id_, title, start_s, end_s, loc, rem, reminded = r
        start_dt = datetime.fromisoformat(start_s)
        end_dt = datetime.fromisoformat(end_s) if end_s else None
        events.append((id_, title, start_dt, end_dt, loc, rem, reminded))
    return events


def delete_event(event_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.commit()
    conn.close()


def update_event_basic(event_id: int, title: str, location: Optional[str], reminder_minutes: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "UPDATE events SET title=?, location=?, reminder_minutes=? WHERE id=?",
        (title, location, reminder_minutes, event_id),
    )
    conn.commit()
    conn.close()


def mark_reminded(event_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE events SET reminded=1 WHERE id=?", (event_id,))
    conn.commit()
    conn.close()


# ================== NLP TIẾNG VIỆT ==================

WEEKDAY_MAP = {
    "thứ hai": 0, "thu hai": 0, "t2": 0,
    "thứ ba": 1, "thu ba": 1, "t3": 1,
    "thứ tư": 2, "thu tu": 2, "t4": 2,
    "thứ năm": 3, "thu nam": 3, "t5": 3,
    "thứ sáu": 4, "thu sau": 4, "t6": 4,
    "thứ bảy": 5, "thu bay": 5, "t7": 5,
    "chủ nhật": 6, "chu nhat": 6, "cn": 6,
}


def normalize_text(s: str) -> str:
    return " ".join(s.lower().strip().split())


def extract_reminder_minutes(text: str, default: int = 15) -> int:
    m = re.search(r"nhắc.*?(trước)?\s*(\d{1,3})\s*(phút|p|phut)", text)
    if m:
        return int(m.group(2))
    return default


def extract_location(text: str) -> Optional[str]:
    m = re.search(r"(ở|tai)\s+([^,]+)", text, flags=re.IGNORECASE)
    if m:
        return m.group(2).strip()
    return None


def extract_title(text: str) -> str:
    m = re.search(
        r"nhắc(?: tôi)?\s*(.*?)(?:\s+lúc|\s+vao|\s+vào|,|$)",
        text,
        flags=re.IGNORECASE,
    )
    if m and m.group(1).strip():
        return m.group(1).strip()
    return text.strip().capitalize()


def parse_time_part(text: str, now: datetime):
    hour = now.hour
    minute = 0

    m = re.search(r"(\d{1,2})[:h ]\s*(\d{1,2})", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
    else:
        m = re.search(r"(\d{1,2})\s*(h|giờ|gio)", text)
        if m:
            hour = int(m.group(1))
            minute = 0

    lower = text.lower()
    if "sáng" in lower or "sang" in lower:
        if hour == 0:
            hour = 8
    elif "chiều" in lower or "chieu" in lower:
        if hour < 12:
            hour += 12
    elif "tối" in lower or "toi" in lower:
        if hour < 12:
            hour += 12

    return hour, minute


def parse_date_part(text: str, now: datetime):
    text_norm = normalize_text(text)

    if "hôm nay" in text_norm or "hom nay" in text_norm:
        return now.date()

    if any(
        w in text_norm
        for w in [
            "ngày mai", "ngay mai",
            "sáng mai", "sang mai",
            "chiều mai", "chieu mai",
            "tối mai", "toi mai",
        ]
    ):
        return (now + timedelta(days=1)).date()

    if "cuối tuần" in text_norm or "cuoi tuan" in text_norm:
        days_ahead = (5 - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return (now + timedelta(days=days_ahead)).date()

    for key, wd in WEEKDAY_MAP.items():
        if key in text_norm:
            days_ahead = (wd - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (now + timedelta(days=days_ahead)).date()

    return now.date()


def parse_vi_sentence(text: str, now: Optional[datetime] = None):
    if now is None:
        now = datetime.now()

    raw = text
    text_norm = normalize_text(text)

    title = extract_title(raw)
    location = extract_location(raw)
    reminder_minutes = extract_reminder_minutes(text_norm)
    date = parse_date_part(text_norm, now)
    hour, minute = parse_time_part(text_norm, now)

    start_dt = datetime.combine(date, datetime.min.time()).replace(
        hour=hour, minute=minute, second=0
    )

    return {
        "event": title,
        "start_time": start_dt.isoformat(timespec="seconds"),
        "end_time": None,
        "location": location,
        "reminder_minutes": reminder_minutes,
    }


# ================== GIAO DIỆN PASTEL HỒNG ==================

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Personal Schedule Assistant - NLP Tiếng Việt")
        self.root.geometry("1080x620")
        self.root.minsize(960, 560)

        # Màu pastel hồng + font dễ thương
        self.bg_main = "#ffeef5"     # nền ngoài
        self.bg_card = "#ffffff"     # nền khung
        self.primary = "#f472b6"     # hồng đậm (nút)
        self.primary_dark = "#ec4899"
        self.text_dark = "#4a2833"

        # Font “dễ thương” – nếu máy không có sẽ tự fallback
        self.font_main = ("Comic Sans MS", 11)
        self.font_small = ("Comic Sans MS", 10)
        self.font_header = ("Comic Sans MS", 20, "bold")
        self.font_section = ("Comic Sans MS", 12, "bold")

        self.root.configure(bg=self.bg_main)

        self._setup_style()
        self._build_layout()
        self.refresh_events()

        # Thread nhắc nhở
        t = threading.Thread(target=self.reminder_loop, daemon=True)
        t.start()

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Card.TFrame",
            background=self.bg_card,
            relief="flat",
        )
        style.configure(
            "Top.TFrame",
            background=self.bg_main,
        )
        style.configure(
            "Primary.TButton",
            font=("Comic Sans MS", 11, "bold"),
            padding=8,
            focuscolor=self.primary,
        )
        style.map(
            "Primary.TButton",
            foreground=[("!disabled", "#ffffff")],
            background=[("!disabled", self.primary), ("pressed", self.primary_dark)],
        )

        style.configure(
            "TButton",
            font=self.font_main,
            padding=6,
            background=self.bg_card,
        )
        style.configure("TLabel", background=self.bg_card, font=self.font_main)
        style.configure(
            "Header.TLabel",
            background=self.bg_main,
            font=self.font_header,
            foreground=self.text_dark,
        )
        style.configure(
            "Section.TLabel",
            background=self.bg_card,
            font=self.font_section,
            foreground=self.text_dark,
        )

        style.configure(
            "Treeview",
            rowheight=30,
            font=self.font_small,
        )
        style.configure(
            "Treeview.Heading",
            font=("Comic Sans MS", 11, "bold"),
            background="#fecdd3",
        )

    def _build_layout(self):
        # ======= HEADER =======
        top = ttk.Frame(self.root, style="Top.TFrame")
        top.pack(fill="x", padx=24, pady=(16, 8))

        title_lbl = ttk.Label(
            top,
            text="✨ Trợ lý lịch trình cá nhân ✨",
            style="Header.TLabel",
        )
        title_lbl.pack(side="left")

        subtitle = ttk.Label(
            top,
            text="NLP tiếng Việt • Nhắc nhở cực xinh",
            background=self.bg_main,
            font=self.font_small,
            foreground="#9f1239",
        )
        subtitle.pack(side="left", padx=16)

        # ======= MAIN WRAPPER =======
        main_wrapper = ttk.Frame(self.root, style="Top.TFrame")
        main_wrapper.pack(fill="both", expand=True, padx=24, pady=(0, 18))

        left_card = ttk.Frame(main_wrapper, style="Card.TFrame")
        right_card = ttk.Frame(main_wrapper, style="Card.TFrame")

        left_card.pack(side="left", fill="y", padx=(0, 14), pady=4, ipadx=12, ipady=12)
        right_card.pack(side="left", fill="both", expand=True, pady=4, ipadx=12, ipady=12)

        # ======= LEFT: INPUT & CONTROL =======
        input_label = ttk.Label(
            left_card,
            text="Nhập câu tiếng Việt mô tả sự kiện 💌",
            style="Section.TLabel",
        )
        input_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.input_entry = tk.Text(
            left_card,
            height=6,
            wrap="word",
            font=self.font_main,
            bg="#fff7fb",
            bd=0,
            highlightthickness=1,
            highlightbackground="#f9a8d4",
        )
        self.input_entry.grid(row=1, column=0, columnspan=2, sticky="nsew")

        left_card.rowconfigure(1, weight=1)
        left_card.columnconfigure(0, weight=1)
        left_card.columnconfigure(1, weight=1)

        # Nút chính
        self.add_btn = ttk.Button(
            left_card,
            text="➕  Thêm sự kiện xinh",
            style="Primary.TButton",
            command=self.add_event_from_text,
        )
        self.add_btn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 6))

        # Hàng nút phụ
        self.edit_btn = ttk.Button(
            left_card,
            text="✏️  Sửa sự kiện",
            command=self.edit_selected_event,
        )
        self.edit_btn.grid(row=3, column=0, sticky="ew", pady=3)

        self.delete_btn = ttk.Button(
            left_card,
            text="🗑  Xóa sự kiện",
            command=self.delete_selected_event,
        )
        self.delete_btn.grid(row=3, column=1, sticky="ew", pady=3, padx=(6, 0))

        # Bộ lọc
        filter_label = ttk.Label(
            left_card,
            text="🎀 Chế độ xem",
            style="Section.TLabel",
        )
        filter_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(14, 4))

        filter_row = ttk.Frame(left_card, style="Card.TFrame")
        filter_row.grid(row=5, column=0, columnspan=2, sticky="ew")

        ttk.Label(filter_row, text="Khoảng:", width=8, font=self.font_small).pack(side="left")

        self.view_mode = tk.StringVar(value="all")
        self.filter_combo = ttk.Combobox(
            filter_row,
            textvariable=self.view_mode,
            values=["all", "today", "week", "month"],
            width=9,
            state="readonly",
            font=self.font_small,
        )
        self.filter_combo.pack(side="left", padx=(0, 6))
        self.filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_events())

        ttk.Label(filter_row, text="Từ khóa:", font=self.font_small).pack(side="left")
        self.search_entry = ttk.Entry(filter_row, width=12, font=self.font_small)
        self.search_entry.pack(side="left")
        ttk.Button(
            filter_row,
            text="Lọc",
            command=self.refresh_events,
        ).pack(side="left", padx=(4, 0))

        # Export
        export_label = ttk.Label(
            left_card,
            text="📂 Xuất & sao lưu",
            style="Section.TLabel",
        )
        export_label.grid(row=6, column=0, columnspan=2, sticky="w", pady=(14, 4))

        export_row = ttk.Frame(left_card, style="Card.TFrame")
        export_row.grid(row=7, column=0, columnspan=2, sticky="ew")

        self.export_json_btn = ttk.Button(
            export_row,
            text="💾  Xuất JSON",
            command=self.export_json,
        )
        self.export_json_btn.pack(side="left", fill="x", expand=True)

        self.export_ics_btn = ttk.Button(
            export_row,
            text="📅  Xuất ICS",
            command=self.export_ics,
        )
        self.export_ics_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        hint = ttk.Label(
            left_card,
            text='Ví dụ: "Nhắc tôi họp nhóm lúc 10h sáng mai ở phòng 302, nhắc trước 15 phút"',
            font=self.font_small,
            foreground="#be185d",
        )
        hint.grid(row=8, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # ======= RIGHT: TABLE =======
        header_table = ttk.Label(
            right_card, text="Danh sách sự kiện xinh xắn 📋", style="Section.TLabel"
        )
        header_table.pack(anchor="w", pady=(0, 6))

        tree_frame = ttk.Frame(right_card, style="Card.TFrame")
        tree_frame.pack(fill="both", expand=True)

        columns = ("id", "title", "start", "location", "reminder")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("id", text="ID")
        self.tree.heading("title", text="Tên sự kiện")
        self.tree.heading("start", text="Bắt đầu")
        self.tree.heading("location", text="Địa điểm")
        self.tree.heading("reminder", text="Nhắc trước (phút)")

        self.tree.column("id", width=50, anchor="center")
        self.tree.column("title", width=280)
        self.tree.column("start", width=160, anchor="center")
        self.tree.column("location", width=160)
        self.tree.column("reminder", width=140, anchor="center")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree.bind("<Delete>", self.delete_selected_event)

    # ---------- CRUD / UI ----------

    def add_event_from_text(self):
        text = self.input_entry.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning(
                "Thiếu dữ liệu",
                "Vui lòng nhập câu mô tả sự kiện bằng tiếng Việt nhé 💗",
            )
            return

        data = parse_vi_sentence(text)
        start_dt = datetime.fromisoformat(data["start_time"])

        ev = Event(
            id=None,
            title=data["event"],
            start_time=start_dt,
            end_time=None,
            location=data["location"],
            reminder_minutes=data["reminder_minutes"],
        )
        insert_event(ev)
        self.input_entry.delete("1.0", "end")
        self.refresh_events()

        messagebox.showinfo(
            "Thêm thành công 🎉",
            f"Đã thêm sự kiện:\n- {ev.title}\n"
            f"- Thời gian: {ev.start_time.strftime('%Y-%m-%d %H:%M')}\n"
            f"- Địa điểm: {ev.location or '-'}\n"
            f"- Nhắc trước: {ev.reminder_minutes} phút",
        )

    def _filter_events_by_mode(self, events):
        mode = self.view_mode.get()
        if mode == "all":
            return events

        today = datetime.now().date()
        result = []

        start_week = today - timedelta(days=today.weekday())
        end_week = start_week + timedelta(days=6)

        for ev in events:
            id_, title, start_dt, end_dt, loc, rem, reminded = ev
            d = start_dt.date()
            if mode == "today" and d == today:
                result.append(ev)
            elif mode == "week" and start_week <= d <= end_week:
                result.append(ev)
            elif mode == "month" and (d.year == today.year and d.month == today.month):
                result.append(ev)

        return result

    def refresh_events(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        keyword = self.search_entry.get().strip()
        events = get_all_events(keyword if keyword else None)
        events = self._filter_events_by_mode(events)

        for ev in events:
            id_, title, start_dt, end_dt, loc, rem, reminded = ev
            self.tree.insert(
                "",
                "end",
                values=(
                    id_,
                    title,
                    start_dt.strftime("%Y-%m-%d %H:%M"),
                    loc or "",
                    rem,
                ),
            )

    def _get_selected_event_id(self) -> Optional[int]:
        sel = self.tree.selection()
        if not sel:
            return None
        item_id = sel[0]
        values = self.tree.item(item_id, "values")
        return int(values[0])

    def delete_selected_event(self, event=None):
        ev_id = self._get_selected_event_id()
        if not ev_id:
            messagebox.showinfo("Xóa", "Hãy chọn một sự kiện trong bảng nhé 💕")
            return

        if messagebox.askyesno("Xác nhận", "Bạn chắc chắn muốn xóa sự kiện này chứ?"):
            delete_event(ev_id)
            self.refresh_events()

    def edit_selected_event(self):
        ev_id = self._get_selected_event_id()
        if not ev_id:
            messagebox.showinfo("Sửa", "Hãy chọn một sự kiện để sửa nè 💗")
            return

        events = get_all_events()
        current = None
        for ev in events:
            if ev[0] == ev_id:
                current = ev
                break

        if current is None:
            return

        id_, title, start_dt, end_dt, loc, rem, reminded = current

        new_title = simpledialog.askstring(
            "Sửa tên sự kiện", "Tên sự kiện:", initialvalue=title
        )
        if new_title is None or not new_title.strip():
            return

        new_loc = simpledialog.askstring(
            "Sửa địa điểm", "Địa điểm:", initialvalue=loc or ""
        )
        if new_loc is None:
            new_loc = ""

        new_rem_str = simpledialog.askstring(
            "Sửa nhắc trước (phút)",
            "Nhắc trước (phút):",
            initialvalue=str(rem),
        )
        try:
            new_rem = int(new_rem_str)
        except (TypeError, ValueError):
            new_rem = rem

        update_event_basic(ev_id, new_title.strip(), new_loc.strip(), new_rem)
        self.refresh_events()

    # ---------- NHẮC NHỞ ----------

    def reminder_loop(self):
        while True:
            now = datetime.now()
            events = get_all_events()

            for id_, title, start_dt, end_dt, loc, rem, reminded in events:
                if reminded:
                    continue
                remind_time = start_dt - timedelta(minutes=rem or 0)
                if remind_time <= now <= start_dt:
                    msg = (
                        f"Sắp đến sự kiện: {title}\n"
                        f"Thời gian: {start_dt.strftime('%Y-%m-%d %H:%M')}\n"
                        f"Địa điểm: {loc or '-'}"
                    )
                    self.root.after(
                        0, lambda m=msg, eid=id_: self.show_reminder(m, eid)
                    )

            time.sleep(60)

    def show_reminder(self, message, event_id):
        messagebox.showinfo("Nhắc nhở dễ thương 💖", message)
        mark_reminded(event_id)

    # ---------- EXPORT ----------

    def export_json(self):
        import json

        events = get_all_events()
        data = []
        for id_, title, start_dt, end_dt, loc, rem, reminded in events:
            data.append(
                {
                    "id": id_,
                    "title": title,
                    "start_time": start_dt.isoformat(timespec="seconds"),
                    "end_time": end_dt.isoformat(timespec="seconds")
                    if end_dt
                    else None,
                    "location": loc,
                    "reminder_minutes": rem,
                }
            )

        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")]
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        messagebox.showinfo("Xuất JSON", f"Đã lưu vào:\n{path}")

    def export_ics(self):
        events = get_all_events()
        if not events:
            messagebox.showinfo("Xuất ICS", "Chưa có sự kiện nào để xuất cả 💌")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".ics", filetypes=[("iCalendar", "*.ics")]
        )
        if not path:
            return

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//PersonalScheduleAssistant//VI",
        ]

        for id_, title, start_dt, end_dt, loc, rem, reminded in events:
            dtstart = start_dt.strftime("%Y%m%dT%H%M%S")
            dtend = (end_dt or (start_dt + timedelta(hours=1))).strftime(
                "%Y%m%dT%H%M%S"
            )
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{id_}@local",
                    f"SUMMARY:{title}",
                    f"DTSTART:{dtstart}",
                    f"DTEND:{dtend}",
                    f"LOCATION:{loc or ''}",
                    "END:VEVENT",
                ]
            )

        lines.append("END:VCALENDAR")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        messagebox.showinfo("Xuất ICS", f"Đã lưu vào:\n{path}")


# ================== MAIN ==================

def main():
    init_db()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
