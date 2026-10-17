from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import load_config
from .discovery import audit_source
from .fetcher import PoliteFetcher
from .repair import repair_links
from .store import Store
from .sync import sync_source
from .enrich import enrich_weak_articles
from .quality import build_quality_report, normalize_database_text, write_quality_report


def _timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _backup_sqlite(source_path: Path, backup_dir: Path) -> str | None:
    """Create a consistent SQLite snapshot before the batch mutates any data."""
    if not source_path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{source_path.stem}.pre-run-all-{_timestamp()}{source_path.suffix}"
    src = sqlite3.connect(source_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()
    return str(target.resolve())


def _write_audit_reports(config_path: Path, reports: list[dict], warnings: list[str], target_dir: Path) -> tuple[str, str]:
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    payload = {
        "generated_at": generated_at,
        "config": str(config_path),
        "sources": reports,
        "warnings": warnings,
    }
    json_path = target_dir / "source-audit.json"
    md_path = target_dir / "source-audit.md"
    _write_json(json_path, payload)
    md = [
        "# Báo cáo audit nguồn HCMUS Hub",
        "",
        f"- Chạy lúc: `{generated_at}`",
        f"- File cấu hình: `{config_path}`",
        "",
    ]
    for item in reports:
        md += [
            f"## {item.get('source_name', item.get('source_id', 'Nguồn'))} (`{item.get('source_id', '')}`)",
            "",
            f"- Base URL: {item.get('base_url', 'không rõ')}",
            f"- Hướng đề xuất: **{item.get('recommendation', 'cần xem lại')}**",
            "",
            "| Loại probe | HTTP | Phân loại | URL | Ghi chú |",
            "|---|---:|---|---|---|",
        ]
        for row in item.get("results", []):
            status = row.get("status") if row.get("status") is not None else "—"
            url = str(row.get("url", "")).replace("|", "%7C")
            note = str(row.get("note", "")).replace("|", "\\|").replace("\n", " ")
            md.append(f"| {row.get('label', '')} | {status} | {row.get('classification', '')} | {url} | {note} |")
        if item.get("error"):
            md += ["", f"Lỗi audit: `{item['error']}`"]
        if item.get("warnings"):
            md += ["", "Cảnh báo: " + "; ".join(item["warnings"])]
        md.append("")
    if warnings:
        md += ["## Cảnh báo chung", "", *[f"- {warning}" for warning in warnings], ""]
    md_path.write_text("\n".join(md), encoding="utf-8")
    return str(json_path.resolve()), str(md_path.resolve())


def _write_batch_markdown(report: dict, target: Path) -> None:
    repair = report.get("repair", {})
    sync_rows = report.get("sync", [])
    md = [
        "# HCMUS Hub — báo cáo chạy toàn bộ",
        "",
        f"- Bắt đầu: `{report.get('started_at')}`",
        f"- Kết thúc: `{report.get('finished_at')}`",
        f"- CSDL: `{report.get('database')}`",
        f"- Sao lưu trước khi chạy: `{report.get('pre_run_backup') or 'không cần (CSDL chưa tồn tại)'}`",
        "",
        "## Sửa dữ liệu cũ",
        "",
        f"- Trạng thái: **{repair.get('status', 'không chạy')}**",
        f"- Liên kết dự kiến gỡ: {repair.get('planned_links_to_remove', 0)}",
        f"- Bài dự kiến xóa: {repair.get('planned_articles_to_delete', 0)}",
        f"- Liên kết đã gỡ: {repair.get('links_removed', 0)}",
        f"- Bài đã xóa: {len(repair.get('articles_deleted', []))}",
        f"- Sao lưu riêng của thao tác repair: `{repair.get('backup_path') or 'không có'}`",
    ]
    normalization = report.get("text_normalization", {})
    md += [f"- Chuẩn hóa HTML entity: {normalization.get('articles_changed', 0)} bài; {normalization.get('article_sources_changed', 0)} liên kết; {normalization.get('fields_changed', 0)} trường.", ""]
    if repair.get("message"):
        md.append(f"- Ghi chú: {repair['message']}")
    md += ["", "## Đồng bộ các nguồn công khai bật mặc định", "", "| Nguồn | Listing OK | Phát hiện | HTTP 200 | Parse/ghi | Có thân bài | Trống sau fetch | Parse lỗi | Mới | Cập nhật | Lỗi |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in sync_rows:
        if row.get("exception"):
            md.append(f"| {row.get('source_name', row.get('source_id', '?'))} | — | — | — | — | — | — | — | — | — | 1 |")
            continue
        lo = row.get("listing_outcomes", {})
        do = row.get("detail_outcomes", {})
        md.append(
            f"| {row.get('source_name', row.get('source_id', '?'))} | {row.get('listings_succeeded', 0)} | "
            f"{row.get('articles_discovered', 0)} | {row.get('details_http_fetched', row.get('details_fetched', 0))} | "
            f"{row.get('details_fetched', 0)}/{row.get('details_attempted', 0)} | "
            f"{row.get('details_body_extracted', 0)} | {row.get('details_empty_body_after_fetch', 0)} | "
            f"{row.get('details_parse_errors', 0)} | "
            f"{lo.get('new', 0) + do.get('new', 0)} | "
            f"{lo.get('updated_content', 0) + do.get('updated_content', 0)} | {len(row.get('errors', []))} |"
        )
    counts = report.get("final_counts", {})
    md += [
        "",
        "## Kết quả cuối",
        "",
        f"- Số bài trong CSDL: {counts.get('articles', '—')}",
        f"- Chưa đọc: {counts.get('unread', '—')}",
        f"- Nguồn đã đăng ký: {counts.get('sources', '—')}",
        f"- File dữ liệu JSON: `{report.get('export_path')}`",
        f"- Audit chi tiết: `{report.get('audit_markdown_path')}`",
        f"- Kế hoạch repair: `{report.get('repair_plan_path')}`",
        f"- Báo cáo chất lượng: `{report.get('quality_markdown_path', '—')}`",
        "",
        "## Ghi chú",
        "",
        "Báo cáo này ghi nhận kết quả chạy tại máy đã thực hiện lệnh. HTTP fetch thành công không đồng nghĩa thân bài được trích xuất thành công; hãy xem các chỉ số extraction và báo cáo chất lượng.",
        "",
    ]
    metrics = report.get("quality_metrics", {})
    enrichment = report.get("enrichment", {})
    if enrichment:
        md += ["## Làm giàu dữ liệu cũ", "", f"- Ứng viên yếu dữ liệu: {enrichment.get('candidate_records', '—')}",
               f"- Lượt thử tải chi tiết: {enrichment.get('details_attempted', 0)}", f"- HTTP tải thành công: {enrichment.get('http_fetched', 0)}",
               f"- Trích xuất được thân bài: {enrichment.get('body_extracted', 0)}", f"- Tải được trang nhưng chưa lấy thân bài: {enrichment.get('empty_body_after_fetch', 0)}", ""]
    if metrics:
        md += ["## Chất lượng dữ liệu sau đồng bộ", "", "| Chỉ số | Số bài |", "|---|---:|",
               f"| Thiếu nội dung đầy đủ | {metrics.get('empty_content', '—')} |",
               f"| Thiếu cả nội dung lẫn tóm tắt | {metrics.get('neither_content_nor_summary', '—')} |",
               f"| Chưa có ngày đăng | {metrics.get('missing_published_at', '—')} |",
               f"| Ngày chưa xác minh | {metrics.get('unverified_date', '—')} |",
               f"| Tiêu đề có vẻ dựng từ slug | {metrics.get('slug_placeholder_title', '—')} |",
               f"| HTML entity còn sót | {metrics.get('html_entities', '—')} |", ""]
    target.write_text("\n".join(md), encoding="utf-8")


async def run_all(*, config_path: str | Path, db_path: str | Path, output_dir: str | Path,
                  delay: float = 1.0, max_details: int = 30,
                  max_items_per_listing: int = 1000, enrich_details: int | None = None) -> dict:
    """One-pass workflow: snapshot, audit all configured sources, repair safely,
    sync enabled announcement sources, and export a run report.
    """
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    config_file = Path(config_path).expanduser().resolve()
    database = Path(db_path).expanduser().resolve()
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    config, sources = load_config(config_file)

    # Snapshot before even initializing/migrating the schema.
    pre_backup = _backup_sqlite(database, out / "backups")

    # Ensure schema exists for first-run installs and capture pre-repair counts.
    store = Store(database)
    try:
        initial_counts = store.counts()
    finally:
        store.close()

    report: dict[str, Any] = {
        "version": "0.8",
        "started_at": started_at,
        "config": str(config_file),
        "database": str(database),
        "output_directory": str(out),
        "pre_run_backup": pre_backup,
        "initial_counts": initial_counts,
        "settings": {
            "delay_seconds": delay,
            "max_details_per_source": max_details,
            "max_items_per_listing": max_items_per_listing,
            "enrich_details": "all" if enrich_details is None else enrich_details,
            "audit_includes_disabled_reference_sources": True,
            "sync_includes_enabled_sources_only": True,
        },
    }

    # Audit all configured sources, including disabled reference-only sources.
    audit_reports: list[dict] = []
    audit_warnings: list[str] = []
    async with PoliteFetcher(
        user_agent=config.get("user_agent", "HCMUSHub/0.8"),
        timeout=float(config.get("request_timeout_seconds", 20)),
        delay=max(0.0, delay),
        max_bytes=int(config.get("max_response_bytes", 5_000_000)),
        respect_robots=True,
    ) as fetcher:
        for source in sources:
            print(f"[AUDIT] {source.id}: {source.name}", flush=True)
            try:
                audit_reports.append(await audit_source(source, fetcher))
            except Exception as exc:  # one broken site must not stop the whole batch
                audit_reports.append({
                    "source_id": source.id,
                    "source_name": source.name,
                    "base_url": source.base_url,
                    "recommendation": "manual_review",
                    "results": [],
                    "error": f"{type(exc).__name__}: {exc}",
                })
            audit_warnings = list(fetcher.warnings)
    audit_json_path, audit_md_path = _write_audit_reports(config_file, audit_reports, audit_warnings, out / "audit")
    report["audit_json_path"] = audit_json_path
    report["audit_markdown_path"] = audit_md_path
    report["audit_sources"] = [
        {
            "source_id": row.get("source_id"),
            "recommendation": row.get("recommendation"),
            "error": row.get("error"),
            "http_200": sum(1 for probe in row.get("results", []) if probe.get("status") == 200),
            "probes": len(row.get("results", [])),
        }
        for row in audit_reports
    ]

    # Create and save the exact repair plan before making any changes.
    plan = repair_links(database, apply=False)
    plan_path = out / "repair-plan.json"
    _write_json(plan_path, plan)
    report["repair_plan_path"] = str(plan_path.resolve())
    repair_summary: dict[str, Any] = {
        "status": "skipped_unresolved_duplicates" if plan.get("unresolved_duplicate_groups") else "planned",
        "planned_links_to_remove": len(plan.get("links_to_remove", [])),
        "planned_articles_to_delete": len(plan.get("articles_to_delete", [])),
        "protected_navigation_links": len(plan.get("protected_navigation_links", [])),
        "unresolved_duplicate_groups": len(plan.get("unresolved_duplicate_groups", [])),
        "plan_path": str(plan_path.resolve()),
    }
    if not plan.get("unresolved_duplicate_groups"):
        print(
            f"[REPAIR] Áp dụng kế hoạch an toàn: {repair_summary['planned_links_to_remove']} liên kết, "
            f"{repair_summary['planned_articles_to_delete']} bản ghi bài (đã sao lưu).",
            flush=True,
        )
        try:
            applied = repair_links(database, apply=True)
            repair_path = out / "repair-result.json"
            _write_json(repair_path, applied)
            repair_summary.update({
                "status": "applied",
                "links_removed": applied.get("links_removed", 0),
                "articles_deleted": applied.get("articles_deleted", []),
                "backup_path": applied.get("backup_path"),
                "result_path": str(repair_path.resolve()),
                "message": applied.get("message"),
            })
        except Exception as exc:
            repair_summary.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    else:
        repair_summary["message"] = "Không tự sửa vì còn nhóm trùng chưa phân giải; kế hoạch được lưu để xem lại."
    report["repair"] = repair_summary

    # Decode HTML entities already stored in historical rows. The pre-run backup above
    # guarantees rollback is possible if the user needs the original snapshot.
    try:
        report["text_normalization"] = normalize_database_text(database)
    except Exception as exc:
        report["text_normalization"] = {"error": f"{type(exc).__name__}: {exc}"}

    # Sync all enabled sources in one pass. A failure on one source does not stop others.
    enabled_sources = [source for source in sources if source.enabled]
    sync_reports: list[dict] = []
    store = Store(database)
    try:
        async with PoliteFetcher(
            user_agent=config.get("user_agent", "HCMUSHub/0.8"),
            timeout=float(config.get("request_timeout_seconds", 20)),
            delay=max(0.0, delay),
            max_bytes=int(config.get("max_response_bytes", 5_000_000)),
            respect_robots=True,
        ) as fetcher:
            for source in enabled_sources:
                print(f"[SYNC] {source.id}: {source.name}", flush=True)
                try:
                    result = await sync_source(
                        source,
                        fetcher,
                        store,
                        max_details=max_details,
                        max_items_per_listing=max_items_per_listing,
                    )
                    sync_reports.append(result)
                    print(
                        f"  -> phát hiện {result.get('articles_discovered', 0)}, "
                        f"chi tiết {result.get('details_fetched', 0)}/{result.get('details_attempted', 0)}, "
                        f"lỗi {len(result.get('errors', []))}",
                        flush=True,
                    )
                except Exception as exc:
                    sync_reports.append({
                        "source_id": source.id,
                        "source_name": source.name,
                        "exception": f"{type(exc).__name__}: {exc}",
                        "errors": [f"{type(exc).__name__}: {exc}"],
                    })
                    print(f"  -> LỖI: {type(exc).__name__}: {exc}", flush=True)
            if enrich_details is None or enrich_details > 0:
                if enrich_details is None:
                    print("[ENRICH] Làm giàu toàn bộ bài đang thiếu dữ liệu (không giới hạn số lượng)", flush=True)
                else:
                    print(f"[ENRICH] Ưu tiên làm giàu tối đa {enrich_details} bài đang thiếu dữ liệu", flush=True)
                try:
                    report["enrichment"] = await enrich_weak_articles(
                        enabled_sources, fetcher, store, limit=enrich_details
                    )
                    print(
                        f"  -> HTTP {report['enrichment'].get('http_fetched', 0)}, "
                        f"thân bài {report['enrichment'].get('body_extracted', 0)}, "
                        f"lỗi {len(report['enrichment'].get('errors', []))}", flush=True
                    )
                except Exception as exc:
                    report["enrichment"] = {"errors": [f"{type(exc).__name__}: {exc}"]}
            else:
                report["enrichment"] = {"details_attempted": 0, "message": "Đã tắt bằng --enrich-details 0."}
        report["fetcher_warnings"] = list(fetcher.warnings)
        final_counts = store.counts()
        exported = store.export_articles()
    finally:
        store.close()

    export_path = out / "hcmus-hub-export.json"
    _write_json(export_path, exported)
    quality = build_quality_report(database)
    quality_json_path, quality_md_path = write_quality_report(quality, out / "quality")
    report["quality_metrics"] = quality.get("metrics", {})
    report["quality_json_path"] = str(quality_json_path)
    report["quality_markdown_path"] = str(quality_md_path)
    report["sync"] = sync_reports
    report["final_counts"] = final_counts
    report["export_path"] = str(export_path.resolve())
    report["sync_sources_succeeded"] = sum(1 for row in sync_reports if not row.get("exception") and not row.get("errors"))
    report["sync_sources_with_errors"] = [
        {"source_id": row.get("source_id"), "errors": row.get("errors", [row.get("exception")])}
        for row in sync_reports if row.get("exception") or row.get("errors")
    ]
    report["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    report_json_path = out / "run-report.json"
    report_md_path = out / "run-report.md"
    _write_json(report_json_path, report)
    _write_batch_markdown(report, report_md_path)
    report["run_report_json_path"] = str(report_json_path.resolve())
    report["run_report_markdown_path"] = str(report_md_path.resolve())
    # Rewrite JSON once more to include the report paths themselves.
    _write_json(report_json_path, report)
    print("\n[HOÀN TẤT]", flush=True)
    print(f"Bài trong CSDL: {final_counts['articles']} | Chưa đọc: {final_counts['unread']} | Nguồn: {final_counts['sources']}", flush=True)
    print(f"Báo cáo tổng: {report_md_path.resolve()}", flush=True)
    print(f"Dữ liệu xuất: {export_path.resolve()}", flush=True)
    return report
