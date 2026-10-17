from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .config import load_config
from .batch import run_all as run_all_workflow
from .discovery import audit_source
from .repair import repair_links
from .fetcher import PoliteFetcher
from .store import Store
from .textutils import normalize_title
from .sync import sync_source
from .enrich import enrich_weak_articles
from .quality import build_quality_report, write_quality_report
from .web_server import serve_dashboard
from .sharing import export_snapshot, import_snapshot

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "sources.json"
DEFAULT_DB = ROOT / "data" / "hcmus_hub.sqlite3"


def _parse_enrichment_limit(value: str) -> int | None:
    """Parse a numeric cap, or 'all' for unlimited enrichment."""
    if value.strip().casefold() in {"all", "tat-ca", "tất-cả"}:
        return None
    try:
        limit = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Nhập số nguyên không âm hoặc 'all'.") from exc
    if limit < 0:
        raise argparse.ArgumentTypeError("Giới hạn phải là số nguyên không âm hoặc 'all'.")
    return limit


def _load_args_config(path: str):
    config_path = Path(path).expanduser().resolve()
    config, sources = load_config(config_path)
    return config, sources, config_path


def _create_fetcher(config, *, force_delay: float | None = None) -> PoliteFetcher:
    return PoliteFetcher(
        user_agent=config.get("user_agent", "HCMUSHub/0.1"),
        timeout=float(config.get("request_timeout_seconds", 20)),
        delay=float(config.get("delay_between_requests_seconds", 0.8) if force_delay is None else force_delay),
        max_bytes=int(config.get("max_response_bytes", 5_000_000)),
        respect_robots=True,
    )


async def _run_audit(args):
    config, sources, config_path = _load_args_config(args.config)
    target_dir = Path(args.output).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    selected = [s for s in sources if (not args.source or s.id in args.source)]
    reports = []
    async with _create_fetcher(config, force_delay=args.delay) as fetcher:
        # Keep audit gentle: unique origins are cached for robots checks; endpoints are requested sequentially.
        for source in selected:
            print(f"[AUDIT] {source.id}: {source.name}")
            reports.append(await audit_source(source, fetcher))
        shared_warnings = list(fetcher.warnings)
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    payload = {"generated_at": generated_at, "config": str(config_path), "sources": reports, "warnings": shared_warnings}
    json_path = target_dir / "source-audit.json"
    md_path = target_dir / "source-audit.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = ["# Báo cáo audit nguồn HCMUS Hub", "", f"- Chạy lúc: `{generated_at}`", f"- File cấu hình: `{config_path}`", ""]
    for item in reports:
        md += [f"## {item['source_name']} (`{item['source_id']}`)", "", f"- Base URL: {item['base_url']}", f"- Hướng đề xuất: **{item['recommendation']}**", "", "| Loại probe | HTTP | Phân loại | URL | Ghi chú |", "|---|---:|---|---|---|"]
        for row in item["results"]:
            status = row.get("status") if row.get("status") is not None else "—"
            url = row.get("url", "").replace("|", "%7C")
            note = row.get("note", "").replace("|", "\\|").replace("\n", " ")
            md.append(f"| {row.get('label','')} | {status} | {row.get('classification','')} | {url} | {note} |")
        if item.get("warnings"):
            md += ["", "Cảnh báo: " + "; ".join(item["warnings"])]
        md.append("")
    if shared_warnings:
        md += ["## Cảnh báo chung", "", *[f"- {warning}" for warning in shared_warnings], ""]
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"Đã ghi: {json_path}")
    print(f"Đã ghi: {md_path}")
    for report in reports:
        print(f"  {report['source_id']}: {report['recommendation']} ({len(report['results'])} probes)")


async def _run_sync(args):
    config, sources, _ = _load_args_config(args.config)
    selected = [s for s in sources if s.enabled and (not args.source or s.id in args.source)]
    if args.include_reference:
        selected = [s for s in sources if (not args.source or s.id in args.source)]
    if not selected:
        print("Không có nguồn phù hợp. Kiểm tra config/sources.json và tuỳ chọn --source.")
        return
    db_path = Path(args.db).expanduser().resolve()
    store = Store(db_path)
    try:
        async with _create_fetcher(config, force_delay=args.delay) as fetcher:
            for source in selected:
                print(f"[SYNC] {source.id}: {source.name}")
                report = await sync_source(source, fetcher, store,
                                           max_details=args.max_details,
                                           max_items_per_listing=args.max_items_per_listing)
                print(json.dumps(report, ensure_ascii=False, indent=2))
            if fetcher.warnings:
                print("CẢNH BÁO FETCHER:")
                for warning in fetcher.warnings:
                    print("- " + warning)
        print(f"CSDL: {db_path}")
        print(f"Tổng: {json.dumps(store.counts(), ensure_ascii=False)}")
    finally:
        store.close()


def _looks_like_slug_placeholder(title: str, urls: str) -> bool:
    """Identify sitemap slug placeholders so they are not mistaken for real titles."""
    for url in (urls or "").split(","):
        path = urlparse(url.strip()).path.rstrip("/")
        if not path:
            continue
        slug = path.split("/")[-1]
        slug_title = re.sub(r"[-_]+", " ", slug).strip().capitalize()
        if slug_title and normalize_title(title) == normalize_title(slug_title):
            return True
    return False


def _run_list(args):
    store = Store(Path(args.db).expanduser().resolve())
    try:
        rows = store.list_articles(limit=args.limit, unread_only=args.unread)
        if not rows:
            print("Chưa có thông báo. Chạy lệnh sync trước.")
            return
        for i, row in enumerate(rows, start=1):
            date_text = row["published_at"] or "chưa rõ ngày đăng"
            if row["published_at"] and row.get("published_at_source") in {"legacy_unverified", "unknown", ""}:
                date_text += " (chưa xác minh)"
            title = row["title"]
            if _looks_like_slug_placeholder(title, row.get("source_urls", "")):
                title = "[CHƯA LẤY CHI TIẾT] " + title
            sources = row["source_names"] or "nguồn không rõ"
            categories = row.get("source_categories") or row["category"]
            print(f"{i:02d}. [{categories}] {title}\n    Ngày: {date_text} | Nguồn: {sources}\n    URL: {row['source_urls']}\n")
    finally:
        store.close()


def _run_repair(args):
    result = repair_links(args.db, apply=args.apply)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        target = Path(args.output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        print(f"Đã ghi báo cáo: {target}")
    print(rendered)
    if not args.apply:
        print("Chế độ xem trước: CSDL chưa bị thay đổi. Chỉ thêm --apply sau khi xem báo cáo.")



def _run_all_command(args):
    output_dir = args.output
    if not output_dir:
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        output_dir = str(Path(args.db).expanduser().resolve().parent / "runs" / f"run-{stamp}")
    asyncio.run(run_all_workflow(
        config_path=args.config,
        db_path=args.db,
        output_dir=output_dir,
        delay=args.delay,
        max_details=args.max_details,
        max_items_per_listing=args.max_items_per_listing,
        enrich_details=args.enrich_details,
    ))

def _run_export(args):
    store = Store(Path(args.db).expanduser().resolve())
    try:
        data = store.export_articles()
        target = Path(args.output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Đã xuất {len(data)} bài: {target}")
    finally:
        store.close()


def _run_share_export(args):
    report = export_snapshot(args.db, args.output, args.manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _run_share_import(args):
    report = import_snapshot(args.db, args.snapshot, args.manifest, apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.apply:
        print("Chế độ xem trước: CSDL chưa bị thay đổi. Chỉ thêm --apply sau khi kiểm tra báo cáo.")


def _run_quality(args):
    report = build_quality_report(Path(args.db).expanduser().resolve())
    json_path, md_path = write_quality_report(report, Path(args.output_dir).expanduser().resolve())
    print(f"Tổng số bài: {report['metrics']['articles']}")
    print(f"Thiếu cả nội dung lẫn tóm tắt: {report['metrics']['neither_content_nor_summary']}")
    print(f"Thiếu ngày đăng: {report['metrics']['missing_published_at']}")
    print(f"Ngày chưa xác minh: {report['metrics']['unverified_date']}")
    print(f"Tiêu đề có vẻ dựng từ slug: {report['metrics']['slug_placeholder_title']}")
    print(f"Báo cáo Markdown: {md_path}")
    print(f"Báo cáo JSON: {json_path}")


async def _run_enrich(args):
    config, sources, _ = _load_args_config(args.config)
    selected_ids = args.source or None
    store = Store(Path(args.db).expanduser().resolve())
    try:
        async with _create_fetcher(config, force_delay=args.delay) as fetcher:
            report = await enrich_weak_articles(
                sources, fetcher, store, limit=args.max_details, source_ids=selected_ids
            )
            report["fetcher_warnings"] = list(fetcher.warnings)
        target = Path(args.output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"Đã ghi báo cáo: {target}")
    finally:
        store.close()


def build_parser():
    parser = argparse.ArgumentParser(prog="hcmus-hub", description="Bộ thu thập và dashboard thông báo HCMUS Hub - v0.8")
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit", help="Kiểm tra robots/sitemap/feed/API và trang danh mục trực tiếp")
    audit.add_argument("--config", default=str(DEFAULT_CONFIG))
    audit.add_argument("--output", default=str(ROOT / "data" / "audit"))
    audit.add_argument("--source", action="append", help="ID nguồn; lặp lại để chọn nhiều nguồn. Mặc định tất cả.")
    audit.add_argument("--delay", type=float, default=None, help="Giây tối thiểu giữa các yêu cầu tới cùng host.")
    audit.set_defaults(func=lambda args: asyncio.run(_run_audit(args)))

    sync = sub.add_parser("sync", help="Đồng bộ thông báo vào SQLite")
    sync.add_argument("--config", default=str(DEFAULT_CONFIG))
    sync.add_argument("--db", default=str(DEFAULT_DB))
    sync.add_argument("--source", action="append", help="ID nguồn; mặc định các nguồn enabled.")
    sync.add_argument("--include-reference", action="store_true", help="Cho phép đồng bộ nguồn kind=reference đang disabled.")
    sync.add_argument("--max-details", type=int, default=None, help="Giới hạn số bài chi tiết tải cho mỗi nguồn.")
    sync.add_argument("--max-items-per-listing", type=int, default=1000)
    sync.add_argument("--delay", type=float, default=None)
    sync.set_defaults(func=lambda args: asyncio.run(_run_sync(args)))

    listing = sub.add_parser("list", help="Xem thông báo đã lưu")
    listing.add_argument("--db", default=str(DEFAULT_DB))
    listing.add_argument("--limit", type=int, default=30)
    listing.add_argument("--unread", action="store_true")
    listing.set_defaults(func=_run_list)

    repair = sub.add_parser("repair", help="Rà soát liên kết nguồn trùng và URL điều hướng bị thu nhầm")
    repair.add_argument("--db", default=str(DEFAULT_DB), help="Đường dẫn SQLite cần rà soát")
    repair.add_argument("--apply", action="store_true", help="Áp dụng kế hoạch sau khi tạo bản sao lưu; mặc định chỉ dry-run")
    repair.add_argument("--output", default=str(ROOT / "data" / "repair-plan.json"), help="Đường dẫn báo cáo JSON")
    repair.set_defaults(func=_run_repair)

    run_all = sub.add_parser(
        "run-all",
        help="Chạy một lượt: sao lưu, audit mọi nguồn, sửa lỗi an toàn, đồng bộ nguồn bật và xuất dữ liệu",
    )
    run_all.add_argument("--config", default=str(DEFAULT_CONFIG))
    run_all.add_argument("--db", default=str(DEFAULT_DB))
    run_all.add_argument("--output", default=None, help="Thư mục báo cáo; mặc định tạo thư mục runs theo thời gian")
    run_all.add_argument("--delay", type=float, default=1.0, help="Giây chờ tối thiểu giữa các yêu cầu tới cùng host")
    run_all.add_argument("--max-details", type=int, default=30, help="Giới hạn bài chi tiết mỗi nguồn trong lượt tổng hợp")
    run_all.add_argument("--max-items-per-listing", type=int, default=1000, help="Số URL tối đa đọc từ mỗi danh mục (đặc biệt để không cắt cụt sitemap)")
    run_all.add_argument("--enrich-details", type=_parse_enrichment_limit, default=None, help="Số bài làm giàu; mặc định all (không giới hạn), đặt 0 để bỏ qua")
    run_all.set_defaults(func=_run_all_command)

    enrich = sub.add_parser("enrich", help="Ưu tiên tải chi tiết cho bài cũ đang thiếu dữ liệu")
    enrich.add_argument("--config", default=str(DEFAULT_CONFIG))
    enrich.add_argument("--db", default=str(DEFAULT_DB))
    enrich.add_argument("--source", action="append", help="ID nguồn; mặc định tất cả nguồn đang bật")
    enrich.add_argument("--max-details", type=_parse_enrichment_limit, default=None, help="Số bài làm giàu; mặc định all (không giới hạn), hoặc nhập số cụ thể")
    enrich.add_argument("--delay", type=float, default=1.0)
    enrich.add_argument("--output", default=str(ROOT / "data" / "enrich-report.json"))
    enrich.set_defaults(func=lambda args: asyncio.run(_run_enrich(args)))

    quality = sub.add_parser("quality", help="Phân tích chất lượng dữ liệu mà không sửa CSDL")
    quality.add_argument("--db", default=str(DEFAULT_DB))
    quality.add_argument("--output-dir", default=str(ROOT / "data" / "quality"))
    quality.set_defaults(func=_run_quality)

    web = sub.add_parser("web", help="Chạy dashboard cá nhân trên máy local")
    web.add_argument("--db", default=str(DEFAULT_DB))
    web.add_argument("--host", default="127.0.0.1", help="Mặc định chỉ truy cập từ máy này")
    web.add_argument("--port", type=int, default=8787)
    web.set_defaults(func=lambda args: serve_dashboard(args.db, args.host, args.port))

    export = sub.add_parser("export", help="Xuất toàn bộ dữ liệu ra JSON")
    export.add_argument("--db", default=str(DEFAULT_DB))
    export.add_argument("--output", default=str(ROOT / "data" / "export.json"))
    export.set_defaults(func=_run_export)

    share_export = sub.add_parser("share-export", help="Xuất snapshot dữ liệu dùng chung dạng gzip")
    share_export.add_argument("--db", default=str(DEFAULT_DB))
    share_export.add_argument("--output", default=str(ROOT / "data" / "share-snapshot.json.gz"))
    share_export.add_argument("--manifest", default=str(ROOT / "data" / "share-snapshot.manifest.json"))
    share_export.set_defaults(func=_run_share_export)

    share_import = sub.add_parser("share-import", help="Kiểm tra hoặc nhập snapshot dữ liệu dùng chung")
    share_import.add_argument("--db", default=str(DEFAULT_DB))
    share_import.add_argument("--snapshot", default=str(ROOT / "data" / "share-snapshot.json.gz"))
    share_import.add_argument("--manifest", default=str(ROOT / "data" / "share-snapshot.manifest.json"))
    share_import.add_argument("--apply", action="store_true", help="Ghi snapshot vào SQLite; mặc định chỉ xem trước")
    share_import.set_defaults(func=_run_share_import)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
