import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.ai_pipeline import (
    collect_php_includes,
    resolve_php_include_path,
    validate_php_cross_files,
)


class PhpCrossFileValidationTest(unittest.TestCase):
    def test_collect_php_includes_simple_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            src = root / "src"
            src.mkdir(parents=True)
            php_path = src / "index.php"
            php_path.write_text(
                "<?php\nrequire 'config.php';\nrequire_once __DIR__ . '/functions.php';\ninclude_once 'common.php';\n",
                encoding="utf-8",
            )

            includes = collect_php_includes(php_path)
            self.assertEqual(len(includes), 3)
            self.assertEqual(includes[0]["type"], "require")
            self.assertEqual(includes[0]["expression"], "'config.php'")
            self.assertEqual(includes[1]["type"], "require_once")
            self.assertEqual(includes[1]["expression"], "__DIR__ . '/functions.php'")
            self.assertEqual(includes[2]["type"], "include_once")
            self.assertEqual(includes[2]["expression"], "'common.php'")

    def test_validate_php_cross_files_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            safe_root = Path(tmpdir) / "generated" / "files"
            src = safe_root / "src"
            src.mkdir(parents=True)

            index_php = src / "index.php"
            functions_php = src / "functions.php"

            index_php.write_text("<?php\nrequire_once __DIR__ . '/functions.php';\n", encoding="utf-8")
            functions_php.write_text("<?php\nfunction foo() {}\n", encoding="utf-8")

            errors = validate_php_cross_files([index_php, functions_php], safe_root)
            self.assertEqual(errors, [])

    def test_validate_php_cross_files_missing_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            safe_root = Path(tmpdir) / "generated" / "files"
            src = safe_root / "src"
            src.mkdir(parents=True)

            index_php = src / "index.php"
            index_php.write_text("<?php\nrequire_once __DIR__ . '/missing.php';\n", encoding="utf-8")

            errors = validate_php_cross_files([index_php], safe_root)
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0]["type"], "php_include")
            self.assertIn("Referenced PHP file does not exist", errors[0]["message"])
            self.assertEqual(errors[0]["file"], "src/index.php")
            self.assertEqual(errors[0]["reference"], "src/missing.php")

    def test_validate_php_cross_files_dir_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            safe_root = Path(tmpdir) / "generated" / "files"
            src = safe_root / "src"
            src.mkdir(parents=True)

            index_php = src / "index.php"
            functions_php = src / "functions.php"

            index_php.write_text("<?php\nrequire_once __DIR__ . '/functions.php';\n", encoding="utf-8")
            functions_php.write_text("<?php\nfunction foo() {}\n", encoding="utf-8")

            errors = validate_php_cross_files([index_php], safe_root)
            self.assertEqual(errors, [])

    def test_validate_php_cross_files_outside_safe_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            safe_root = Path(tmpdir) / "generated" / "files"
            src = safe_root / "src"
            src.mkdir(parents=True)

            index_php = src / "index.php"
            index_php.write_text("<?php\nrequire_once __DIR__ . '/../../outside.php';\n", encoding="utf-8")

            errors = validate_php_cross_files([index_php], safe_root)
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0]["type"], "php_include")
            self.assertIn("outside SAFE_ROOT", errors[0]["message"])
            self.assertEqual(errors[0]["file"], "src/index.php")

    def test_validate_php_cross_files_dynamic_path_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            safe_root = Path(tmpdir) / "generated" / "files"
            src = safe_root / "src"
            src.mkdir(parents=True)

            index_php = src / "index.php"
            index_php.write_text("<?php\nrequire_once $config['file'];\n", encoding="utf-8")

            errors = validate_php_cross_files([index_php], safe_root)
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
