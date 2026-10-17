# HCMUS Hub — bộ thu thập thông báo (prototype v0.2)

Đây là nền móng cho website thông tin cá nhân HCMUS Hub: thu thập bài công khai từ nhiều nguồn, chuẩn hóa dữ liệu, phát hiện bài trùng, lưu lịch sử cập nhật và xuất dữ liệu để xây dashboard ở giai đoạn tiếp theo.

**Phạm vi hiện tại:** Giai đoạn A (kiểm kê nguồn + audit RSS/sitemap/API/HTML chạy tại máy người dùng) và Giai đoạn B (bộ thu thập + SQLite + CLI). v0.2 dùng các RSS đã được audit xác nhận, bổ sung parser sitemap cho CTSV và mở rộng audit để đếm URL feed/sitemap. Chưa có giao diện web, chưa có thông báo đẩy và chưa tích hợp portal cần đăng nhập.

## 1. Yêu cầu

- Python 3.11 trở lên (khuyến nghị).
- Internet từ máy chạy chương trình.
- Các package trong `requirements.txt`.

## 2. Cài đặt trên Kali Linux / Ubuntu

Mở terminal trong thư mục `hcmus-hub-v0.1`:

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Nếu Kali báo thiếu `venv`, cài gói hệ thống bằng `sudo apt install python3-venv` rồi tạo môi trường ảo lại.

## 3. Cài đặt trên Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 4. Bước đầu tiên — audit thật các nguồn từ máy của bạn

Báo cáo audit của mèo ngày 15/10/2026 đã xác nhận một số endpoint RSS/API/sitemap hoạt động. Xem `docs/AUDIT_RESULTS_2026-10-15.md`. v0.2 mở rộng audit để đếm mục feed, URL trong sitemap và hiển thị một số URL mẫu. Chạy audit lại khi muốn xác nhận sitemap CTSV có bao nhiêu URL bài viết, vì bản audit cũ chỉ ghi `root=urlset`.

Chỉ thử một nguồn trước:

```bash
python -m hcmus_hub audit --source fit --output data/audit
```

Sau đó thử các nguồn còn lại:

```bash
python -m hcmus_hub audit --output data/audit
```

Đầu ra:

- `data/audit/source-audit.md`: bảng dễ đọc về HTTP status, loại phản hồi và hướng đề xuất.
- `data/audit/source-audit.json`: dữ liệu audit để so sánh / tự động xử lý.

Các URL audit gồm `robots.txt`, sitemap phổ biến, feed RSS/Atom, endpoint WordPress REST API phổ biến và các URL danh mục đã cấu hình. Audit **không** tìm thấy mọi endpoint có thể tồn tại; nó là một đợt dò kỹ thuật có giới hạn.

## 5. Bước thứ hai — đồng bộ thử FIT

Bắt đầu nhẹ để kiểm tra chất lượng dữ liệu:

```bash
python -m hcmus_hub sync --source fit --max-details 3 --max-items-per-listing 10 --delay 1.0
```

Nếu kết quả hợp lý, đồng bộ những nguồn công khai đã bật:

```bash
python -m hcmus_hub sync --max-details 5 --max-items-per-listing 15 --delay 1.0
```

Xem thông báo đã lưu:

```bash
python -m hcmus_hub list --limit 30
python -m hcmus_hub list --unread --limit 30
```

Xuất dữ liệu:

```bash
python -m hcmus_hub export --output data/export.json
```

CSDL mặc định ở `data/hcmus_hub.sqlite3`. Để xem log dễ hơn, lưu toàn bộ terminal vào file hoặc copy phần JSON của lệnh sync khi có lỗi.

## 6. Các lệnh

```text
python -m hcmus_hub audit [--source SOURCE_ID] [--output DIR]
python -m hcmus_hub sync [--source SOURCE_ID] [--max-details N]
python -m hcmus_hub list [--limit N] [--unread]
python -m hcmus_hub export [--output FILE]
```

Có thể lặp `--source` để chọn nhiều nguồn, ví dụ `--source fit --source svnckh`.

## 7. Mô hình dữ liệu

- `sources`: nguồn, trạng thái kiểm tra gần nhất, lỗi gần nhất.
- `articles`: tiêu đề, ngày đăng, chủ đề, trích đoạn, nội dung, tệp đính kèm, dấu vết nội dung, trạng thái đã đọc/yêu thích.
- `article_sources`: lưu URL nguồn; một bài trùng có thể gắn với nhiều website.
- `article_revisions`: bản cũ khi phát hiện nội dung thay đổi qua một URL đã biết.

Bài trùng hiện được phát hiện bằng tiêu đề đã chuẩn hóa + ngày đăng (khi có). Đây là heuristic hữu ích nhưng không hoàn hảo: tiêu đề giống nhau không đảm bảo cùng một bài, và một tiêu đề thay đổi mạnh có thể không tự hợp nhất. Trước khi dùng lâu dài, cần kiểm chứng bằng kết quả thực tế.

## 8. Bảo mật và giới hạn

- Không nhập mật khẩu HCMUS / UStudy vào file cấu hình.
- Không lưu cookie hoặc access token vào repository.
- Prototype chỉ xử lý URL công khai đã khai báo. Không tự động vượt CAPTCHA, MFA, trang đăng nhập hoặc giới hạn truy cập.
- Mặc định có kiểm tra `robots.txt`, delay giữa các request, retry giới hạn và giới hạn kích thước phản hồi. Nếu robots không đọc được, chương trình ghi cảnh báo; người dùng cần xem chính sách nguồn trước khi chạy lâu dài.
- Hiện tại chỉ lưu URL tệp đính kèm, không tải hàng loạt file PDF/DOC/XLS hay danh sách sinh viên.
- Nguồn chưa được kiểm thử thật nên có thể trả về 0 bài hoặc lấy nhầm liên kết. Cần đọc kết quả và tinh chỉnh selectors trước khi tin cậy.

## 9. Tiêu chí nghiệm thu bước B

1. `audit --source fit` trả ra trạng thái HTTP thực tế cho các endpoint.
2. `sync --source fit` lấy tiêu đề + URL + ngày đăng từ các danh mục đã cấu hình.
3. Bài chi tiết được lấy nội dung và URL tệp đính kèm khi có.
4. Chạy sync lần hai không tạo bản ghi lặp cho những URL đã thấy.
5. Bài cùng tiêu đề/ngày từ nguồn khác được liên kết như một nguồn bổ sung.
6. Nếu trang không tải được, lỗi được ghi vào báo cáo thay vì bị bỏ qua âm thầm.

## 10. Lệnh kiểm thử sau audit ngày 15/10/2026

Audit trên máy của mèo đã xác nhận:

- `https://hcmus.edu.vn/rss.xml` là RSS hợp lệ; không dùng `/feed/` ở domain này vì nó trả HTML.
- `https://tuyensinh.hcmus.edu.vn/feed/` là RSS hợp lệ.
- SVNCKH có RSS theo danh mục tại `/danh-muc/thong-bao-tin-tuc/feed/` và `/danh-muc/tin-tuc/feed/`.
- Đoàn trường có `/feed/` và `/news/feed/`.
- CTSV có `sitemap.xml` trả `urlset`, trong khi trang chủ audit được ghi nhận 0 thẻ liên kết; v0.2 thử lấy các URL `/news/` từ sitemap rồi đọc chi tiết.

Bắt đầu bằng audit lại sitemap CTSV:

```bash
python -m hcmus_hub audit --source ctsv --output data/audit
```

Sau đó đồng bộ riêng CTSV để kiểm tra parser sitemap:

```bash
python -m hcmus_hub sync --source ctsv --delay 1.0
python -m hcmus_hub list --limit 30
```

Tiếp theo thử các nguồn có RSS đã xác nhận:

```bash
python -m hcmus_hub sync --source hcmus --source tuyensinh --source svnckh --source doantn --delay 1.0
python -m hcmus_hub list --limit 50
```

Cuối cùng thử FIT bằng HTML:

```bash
python -m hcmus_hub sync --source fit --max-details 3 --max-items-per-listing 10 --delay 1.0
```

Lưu ý: `--max-details` nếu có sẽ ghi đè giới hạn chi tiết cấu hình của tất cả nguồn được chọn. Khi kiểm tra CTSV, nên không truyền `--max-details` để dùng giới hạn riêng của CTSV.

## 11. Giai đoạn kế tiếp

Sau khi kiểm thử B: chỉnh parser theo HTML thực tế, bổ sung nguồn CTSV/Phòng Đào tạo/Đoàn–Hội, xây giao diện web; riêng UStudy/Portal HCMUS cần khảo sát API qua phiên đăng nhập hợp lệ và cấu hình bảo mật riêng.
