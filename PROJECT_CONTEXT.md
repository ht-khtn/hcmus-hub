# HCMUS Hub — Project Context

## Công nghệ

- Python 3.11+.
- SQLite cục bộ cho dữ liệu thông báo và trạng thái cá nhân.
- `httpx` cho HTTP async; `beautifulsoup4` cho HTML; thư viện chuẩn cho CLI, XML, SQLite và HTTP server.
- Dashboard HTML/CSS/JavaScript chạy qua web server local, không dùng framework frontend.

## Cấu trúc quan trọng

- `hcmus_hub/`: package chính.
  - `cli.py`, `__main__.py`: các lệnh CLI và entry point.
  - `config.py`, `models.py`: đọc cấu hình và mô hình dữ liệu.
  - `fetcher.py`: HTTP client, retry, delay, giới hạn phản hồi và kiểm tra `robots.txt`.
  - `discovery.py`: audit endpoint và phân loại nguồn.
  - `parsers.py`, `sync.py`: parse HTML/RSS/sitemap và đồng bộ bài viết.
  - `store.py`: schema/migration và thao tác SQLite.
  - `enrich.py`, `quality.py`, `repair.py`: làm giàu dữ liệu cũ, báo cáo chất lượng và repair an toàn.
  - `safehtml.py`, `textutils.py`: lọc HTML và chuẩn hóa văn bản/hash.
  - `web_server.py`: API/dashboard local.
- `config/sources.json`: nguồn, danh mục, parser mode, giới hạn trang/chi tiết.
- `dashboard/`: giao diện local (`index.html`, `app.js`, `styles.css`).
- `tests/`: test parser, sync, store, CLI và dashboard.
- `docs/`: ghi chú thay đổi giao diện/nội dung đã chốt.
- `data/`: SQLite, báo cáo, bản export và backup runtime; không dùng làm tài liệu kiến trúc.

## Luồng dữ liệu

1. `config/sources.json` được đọc thành `SourceConfig`/`ListingConfig`.
2. `sync` dùng `PoliteFetcher` tải các listing đã cấu hình, tự nhận diện hoặc ép parser HTML/RSS/sitemap.
3. Parser tạo `Article`; bài chi tiết được tải giới hạn theo nguồn và làm giàu nội dung khi phù hợp.
4. `Store` đăng ký nguồn, upsert bài theo fingerprint/hash, liên kết nhiều nguồn/danh mục và lưu revision khi nội dung thực sự đổi.
5. Dashboard local đọc dữ liệu qua `web_server.py`; trạng thái đã đọc và yêu thích được ghi lại trong SQLite.
6. `audit`, `repair`, `quality`, `export` tạo báo cáo hoặc thao tác được kiểm soát; `run-all` kết hợp các bước và sao lưu SQLite trước khi chạy.

## Module chính và quy ước

- Giữ tương thích dữ liệu hiện có; migration dùng `CREATE TABLE IF NOT EXISTS`/`ALTER TABLE` có kiểm tra cột, không tái tạo database.
- Dùng type hints, dataclass và `pathlib`; lỗi fetch/parse được ghi vào báo cáo hoặc trạng thái nguồn thay vì bỏ qua im lặng.
- Fetch công khai ở mức thấp: tôn trọng `robots.txt`, delay theo host, retry giới hạn và giới hạn kích thước phản hồi; không vượt xác thực/CAPTCHA.
- Nội dung HTML nguồn phải qua sanitizer trước khi dashboard hiển thị.
- Thay đổi dữ liệu nguy hiểm phải có backup hoặc chế độ dry-run; ưu tiên bảo toàn bản ghi có trạng thái người dùng.
- Kiểm thử bằng `python -m unittest discover -s tests` hoặc test liên quan trực tiếp; không chạy crawler thật nếu chưa được yêu cầu.

## Cách chạy/kiểm thử

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python -m hcmus_hub list --limit 30
python -m hcmus_hub audit --source fit --output data\audit
python -m hcmus_hub sync --source fit --max-details 3
python -m hcmus_hub quality --output-dir data\quality
python -m hcmus_hub web --db data\hcmus_hub.sqlite3

python -m unittest discover -s tests
```

## Các quyết định kiến trúc đã chốt

- Dự án hiện dùng **Python + SQLite**.
- Phải bảo toàn database, trạng thái đã đọc, yêu thích và cấu hình nguồn; không xóa/tái tạo/ghi đè các dữ liệu này khi chưa có yêu cầu rõ ràng.
- Hướng thiết kế đang cân nhắc: **SQLite cục bộ + dữ liệu thông báo dùng chung qua Cloudflare R2 + polling để phát hiện phiên bản mới**.
- Chưa tự triển khai hướng SQLite/R2/polling nói trên khi chưa có yêu cầu cụ thể.
