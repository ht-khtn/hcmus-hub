import unittest

from hcmus_hub.cli import _looks_like_slug_placeholder, build_parser


class CLITests(unittest.TestCase):
    def test_sitemap_slug_title_is_marked_as_placeholder(self):
        self.assertTrue(_looks_like_slug_placeholder(
            "Thong bao to chuc tuan sinh hoat cong dan sinh vien dau khoa",
            "https://ctsv.hcmus.edu.vn/news/thong-bao-to-chuc-tuan-sinh-hoat-cong-dan-sinh-vien-dau-khoa"
        ))

    def test_real_vietnamese_title_is_not_a_slug_placeholder(self):
        self.assertFalse(_looks_like_slug_placeholder(
            "Thông báo tổ chức Tuần Sinh hoạt Công dân – Sinh viên đầu khóa",
            "https://ctsv.hcmus.edu.vn/news/thong-bao-to-chuc-tuan-sinh-hoat-cong-dan-sinh-vien-dau-khoa"
        ))

    def test_enrichment_limit_supports_unlimited_and_numeric_values(self):
        all_args = build_parser().parse_args(["run-all", "--enrich-details", "all", "--db", "demo.sqlite3"])
        numeric_args = build_parser().parse_args(["run-all", "--enrich-details", "250", "--db", "demo.sqlite3"])
        default_args = build_parser().parse_args(["run-all", "--db", "demo.sqlite3"])
        self.assertIsNone(all_args.enrich_details)
        self.assertEqual(numeric_args.enrich_details, 250)
        self.assertIsNone(default_args.enrich_details)

    def test_run_all_command_is_available(self):
        args = build_parser().parse_args(["run-all", "--db", "demo.sqlite3"])
        self.assertEqual(args.command, "run-all")
        self.assertEqual(args.max_details, 30)
        self.assertEqual(args.max_items_per_listing, 1000)


if __name__ == "__main__":
    unittest.main()
