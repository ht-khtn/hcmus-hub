# HCMUS Hub

HCMUS Hub là dự án cá nhân nhằm tổng hợp và theo dõi thông báo công khai từ nhiều nguồn liên quan đến Trường Đại học Khoa học Tự nhiên, ĐHQG-HCM. Dự án thu thập và chuẩn hóa dữ liệu, phát hiện bài trùng, lưu lịch sử thay đổi và cung cấp dashboard web chạy cục bộ.

> **Trạng thái:** alpha. Các chức năng và cấu trúc dữ liệu vẫn có thể thay đổi; hãy sao lưu dữ liệu trước khi nâng cấp hoặc chuyển sang bản đóng gói.

## Tải xuống (bản alpha)

**Windows — HCMUS Hub v0.9.0-alpha:** [Tải HCMUS-Hub-Setup.exe](https://github.com/ht-khtn/hcmus-hub/releases/download/v0.9.0-alpha/HCMUS-Hub-Setup.exe)

> Đây là bản alpha dùng thử; một số chức năng có thể chưa ổn định. Hãy sao lưu dữ liệu trước khi cài đặt hoặc nâng cấp.

Xem thêm [ghi chú phát hành v0.9.0-alpha](https://github.com/ht-khtn/hcmus-hub/releases/tag/v0.9.0-alpha).

## Tính năng

- Thu thập thông báo từ các nguồn công khai đã cấu hình, sử dụng RSS/Atom, sitemap hoặc HTML tùy từng nguồn.
- Kiểm tra nguồn và hỗ trợ audit endpoint để xem HTTP status, loại phản hồi và một số URL mẫu.
- Lưu dữ liệu trong SQLite; liên kết các URL nguồn trỏ tới cùng một bài và lưu revision khi phát hiện nội dung thay đổi.
- Đồng bộ tăng dần để hạn chế tải lại chi tiết bài đã biết.
- Dashboard web cục bộ để xem, lọc và tìm thông báo; quản lý trạng thái đã đọc/yêu thích.
- Kiểm tra website chạy nền, có thống kê bài mới, nội dung cập nhật, liên kết trùng và các mục không thay đổi.
- Hỗ trợ xuất/nhập snapshot và đồng bộ dữ liệu dùng chung thông qua Cloudflare Worker và R2 khi được cấu hình.
- Có script khởi chạy trên Windows và cấu hình đóng gói bằng PyInstaller + Inno Setup.

## Yêu cầu

- Python 3.11 trở lên được khuyến nghị cho môi trường phát triển.
- Kết nối Internet để audit/đồng bộ các website và sử dụng chức năng chia sẻ dữ liệu.
- Các package được khai báo trong `requirements.txt`.
- Đối với việc tạo bộ cài Windows: PyInstaller và Inno Setup có `ISCC.exe`.

## Chạy trên Windows

Mở PowerShell tại thư mục repository.

### 1. Tạo môi trường Python

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Nếu PowerShell chặn việc kích hoạt môi trường ảo, có thể dùng `python -m pip ...` với đường dẫn Python trong môi trường `.venv`, hoặc điều chỉnh Execution Policy theo chính sách máy đang sử dụng.

### 2. Khởi chạy dashboard

Khuyến nghị dùng file khởi chạy tại thư mục gốc repository:

```powershell
.\Open-HCMUS-Hub.bat
```

Launcher gọi script PowerShell hiện có, chờ dashboard sẵn sàng rồi mở trình duyệt tới:

`http://127.0.0.1:8787/`

Giữ cửa sổ terminal chạy server trong thời gian sử dụng. Khi muốn dừng server, chuyển tới cửa sổ đó và nhấn `Ctrl+C` nếu được hỗ trợ bởi tiến trình đang chạy.

> Nếu chưa có `Open-HCMUS-Hub.bat` trong bản checkout, xem `hcmus-hub.ps1` và `start-dashboard.ps1` để khởi chạy theo cấu hình của repository hiện tại.

## Đóng gói bộ cài Windows

Bản đóng gói sử dụng PyInstaller ở chế độ `onedir` và Inno Setup để tạo một file bộ cài.

### Yêu cầu trên máy build

1. Cài Python 3.11 trở lên.
2. Cài dependencies của dự án và PyInstaller:

   ```powershell
   python -m pip install -r requirements.txt
   python -m pip install pyinstaller
   ```

3. Cài [Inno Setup](https://jrsoftware.org/isdl.php). Script build tìm `ISCC.exe` trong `PATH` và các vị trí cài đặt phổ biến, bao gồm thư mục cài đặt theo user.

### Tạo bộ cài

Chạy từ thư mục gốc repository:

```powershell
.\packaging\build_windows.ps1
```

Nếu build hoàn tất thành công, file bộ cài dự kiến nằm tại:

```text
dist\installer\HCMUS-Hub-Setup.exe
```

Script sử dụng các thư mục build sinh tự động `build\windows` và `dist\windows`; các thư mục này có thể bị xóa và tạo lại trong quá trình build. Không lưu dữ liệu cá nhân trong đó.

**Lưu ý:** việc có cấu hình đóng gói trong repository không có nghĩa bộ cài đã được kiểm thử trên mọi máy Windows. Trước khi phát hành bản mới, hãy cài thử bộ cài và xác nhận dashboard khởi động được, database được giữ nguyên và cấu hình đồng bộ không bị lộ.

### Vị trí lưu dữ liệu của bản cài

Theo cấu hình đóng gói hiện tại, dữ liệu của ứng dụng cài đặt được lưu ngoài thư mục chương trình để không bị xóa khi cập nhật/gỡ ứng dụng:

- SQLite: `%LOCALAPPDATA%\HCMUS Hub\data\hcmus_hub.sqlite3`
- Cấu hình tùy chọn: `%LOCALAPPDATA%\HCMUS Hub\.env`

Khi đường dẫn database đích chưa tồn tại, launcher có thể sao chép database từ `data\hcmus_hub.sqlite3` của bản phát triển để hỗ trợ chuyển đổi lần đầu. Không tự xóa hoặc ghi đè database cũ. Hãy sao lưu database trước khi cài đặt hoặc chuyển đổi.

## Audit nguồn thông tin

Audit giúp kiểm tra các endpoint công khai được cấu hình; đây là phép dò có giới hạn, không bảo đảm tìm thấy mọi API hoặc feed của website.

Audit một nguồn:

```powershell
python -m hcmus_hub audit --source fit --output data/audit
```

Audit các nguồn đã cấu hình:

```powershell
python -m hcmus_hub audit --output data/audit
```

Đầu ra thường gồm:

- `data/audit/source-audit.md`: báo cáo dễ đọc.
- `data/audit/source-audit.json`: dữ liệu audit để so sánh hoặc xử lý tiếp.

Xem thêm kết quả audit đã lưu tại `docs/AUDIT_RESULTS_2026-10-15.md`, nếu file này có trong checkout hiện tại. Nên audit lại trước khi dựa vào trạng thái nguồn cũ vì cấu trúc website có thể thay đổi.

## Đồng bộ dữ liệu

Thử đồng bộ một nguồn với giới hạn nhỏ:

```powershell
python -m hcmus_hub sync --source fit --max-details 3 --max-items-per-listing 10 --delay 1.0
```

Đồng bộ nhiều nguồn công khai đã cấu hình:

```powershell
python -m hcmus_hub sync --max-details 5 --max-items-per-listing 15 --delay 1.0
```

Nếu bỏ `--max-details`, chương trình sẽ dùng giới hạn được cấu hình theo từng nguồn. Tham số này, khi được truyền, có thể ghi đè giới hạn của tất cả nguồn được chọn.

Xem danh sách thông báo và xuất dữ liệu:

```powershell
python -m hcmus_hub list --limit 30
python -m hcmus_hub list --unread --limit 30
python -m hcmus_hub export --output data/export.json
```

Các lệnh CLI chính:

```text
python -m hcmus_hub audit [--source SOURCE_ID] [--output DIR]
python -m hcmus_hub sync [--source SOURCE_ID] [--max-details N]
python -m hcmus_hub list [--limit N] [--unread]
python -m hcmus_hub export [--output FILE]
```

Có thể lặp `--source` để chọn nhiều nguồn, ví dụ `--source fit --source svnckh`. Các tùy chọn có thể khác theo phiên bản; dùng `python -m hcmus_hub --help` để xem trợ giúp của checkout đang sử dụng.

## Đồng bộ snapshot dùng chung (tùy chọn)

HCMUS Hub có cơ chế xuất bản, tải và nhập snapshot dùng chung thông qua Cloudflare Worker và R2. Đây là chức năng tùy chọn; việc chạy dashboard cục bộ không đồng nghĩa đã cấu hình dịch vụ cloud.

- Worker cần được triển khai và cấu hình đúng binding R2.
- Token ghi dữ liệu phải được đặt trong biến môi trường/`.env` phù hợp, không được commit lên Git.
- Dùng `.env.example` làm mẫu cấu hình nếu có; tự điền giá trị riêng trong `.env` của máy mình.
- Chỉ bật tự động publish khi đã cấu hình endpoint và token chính xác. Thiết lập `HUB_AUTO_PUBLISH=1` để bật tính năng này nếu bản đang dùng hỗ trợ biến đó.
- Không đưa token, `.env` thật, database cá nhân hoặc snapshot nội bộ vào GitHub Release.

Các lệnh chia sẻ dữ liệu có thể được xem trong trợ giúp CLI của phiên bản hiện tại. Khi thay đổi cấu hình cloud, hãy thử pull trước và sao lưu SQLite trước khi publish để tránh ghi đè nhầm dữ liệu.

## Mô hình dữ liệu

- `sources`: cấu hình nguồn, trạng thái kiểm tra và lỗi gần nhất.
- `articles`: tiêu đề, ngày đăng, chủ đề, trích đoạn/nội dung, tệp đính kèm và trạng thái của bài.
- `article_sources`: ánh xạ một bài tới một hoặc nhiều URL nguồn.
- `article_revisions`: lưu các phiên bản nội dung cũ khi phát hiện thay đổi.

Việc phát hiện trùng sử dụng heuristic dựa trên thông tin bài đã chuẩn hóa, chẳng hạn tiêu đề và ngày đăng khi có. Đây không phải cơ chế hoàn hảo: hai bài khác nhau vẫn có thể bị xem là trùng, hoặc cùng một bài có thể không được hợp nhất nếu tiêu đề thay đổi nhiều.

## Bảo mật và giới hạn

- Chỉ thu thập các URL công khai đã được cấu hình.
- Không nhập mật khẩu HCMUS/UStudy vào file cấu hình; không lưu cookie hoặc access token trong repository.
- Không tự động vượt CAPTCHA, MFA, trang đăng nhập hoặc biện pháp giới hạn truy cập.
- Tôn trọng chính sách truy cập của từng website. Nếu `robots.txt` không đọc được, cần xem cảnh báo và tự đánh giá chính sách nguồn trước khi chạy lâu dài.
- Chương trình có thể giới hạn tốc độ request, retry và kích thước phản hồi theo cấu hình hiện tại; không nên tăng tải đột ngột lên nguồn.
- Tệp đính kèm có thể chỉ được lưu dưới dạng URL, không có nghĩa nội dung file đã được tải về.
- Một số website có thể thay đổi HTML/feed hoặc chặn request; kết quả đồng bộ cần được kiểm tra thực tế.
- Không công khai `.env`, token Worker, database chứa trạng thái cá nhân hoặc file log có thông tin nhạy cảm.

## Gợi ý kiểm tra nguồn

Các endpoint đã được xác nhận trong đợt audit ngày 15/10/2026 có thể thay đổi theo thời gian. Nếu báo cáo audit vẫn còn trong repository, xem `docs/AUDIT_RESULTS_2026-10-15.md` để biết bối cảnh lịch sử; nên chạy audit lại trước khi chẩn đoán lỗi nguồn.

Ví dụ kiểm tra riêng CTSV:

```powershell
python -m hcmus_hub audit --source ctsv --output data/audit
python -m hcmus_hub sync --source ctsv --delay 1.0
python -m hcmus_hub list --limit 30
```

Ví dụ đồng bộ các nguồn đã cấu hình:

```powershell
python -m hcmus_hub sync --source hcmus --source tuyensinh --source svnckh --source doantn --delay 1.0
python -m hcmus_hub list --limit 50
```

Kiểm tra một nguồn trước với giới hạn thấp là cách tốt để rà soát parser trước khi tăng số lượng bài chi tiết.

## Phát triển và báo lỗi

Khi gặp lỗi:

1. Ghi lại lệnh đã chạy, thời điểm và thông báo lỗi liên quan.
2. Kiểm tra báo cáo audit hoặc log website-check.
3. Chia sẻ log đã loại bỏ token, cookie, thông tin cá nhân và đường dẫn riêng tư nếu cần hỗ trợ.
4. Sao lưu SQLite trước khi thử thay đổi cấu hình đồng bộ hoặc nhập snapshot.

HCMUS Hub hiện là dự án alpha; tính đúng đắn của parser, logic hợp nhất bài trùng và độ ổn định của đồng bộ cần tiếp tục được xác minh bằng dữ liệu thực tế.
