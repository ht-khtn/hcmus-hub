# HCMUS Hub — báo cáo chạy toàn bộ

- Bắt đầu: `2026-10-17T15:24:51+07:00`
- Kết thúc: `2026-10-17T15:45:06+07:00`
- CSDL: `D:\app\hcmus-hub\v0.8.1\data\hcmus_hub.sqlite3`
- Sao lưu trước khi chạy: `D:\app\hcmus-hub\v0.8.1\data\runs\run-20261017-152451\backups\hcmus_hub.pre-run-all-20261017-152451-958587.sqlite3`

## Sửa dữ liệu cũ

- Trạng thái: **applied**
- Liên kết dự kiến gỡ: 0
- Bài dự kiến xóa: 0
- Liên kết đã gỡ: 0
- Bài đã xóa: 0
- Sao lưu riêng của thao tác repair: `D:\app\hcmus-hub\v0.8.1\data\hcmus_hub.before-repair-20261017-152725-009206.sqlite3`
- Chuẩn hóa HTML entity: 1 bài; 0 liên kết; 1 trường.

- Ghi chú: Đã áp dụng sửa chữa và tạo bản sao lưu. Các liên kết đa danh mục hợp lệ được giữ lại.

## Đồng bộ các nguồn công khai bật mặc định

| Nguồn | Listing OK | Phát hiện | HTTP 200 | Parse/ghi | Có thân bài | Trống sau fetch | Parse lỗi | Mới | Cập nhật | Lỗi |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Khoa Công nghệ Thông tin (FIT) | 16 | 153 | 30 | 30/30 | 30 | 0 | 0 | 0 | 0 | 0 |
| Phòng Công tác Sinh viên | 1 | 436 | 30 | 30/30 | 30 | 0 | 0 | 0 | 0 | 0 |
| Website chính HCMUS | 1 | 49 | 30 | 30/30 | 29 | 1 | 0 | 0 | 0 | 0 |
| Phòng Đào tạo HCMUS | 1 | 38 | 30 | 30/30 | 22 | 8 | 0 | 0 | 0 | 0 |
| Cổng thông tin Tuyển sinh HCMUS | 1 | 40 | 30 | 30/30 | 30 | 0 | 0 | 0 | 0 | 0 |
| Nghiên cứu khoa học sinh viên (SVNCKH) | 2 | 16 | 16 | 16/16 | 13 | 3 | 0 | 0 | 0 | 0 |
| Đoàn trường - Hội Sinh viên HCMUS | 3 | 17 | 17 | 17/17 | 16 | 1 | 0 | 0 | 4 | 0 |

## Kết quả cuối

- Số bài trong CSDL: 820
- Chưa đọc: 306
- Nguồn đã đăng ký: 7
- File dữ liệu JSON: `D:\app\hcmus-hub\v0.8.1\data\runs\run-20261017-152451\hcmus-hub-export.json`
- Audit chi tiết: `D:\app\hcmus-hub\v0.8.1\data\runs\run-20261017-152451\audit\source-audit.md`
- Kế hoạch repair: `D:\app\hcmus-hub\v0.8.1\data\runs\run-20261017-152451\repair-plan.json`
- Báo cáo chất lượng: `D:\app\hcmus-hub\v0.8.1\data\runs\run-20261017-152451\quality\quality-report.md`

## Ghi chú

Báo cáo này ghi nhận kết quả chạy tại máy đã thực hiện lệnh. HTTP fetch thành công không đồng nghĩa thân bài được trích xuất thành công; hãy xem các chỉ số extraction và báo cáo chất lượng.

## Làm giàu dữ liệu cũ

- Ứng viên yếu dữ liệu: 681
- Lượt thử tải chi tiết: 681
- HTTP tải thành công: 681
- Trích xuất được thân bài: 652
- Tải được trang nhưng chưa lấy thân bài: 29

## Chất lượng dữ liệu sau đồng bộ

| Chỉ số | Số bài |
|---|---:|
| Thiếu nội dung đầy đủ | 15 |
| Thiếu cả nội dung lẫn tóm tắt | 2 |
| Chưa có ngày đăng | 5 |
| Ngày chưa xác minh | 0 |
| Tiêu đề có vẻ dựng từ slug | 9 |
| HTML entity còn sót | 33 |
