# Báo cáo audit nguồn HCMUS Hub

- Chạy lúc: `2026-10-17T15:18:17+07:00`
- File cấu hình: `D:\app\hcmus-hub\v0.8.1\config\sources.json`

## Khoa Công nghệ Thông tin (FIT) (`fit`)

- Base URL: https://www.fit.hcmus.edu.vn/
- Hướng đề xuất: **html_parser**

| Loại probe | HTTP | Phân loại | URL | Ghi chú |
|---|---:|---|---|---|
| robots | 404 | not_found | https://www.fit.hcmus.edu.vn/robots.txt | HTTP 404. |
| sitemap | 404 | not_found | https://www.fit.hcmus.edu.vn/sitemap.xml | HTTP 404. |
| sitemap_index | 404 | not_found | https://www.fit.hcmus.edu.vn/sitemap_index.xml | HTTP 404. |
| wordpress_sitemap | 404 | not_found | https://www.fit.hcmus.edu.vn/wp-sitemap.xml | HTTP 404. |
| rss_feed | 404 | not_found | https://www.fit.hcmus.edu.vn/feed/ | HTTP 404. |
| rss_feed | 404 | not_found | https://www.fit.hcmus.edu.vn/news/feed/ | HTTP 404. |
| rss_feed | 404 | not_found | https://www.fit.hcmus.edu.vn/feed | HTTP 404. |
| rss_feed | 404 | not_found | https://www.fit.hcmus.edu.vn/rss.xml | HTTP 404. |
| atom_feed | 404 | not_found | https://www.fit.hcmus.edu.vn/atom.xml | HTTP 404. |
| wordpress_api | 404 | not_found | https://www.fit.hcmus.edu.vn/wp-json/wp/v2/posts?per_page=1 | HTTP 404. |
| listing | 200 | html | https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/thong-bao-chung | HTML; title='Danh sách thông báo - Khoa Công Nghệ Thông Tin - Trường ĐH KHTN, ĐHQG-HCM'; 168 liên kết. |
| listing | 200 | html | https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/thong-tin-hoc-bong | HTML; title='Danh sách thông báo - Khoa Công Nghệ Thông Tin - Trường ĐH KHTN, ĐHQG-HCM'; 139 liên kết. |
| listing | 200 | html | https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/thong-bao-he-chinh-quy | HTML; title='Danh sách thông báo - Khoa Công Nghệ Thông Tin - Trường ĐH KHTN, ĐHQG-HCM'; 149 liên kết. |
| listing | 200 | html | https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/hoat-dong-sinh-vien | HTML; title='Danh sách thông báo - Khoa Công Nghệ Thông Tin - Trường ĐH KHTN, ĐHQG-HCM'; 143 liên kết. |
| listing | 200 | html | https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/thong-bao-he-hoan-chinh | HTML; title='Danh sách thông báo - Khoa Công Nghệ Thông Tin - Trường ĐH KHTN, ĐHQG-HCM'; 137 liên kết. |
| listing | 200 | html | https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/hoi-thao-hoi-nghi | HTML; title='Danh sách thông báo - Khoa Công Nghệ Thông Tin - Trường ĐH KHTN, ĐHQG-HCM'; 166 liên kết. |
| listing | 200 | html | https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/thong-tin-tuyen-dung | HTML; title='Danh sách thông báo - Khoa Công Nghệ Thông Tin - Trường ĐH KHTN, ĐHQG-HCM'; 140 liên kết. |
| listing | 200 | html | https://www.fit.hcmus.edu.vn/beta/tin-tuc/c/tot-nghiep-qui-trinh-thuc-hien | HTML; title='Danh sách thông báo - Khoa Công Nghệ Thông Tin - Trường ĐH KHTN, ĐHQG-HCM'; 149 liên kết. |

## Phòng Công tác Sinh viên (`ctsv`)

- Base URL: https://ctsv.hcmus.edu.vn/
- Hướng đề xuất: **manual_review_or_browser**

| Loại probe | HTTP | Phân loại | URL | Ghi chú |
|---|---:|---|---|---|
| robots | 200 | robots_txt | https://ctsv.hcmus.edu.vn/robots.txt | robots.txt đọc được; 4 dòng Disallow; 1 Sitemap được khai báo. |
| sitemap | 200 | sitemap | https://ctsv.hcmus.edu.vn/sitemap.xml | XML hợp lệ, root=urlset; 463 URL. Ví dụ: https://ctsv.hcmus.edu.vn/; https://ctsv.hcmus.edu.vn/about; https://ctsv.hcmus.edu.vn/info |
| sitemap_index | 404 | not_found | https://ctsv.hcmus.edu.vn/sitemap_index.xml | HTTP 404. |
| wordpress_sitemap | 404 | not_found | https://ctsv.hcmus.edu.vn/wp-sitemap.xml | HTTP 404. |
| rss_feed | 404 | not_found | https://ctsv.hcmus.edu.vn/feed/ | HTTP 404. |
| rss_feed | 404 | not_found | https://ctsv.hcmus.edu.vn/news/feed/ | HTTP 404. |
| rss_feed | 404 | not_found | https://ctsv.hcmus.edu.vn/feed | HTTP 404. |
| rss_feed | 404 | not_found | https://ctsv.hcmus.edu.vn/rss.xml | HTTP 404. |
| atom_feed | 404 | not_found | https://ctsv.hcmus.edu.vn/atom.xml | HTTP 404. |
| wordpress_api | 404 | not_found | https://ctsv.hcmus.edu.vn/wp-json/wp/v2/posts?per_page=1 | HTTP 404. |

## Website chính HCMUS (`hcmus`)

- Base URL: https://hcmus.edu.vn/
- Hướng đề xuất: **rss_atom**

| Loại probe | HTTP | Phân loại | URL | Ghi chú |
|---|---:|---|---|---|
| robots | 200 | robots_txt | https://hcmus.edu.vn/robots.txt | robots.txt đọc được; 4 dòng Disallow; 2 Sitemap được khai báo. |
| sitemap | 200 | sitemap | https://hcmus.edu.vn/sitemap.xml | XML hợp lệ, root=sitemapindex; 14 sitemap con. Ví dụ: https://hcmus.edu.vn/post-sitemap.xml; https://hcmus.edu.vn/post-sitemap2.xml; https://hcmus.edu.vn/post-sitemap3.xml |
| sitemap_index | 200 | sitemap | https://hcmus.edu.vn/sitemap_index.xml | XML hợp lệ, root=sitemapindex; 14 sitemap con. Ví dụ: https://hcmus.edu.vn/post-sitemap.xml; https://hcmus.edu.vn/post-sitemap2.xml; https://hcmus.edu.vn/post-sitemap3.xml |
| wordpress_sitemap | 200 | sitemap | https://hcmus.edu.vn/wp-sitemap.xml | XML hợp lệ, root=sitemapindex; 14 sitemap con. Ví dụ: https://hcmus.edu.vn/post-sitemap.xml; https://hcmus.edu.vn/post-sitemap2.xml; https://hcmus.edu.vn/post-sitemap3.xml |
| rss_feed | 200 | html | https://hcmus.edu.vn/feed/ | HTML; title='University of Science - VNUHCM'; 110 liên kết. Feed khai báo: https://hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Fhcmus.edu.vn%2F&format=xml |
| rss_feed | 200 | html | https://hcmus.edu.vn/news/feed/ | HTML; title='University of Science - VNUHCM'; 110 liên kết. Feed khai báo: https://hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Fhcmus.edu.vn%2F&format=xml |
| rss_feed | 200 | html | https://hcmus.edu.vn/feed | HTML; title='University of Science - VNUHCM'; 110 liên kết. Feed khai báo: https://hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Fhcmus.edu.vn%2F&format=xml |
| rss_feed | 200 | feed | https://hcmus.edu.vn/rss.xml | XML hợp lệ, root=rss; khoảng 50 mục feed. |
| atom_feed | 404 | not_found | https://hcmus.edu.vn/atom.xml | HTTP 404. |
| wordpress_api | 200 | json_api | https://hcmus.edu.vn/wp-json/wp/v2/posts?per_page=1 | JSON có cấu trúc danh sách, 1 phần tử ở phản hồi thử nghiệm. |
| sitemap_from_robots | 200 | feed | https://hcmus.edu.vn/sitemap.rss | XML hợp lệ, root=rss; khoảng 50 mục feed. |

## Phòng Đào tạo HCMUS (`pdt`)

- Base URL: https://hcmus.edu.vn/
- Hướng đề xuất: **rss_atom**

| Loại probe | HTTP | Phân loại | URL | Ghi chú |
|---|---:|---|---|---|
| robots | 200 | robots_txt | https://hcmus.edu.vn/robots.txt | robots.txt đọc được; 4 dòng Disallow; 2 Sitemap được khai báo. |
| sitemap | 200 | sitemap | https://hcmus.edu.vn/sitemap.xml | XML hợp lệ, root=sitemapindex; 14 sitemap con. Ví dụ: https://hcmus.edu.vn/post-sitemap.xml; https://hcmus.edu.vn/post-sitemap2.xml; https://hcmus.edu.vn/post-sitemap3.xml |
| sitemap_index | 200 | sitemap | https://hcmus.edu.vn/sitemap_index.xml | XML hợp lệ, root=sitemapindex; 14 sitemap con. Ví dụ: https://hcmus.edu.vn/post-sitemap.xml; https://hcmus.edu.vn/post-sitemap2.xml; https://hcmus.edu.vn/post-sitemap3.xml |
| wordpress_sitemap | 200 | sitemap | https://hcmus.edu.vn/wp-sitemap.xml | XML hợp lệ, root=sitemapindex; 14 sitemap con. Ví dụ: https://hcmus.edu.vn/post-sitemap.xml; https://hcmus.edu.vn/post-sitemap2.xml; https://hcmus.edu.vn/post-sitemap3.xml |
| rss_feed | 200 | html | https://hcmus.edu.vn/feed/ | HTML; title='University of Science - VNUHCM'; 110 liên kết. Feed khai báo: https://hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Fhcmus.edu.vn%2F&format=xml |
| rss_feed | 200 | html | https://hcmus.edu.vn/news/feed/ | HTML; title='University of Science - VNUHCM'; 110 liên kết. Feed khai báo: https://hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Fhcmus.edu.vn%2F&format=xml |
| rss_feed | 200 | html | https://hcmus.edu.vn/feed | HTML; title='University of Science - VNUHCM'; 110 liên kết. Feed khai báo: https://hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Fhcmus.edu.vn%2F&format=xml |
| rss_feed | 200 | feed | https://hcmus.edu.vn/rss.xml | XML hợp lệ, root=rss; khoảng 50 mục feed. |
| atom_feed | 404 | not_found | https://hcmus.edu.vn/atom.xml | HTTP 404. |
| wordpress_api | 200 | json_api | https://hcmus.edu.vn/wp-json/wp/v2/posts?per_page=1 | JSON có cấu trúc danh sách, 1 phần tử ở phản hồi thử nghiệm. |
| listing | 200 | html | https://hcmus.edu.vn/phong-dao-tao/ | HTML; title='Phòng Đào tạo - Trường Đại học Khoa học tự nhiên, ĐHQG-HCM'; 141 liên kết. Feed khai báo: https://hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Fhcmus.edu.vn%2Fphong-dao-tao%2F&format=xml |
| sitemap_from_robots | 200 | feed | https://hcmus.edu.vn/sitemap.rss | XML hợp lệ, root=rss; khoảng 50 mục feed. |
| alternate_feed | 200 | xml | https://hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Fhcmus.edu.vn%2Fphong-dao-tao%2F&format=xml | XML hợp lệ, root=oembed. |

## Cổng thông tin Tuyển sinh HCMUS (`tuyensinh`)

- Base URL: https://tuyensinh.hcmus.edu.vn/
- Hướng đề xuất: **rss_atom**

| Loại probe | HTTP | Phân loại | URL | Ghi chú |
|---|---:|---|---|---|
| robots | 200 | robots_txt | https://tuyensinh.hcmus.edu.vn/robots.txt | robots.txt đọc được; 1 dòng Disallow; 1 Sitemap được khai báo. |
| sitemap | 200 | html | https://tuyensinh.hcmus.edu.vn/sitemap.xml | HTML; title='Trang chủ - Cổng thông tin tuyển sinh Trường Đại học Khoa học tự nhiên - ĐHQG-HCM'; 151 liên kết. Feed khai báo: https://tuyensinh.hcmus.edu.vn/feed/, https://tuyensinh.hcmus.edu.vn/comments/feed/, https://tuyensinh.hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Ftuyensinh.hcmus.edu.vn%2F&format=xml |
| sitemap_index | 200 | sitemap | https://tuyensinh.hcmus.edu.vn/sitemap_index.xml | XML hợp lệ, root=sitemapindex; 4 sitemap con. Ví dụ: https://tuyensinh.hcmus.edu.vn/post-sitemap.xml; https://tuyensinh.hcmus.edu.vn/page-sitemap.xml; https://tuyensinh.hcmus.edu.vn/blocks-sitemap.xml |
| wordpress_sitemap | 200 | html | https://tuyensinh.hcmus.edu.vn/wp-sitemap.xml | HTML; title='Trang chủ - Cổng thông tin tuyển sinh Trường Đại học Khoa học tự nhiên - ĐHQG-HCM'; 151 liên kết. Feed khai báo: https://tuyensinh.hcmus.edu.vn/feed/, https://tuyensinh.hcmus.edu.vn/comments/feed/, https://tuyensinh.hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Ftuyensinh.hcmus.edu.vn%2F&format=xml |
| rss_feed | 200 | feed | https://tuyensinh.hcmus.edu.vn/feed/ | XML hợp lệ, root=rss; khoảng 40 mục feed. |
| rss_feed | 200 | feed | https://tuyensinh.hcmus.edu.vn/news/feed/ | XML hợp lệ, root=rss; khoảng 0 mục feed. |
| rss_feed | 200 | feed | https://tuyensinh.hcmus.edu.vn/feed | XML hợp lệ, root=rss; khoảng 40 mục feed. |
| rss_feed | 200 | html | https://tuyensinh.hcmus.edu.vn/rss.xml | HTML; title='Trang chủ - Cổng thông tin tuyển sinh Trường Đại học Khoa học tự nhiên - ĐHQG-HCM'; 151 liên kết. Feed khai báo: https://tuyensinh.hcmus.edu.vn/feed/, https://tuyensinh.hcmus.edu.vn/comments/feed/, https://tuyensinh.hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Ftuyensinh.hcmus.edu.vn%2F&format=xml |
| atom_feed | 200 | html | https://tuyensinh.hcmus.edu.vn/atom.xml | HTML; title='Trang chủ - Cổng thông tin tuyển sinh Trường Đại học Khoa học tự nhiên - ĐHQG-HCM'; 151 liên kết. Feed khai báo: https://tuyensinh.hcmus.edu.vn/feed/, https://tuyensinh.hcmus.edu.vn/comments/feed/, https://tuyensinh.hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Ftuyensinh.hcmus.edu.vn%2F&format=xml |
| wordpress_api | 200 | json_api | https://tuyensinh.hcmus.edu.vn/wp-json/wp/v2/posts?per_page=1 | JSON có cấu trúc danh sách, 1 phần tử ở phản hồi thử nghiệm. |

## Nghiên cứu khoa học sinh viên (SVNCKH) (`svnckh`)

- Base URL: https://svnckhcn.hcmus.edu.vn/
- Hướng đề xuất: **rss_atom**

| Loại probe | HTTP | Phân loại | URL | Ghi chú |
|---|---:|---|---|---|
| robots | 200 | robots_txt | https://svnckhcn.hcmus.edu.vn/robots.txt | robots.txt đọc được; 1 dòng Disallow; 1 Sitemap được khai báo. |
| sitemap | 404 | not_found | https://svnckhcn.hcmus.edu.vn/sitemap.xml | HTTP 404. |
| sitemap_index | 404 | not_found | https://svnckhcn.hcmus.edu.vn/sitemap_index.xml | HTTP 404. |
| wordpress_sitemap | 200 | sitemap | https://svnckhcn.hcmus.edu.vn/wp-sitemap.xml | XML hợp lệ, root=sitemapindex; 6 sitemap con. Ví dụ: https://svnckhcn.hcmus.edu.vn/wp-sitemap-posts-post-1.xml; https://svnckhcn.hcmus.edu.vn/wp-sitemap-posts-page-1.xml; https://svnckhcn.hcmus.edu.vn/wp-sitemap-posts-blocks-1.xml |
| rss_feed | 200 | feed | https://svnckhcn.hcmus.edu.vn/feed/ | XML hợp lệ, root=rss; khoảng 10 mục feed. |
| rss_feed | 200 | feed | https://svnckhcn.hcmus.edu.vn/news/feed/ | XML hợp lệ, root=rss; khoảng 0 mục feed. |
| rss_feed | 200 | feed | https://svnckhcn.hcmus.edu.vn/feed | XML hợp lệ, root=rss; khoảng 10 mục feed. |
| rss_feed | 404 | not_found | https://svnckhcn.hcmus.edu.vn/rss.xml | HTTP 404. |
| atom_feed | 404 | not_found | https://svnckhcn.hcmus.edu.vn/atom.xml | HTTP 404. |
| wordpress_api | 200 | json_api | https://svnckhcn.hcmus.edu.vn/wp-json/wp/v2/posts?per_page=1 | JSON có cấu trúc danh sách, 1 phần tử ở phản hồi thử nghiệm. |
| listing | 200 | feed | https://svnckhcn.hcmus.edu.vn/danh-muc/thong-bao-tin-tuc/feed/ | XML hợp lệ, root=rss; khoảng 10 mục feed. |
| listing | 200 | feed | https://svnckhcn.hcmus.edu.vn/danh-muc/tin-tuc/feed/ | XML hợp lệ, root=rss; khoảng 8 mục feed. |

## Đoàn trường - Hội Sinh viên HCMUS (`doantn`)

- Base URL: https://doantn.hcmus.edu.vn/
- Hướng đề xuất: **rss_atom**

| Loại probe | HTTP | Phân loại | URL | Ghi chú |
|---|---:|---|---|---|
| robots | 200 | robots_txt | https://doantn.hcmus.edu.vn/robots.txt | robots.txt đọc được; 1 dòng Disallow; 1 Sitemap được khai báo. |
| sitemap | 200 | sitemap | https://doantn.hcmus.edu.vn/sitemap.xml | XML hợp lệ, root=sitemapindex; 7 sitemap con. Ví dụ: https://doantn.hcmus.edu.vn/wp-sitemap-posts-post-1.xml; https://doantn.hcmus.edu.vn/wp-sitemap-posts-page-1.xml; https://doantn.hcmus.edu.vn/wp-sitemap-posts-blocks-1.xml |
| sitemap_index | 404 | not_found | https://doantn.hcmus.edu.vn/sitemap_index.xml | HTTP 404. |
| wordpress_sitemap | 200 | sitemap | https://doantn.hcmus.edu.vn/wp-sitemap.xml | XML hợp lệ, root=sitemapindex; 7 sitemap con. Ví dụ: https://doantn.hcmus.edu.vn/wp-sitemap-posts-post-1.xml; https://doantn.hcmus.edu.vn/wp-sitemap-posts-page-1.xml; https://doantn.hcmus.edu.vn/wp-sitemap-posts-blocks-1.xml |
| rss_feed | 200 | feed | https://doantn.hcmus.edu.vn/feed/ | XML hợp lệ, root=rss; khoảng 10 mục feed. |
| rss_feed | 200 | feed | https://doantn.hcmus.edu.vn/news/feed/ | XML hợp lệ, root=rss; khoảng 0 mục feed. |
| rss_feed | 200 | feed | https://doantn.hcmus.edu.vn/feed | XML hợp lệ, root=rss; khoảng 10 mục feed. |
| rss_feed | 404 | not_found | https://doantn.hcmus.edu.vn/rss.xml | HTTP 404. |
| atom_feed | 404 | not_found | https://doantn.hcmus.edu.vn/atom.xml | HTTP 404. |
| wordpress_api | 200 | json_api | https://doantn.hcmus.edu.vn/wp-json/wp/v2/posts?per_page=1 | JSON có cấu trúc danh sách, 1 phần tử ở phản hồi thử nghiệm. |
| listing | 200 | html | https://doantn.hcmus.edu.vn/niem-yet-hoat-dong/ | HTML; title='NIÊM YẾT HOẠT ĐỘNG – Đoàn trường Đại học Khoa học tự nhiên, ĐHQG-HCM'; 103 liên kết. Feed khai báo: https://doantn.hcmus.edu.vn/feed/, https://doantn.hcmus.edu.vn/comments/feed/, https://doantn.hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Fdoantn.hcmus.edu.vn%2Fniem-yet-hoat-dong%2F&format=xml |
| alternate_feed | 200 | feed | https://doantn.hcmus.edu.vn/comments/feed/ | XML hợp lệ, root=rss; khoảng 0 mục feed. |
| alternate_feed | 200 | xml | https://doantn.hcmus.edu.vn/wp-json/oembed/1.0/embed?url=https%3A%2F%2Fdoantn.hcmus.edu.vn%2Fniem-yet-hoat-dong%2F&format=xml | XML hợp lệ, root=oembed. |

## Sổ tay Sinh viên HCMUS (`stsv`)

- Base URL: https://stsv.hcmus.edu.vn/
- Hướng đề xuất: **html_parser**

| Loại probe | HTTP | Phân loại | URL | Ghi chú |
|---|---:|---|---|---|
| robots | 200 | robots_txt | https://stsv.hcmus.edu.vn/robots.txt | robots.txt đọc được; 0 dòng Disallow; 0 Sitemap được khai báo. |
| sitemap | 404 | not_found | https://stsv.hcmus.edu.vn/sitemap.xml | HTTP 404. |
| sitemap_index | 404 | not_found | https://stsv.hcmus.edu.vn/sitemap_index.xml | HTTP 404. |
| wordpress_sitemap | 404 | not_found | https://stsv.hcmus.edu.vn/wp-sitemap.xml | HTTP 404. |
| rss_feed | 404 | not_found | https://stsv.hcmus.edu.vn/feed/ | HTTP 404. |
| rss_feed | 404 | not_found | https://stsv.hcmus.edu.vn/news/feed/ | HTTP 404. |
| rss_feed | 404 | not_found | https://stsv.hcmus.edu.vn/feed | HTTP 404. |
| rss_feed | 404 | not_found | https://stsv.hcmus.edu.vn/rss.xml | HTTP 404. |
| atom_feed | 404 | not_found | https://stsv.hcmus.edu.vn/atom.xml | HTTP 404. |
| wordpress_api | 404 | not_found | https://stsv.hcmus.edu.vn/wp-json/wp/v2/posts?per_page=1 | HTTP 404. |
| listing | 200 | html | https://stsv.hcmus.edu.vn/ | HTML; title='Sổ tay Sinh viên · Sổ tay Sinh viên'; 90 liên kết. |

## Cổng thông tin nghiên cứu HCMUS (`research`)

- Base URL: https://research.hcmus.edu.vn/
- Hướng đề xuất: **html_parser**

| Loại probe | HTTP | Phân loại | URL | Ghi chú |
|---|---:|---|---|---|
| robots | 404 | not_found | https://research.hcmus.edu.vn/robots.txt | HTTP 404. |
| sitemap | 404 | not_found | https://research.hcmus.edu.vn/sitemap.xml | HTTP 404. |
| sitemap_index | 404 | not_found | https://research.hcmus.edu.vn/sitemap_index.xml | HTTP 404. |
| wordpress_sitemap | 404 | not_found | https://research.hcmus.edu.vn/wp-sitemap.xml | HTTP 404. |
| rss_feed | 404 | not_found | https://research.hcmus.edu.vn/feed/ | HTTP 404. |
| rss_feed | 404 | not_found | https://research.hcmus.edu.vn/news/feed/ | HTTP 404. |
| rss_feed | 404 | not_found | https://research.hcmus.edu.vn/feed | HTTP 404. |
| rss_feed | 404 | not_found | https://research.hcmus.edu.vn/rss.xml | HTTP 404. |
| atom_feed | 404 | not_found | https://research.hcmus.edu.vn/atom.xml | HTTP 404. |
| wordpress_api | 404 | not_found | https://research.hcmus.edu.vn/wp-json/wp/v2/posts?per_page=1 | HTTP 404. |
| listing | 200 | html | https://research.hcmus.edu.vn/ | HTML; title='Science & Innovation@VNUHCM-US'; 90 liên kết. |
