# HCMUS Hub — báo cáo chạy toàn bộ

- Bắt đầu: `2026-10-16T23:03:19+07:00`
- Kết thúc: `2026-10-16T23:11:37+07:00`
- CSDL: `D:\app\hcmus-hub\v0.6\data\hcmus_hub.sqlite3`
- Sao lưu trước khi chạy: `D:\app\hcmus-hub\v0.6\data\runs\run-20261016-230319\backups\hcmus_hub.pre-run-all-20261016-230319-962904.sqlite3`

## Sửa dữ liệu cũ

- Trạng thái: **applied**
- Liên kết dự kiến gỡ: 49
- Bài dự kiến xóa: 22
- Liên kết đã gỡ: 49
- Bài đã xóa: 22
- Sao lưu riêng của thao tác repair: `D:\app\hcmus-hub\v0.6\data\hcmus_hub.before-repair-20261016-230556-136442.sqlite3`
- Ghi chú: Đã áp dụng sửa chữa và tạo bản sao lưu. Các liên kết đa danh mục hợp lệ được giữ lại.

## Đồng bộ các nguồn công khai bật mặc định

| Nguồn | Listing OK | Phát hiện | Tải chi tiết | Mới | Cập nhật | Lỗi |
|---|---:|---:|---:|---:|---:|---:|
| Khoa Công nghệ Thông tin (FIT) | 16 | 153 | 30/30 | 39 | 0 | 0 |
| Phòng Công tác Sinh viên | 1 | 50 | 30/30 | 13 | 0 | 0 |
| Website chính HCMUS | 1 | 49 | 30/30 | 26 | 10 | 0 |
| Phòng Đào tạo HCMUS | 1 | 38 | 30/30 | 30 | 0 | 0 |
| Cổng thông tin Tuyển sinh HCMUS | 1 | 40 | 30/30 | 10 | 0 | 0 |
| Nghiên cứu khoa học sinh viên (SVNCKH) | 2 | 16 | 16/16 | 0 | 0 | 0 |
| Đoàn trường - Hội Sinh viên HCMUS | 3 | 17 | 17/17 | 0 | 0 | 0 |

## Kết quả cuối

- Số bài trong CSDL: 497
- Chưa đọc: 497
- Nguồn đã đăng ký: 7
- File dữ liệu JSON: `D:\app\hcmus-hub\v0.6\data\runs\run-20261016-230319\hcmus-hub-export.json`
- Audit chi tiết: `D:\app\hcmus-hub\v0.6\data\runs\run-20261016-230319\audit\source-audit.md`
- Kế hoạch repair: `D:\app\hcmus-hub\v0.6\data\runs\run-20261016-230319\repair-plan.json`

## Ghi chú

Báo cáo này ghi nhận kết quả chạy tại máy đã thực hiện lệnh. Endpoint có HTTP 200 không tự nó chứng minh mọi bài đã được trích xuất chính xác; hãy xem cột lỗi và file audit nếu một nguồn trả 0 bài hoặc có lỗi.
