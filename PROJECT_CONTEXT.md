# HCMUS Hub — Project Context

## Mục tiêu và công nghệ
Ứng dụng tổng hợp thông báo HCMUS/FIT/CTSV; Python 3.11+, SQLite cục bộ, `httpx`, BeautifulSoup và dashboard HTML/CSS/JavaScript thuần. Repo root: `D:\app\hcmus-hub` (không có thư mục version).

## Cấu trúc cần biết
- `hcmus_hub/`: `cli.py`/`__main__.py` (lệnh), `config.py`/`models.py`, `fetcher.py` (HTTP, delay/retry/robots), `discovery.py`, `parsers.py`, `sync.py`, `store.py` (SQLite/upsert/migration), `enrich.py`, `quality.py`, `repair.py`, `safehtml.py`, `textutils.py`, `web_server.py` (API/dashboard).
- `config/sources.json`: cấu hình nguồn; `dashboard/`: `index.html`, `app.js`, `styles.css`; `tests/`: kiểm thử; `docs/`: ghi chú.
- `data/`: database, report và backup runtime; không đọc/commit/chia sẻ nếu không cần.

## Dữ liệu và API hiện tại
- Các bảng chính: `sources`, `articles`, `article_sources`, `article_revisions`.
- `articles` có cả trường nội dung chung và trạng thái cục bộ `read_at`, `is_favorite`. `article_sources` liên kết một bài với URL/nguồn/danh mục và lưu trạng thái thử tải chi tiết.
- `article_revisions` lưu lịch sử thay đổi *theo bài*, không phải phiên bản tổng thể của database. `articles.id` là ID tự tăng cục bộ, không dùng làm ID chung giữa các máy.
- Upsert dùng fingerprint/hash; giữ nội dung chi tiết tốt hơn nội dung listing mỏng. Migration phải tương thích database cũ.
- API hiện có: `/api/stats`, `/api/articles`, `/api/articles/{id}`, thao tác `/read` và `/favorite`, cùng `/health`. Trong mã đã kiểm tra chưa thấy `/api/version` hay revision toàn database. Dashboard chủ yếu tải dữ liệu khi khởi động/thao tác thủ công; polling chưa được xác nhận là đã triển khai.

## Quyết định và hướng phát triển
- Giữ Python + SQLite; chưa chuyển sang Supabase.
- Bảo toàn database, cấu hình nguồn, trạng thái đã đọc, yêu thích và thiết lập cục bộ. Không xóa/tạo lại database.
- Hướng dự kiến: (1) polling cục bộ phát hiện thay đổi, (2) chia sẻ dữ liệu thông báo qua snapshot + manifest/checksum trên Cloudflare R2, (3) chỉ một tiến trình thu thập nguồn. Đây là kế hoạch, chưa coi là tính năng đã có.
- Không upload nguyên SQLite lên cloud. Snapshot chỉ gồm trường thông báo dùng chung; khi nhập phải ghép bằng định danh ổn định như nguồn + URL/fingerprint, không dựa vào ID tự tăng. Không ghi đè `read_at`, `is_favorite` hoặc thiết lập riêng.

## Quy tắc cho coding agent (ưu tiên giảm quota)
- Đọc file này một lần khi khởi tạo ngữ cảnh. Trong cùng phiên không đọc lại; không quét toàn repo, không nghiên cứu web, không tự lập kế hoạch dài dòng.
- Mỗi nhiệm vụ chỉ mở file được chỉ định và các file trực tiếp liên quan. Giải pháp/kiến trúc do người giao việc cung cấp; agent chủ yếu thực hiện code.
- Diff nhỏ; không refactor, thêm dependency, đổi schema/config hoặc thêm tính năng ngoài yêu cầu.
- Không chạy crawler, `update-hub.ps1`, tác vụ cloud hay thao tác phá hủy dữ liệu nếu chưa được yêu cầu. Không đọc/ghi database thật cho kiểm thử; dùng database tạm trong tests.
- Chỉ chạy test/cú pháp liên quan trực tiếp. Báo ngắn gọn file sửa, kiểm tra thực sự đã chạy và lỗi còn lại; không tuyên bố kiểm thử chưa chạy.

## Lệnh thường dùng
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\start-dashboard.ps1
.\update-hub.ps1  # Đồng bộ thật; chỉ chạy khi được yêu cầu
python -m unittest discover -s tests
```
