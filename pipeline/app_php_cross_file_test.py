import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.ai_pipeline import (
    collect_php_includes,
    resolve_php_include_path,
    validate_php_cross_files,
    repair_validation_errors,
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

    def test_cross_file_error_triggers_repair_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            safe_root = Path(tmpdir) / "generated" / "files"
            src = safe_root / "src"
            src.mkdir(parents=True)

            index_php = src / "index.php"
            index_php.write_text("<?php\nrequire_once __DIR__ . '/missing.php';\n", encoding="utf-8")

            php_files = [index_php]
            cross_file_errors = validate_php_cross_files(php_files, safe_root)

            self.assertEqual(len(cross_file_errors), 1)
            self.assertEqual(cross_file_errors[0]["type"], "php_include")
            self.assertEqual(cross_file_errors[0]["file"], "src/index.php")
            self.assertEqual(cross_file_errors[0]["include_type"], "require_once")

            available_files = [str(p.relative_to(safe_root)).replace("\\", "/") for p in php_files]
            with patch("pipeline.ai_pipeline.regenerate_file_with_context") as mock_regen:
                def fake_regen(path, architecture, context_data, rules, format_rules):
                    self.assertEqual(context_data["available_php_files"], available_files)
                    self.assertEqual(context_data["errors"], cross_file_errors)
                    self.assertEqual(context_data["errors"][0]["include_type"], "require_once")
                    return "<?php\n// repaired\n"

                mock_regen.side_effect = fake_regen

                repair_validation_errors(
                    cross_file_errors,
                    "",
                    "",
                    "",
                    "",
                    "",
                    safe_root,
                    available_php_files=available_files,
                )
                mock_regen.assert_called_once()

    def test_application_pipeline_cross_file_repair_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            safe_root = project_root / "generated" / "files"
            src = safe_root / "src"
            src.mkdir(parents=True)

            index_php = src / "index.php"
            index_php.write_text("<?php\nrequire_once __DIR__ . '/missing.php';\n", encoding="utf-8")

            # We cannot run the full application pipeline here because it requires OpenAI and review.
            # Instead, validate that the error path goes through validate_php_cross_files.
            errors = validate_php_cross_files([index_php], safe_root)
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0]["type"], "php_include")
            self.assertEqual(errors[0]["include_type"], "require_once")
            self.assertEqual(errors[0]["reference"], "src/missing.php")


if __name__ == "__main__":
    unittest.main()
