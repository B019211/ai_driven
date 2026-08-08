import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.ai_pipeline import run_local_php_lint, repair_validation_errors
from pipeline.config import SAFE_ROOT


class PhpRepairLoopTest(unittest.TestCase):
    def test_php_repair_loop_with_intentional_syntax_error(self) -> None:
        php_path = SAFE_ROOT / "src/index.php"

        if not php_path.exists():
            self.skipTest(f"PHP file not found: {php_path}")

        backup_path = Path(tempfile.gettempdir()) / f"src_index_php_backup_{uuid4().hex}.php"
        original_content = php_path.read_text(encoding="utf-8")

        try:
            shutil.copy2(php_path, backup_path)

            broken_content = original_content + "\n<?php syntax error\n"
            php_path.write_text(broken_content, encoding="utf-8")

            lint_result = run_local_php_lint(php_path)
            self.assertNotEqual(lint_result.get("exit_code"), 0, "Expected php -l to detect a syntax error")

            validation_errors = [{
                "type": "php_lint",
                "file": str(php_path),
                "stdout": lint_result.get("stdout", ""),
                "stderr": lint_result.get("stderr", ""),
            }]

            repair_validation_errors(
                validation_errors,
                lint_result.get("stdout", ""),
                lint_result.get("stderr", ""),
                architecture="",
                rules="",
                format_rules="",
                safe_root=SAFE_ROOT,
                target_file_override="src/index.php",
            )

            post_repair_result = run_local_php_lint(php_path)
            self.assertEqual(post_repair_result.get("exit_code"), 0, "PHP syntax should be fixed after repair")
            print("PHP repair loop succeeded")

        finally:
            if backup_path.exists():
                php_path.write_text(backup_path.read_text(encoding="utf-8"), encoding="utf-8")
                backup_path.unlink()

    def test_multiple_php_repair_loop_with_single_failure(self) -> None:
        index_path = SAFE_ROOT / "src/index.php"
        functions_path = SAFE_ROOT / "src/functions.php"

        if not index_path.exists():
            self.skipTest(f"PHP file not found: {index_path}")

        index_backup = Path(tempfile.gettempdir()) / f"src_index_php_backup_{uuid4().hex}.php"
        functions_backup = Path(tempfile.gettempdir()) / f"src_functions_php_backup_{uuid4().hex}.php"
        original_index = index_path.read_text(encoding="utf-8")
        original_functions = functions_path.read_text(encoding="utf-8") if functions_path.exists() else None

        try:
            shutil.copy2(index_path, index_backup)
            if functions_path.exists():
                shutil.copy2(functions_path, functions_backup)

            index_path.write_text("<?php echo 'ok';\n", encoding="utf-8")
            functions_path.write_text("<?php function foo() { echo 'hi'\n", encoding="utf-8")

            index_result = run_local_php_lint(index_path)
            self.assertEqual(index_result.get("exit_code"), 0, "Expected index.php to pass lint")

            functions_result = run_local_php_lint(functions_path)
            self.assertNotEqual(functions_result.get("exit_code"), 0, "Expected functions.php to fail lint")

            validation_errors = [{
                "type": "php_lint",
                "file": str(functions_path),
                "stdout": functions_result.get("stdout", ""),
                "stderr": functions_result.get("stderr", ""),
            }]

            repair_validation_errors(
                validation_errors,
                functions_result.get("stdout", ""),
                functions_result.get("stderr", ""),
                architecture="",
                rules="",
                format_rules="",
                safe_root=SAFE_ROOT,
            )

            post_index_result = run_local_php_lint(index_path)
            post_functions_result = run_local_php_lint(functions_path)

            self.assertEqual(post_index_result.get("exit_code"), 0, "index.php should still pass after repair")
            self.assertEqual(post_functions_result.get("exit_code"), 0, "functions.php should pass after repair")
            print("Multiple PHP repair loop succeeded")

        finally:
            if index_backup.exists():
                index_path.write_text(index_backup.read_text(encoding="utf-8"), encoding="utf-8")
                index_backup.unlink()
            if functions_backup.exists():
                functions_path.write_text(functions_backup.read_text(encoding="utf-8"), encoding="utf-8")
                functions_backup.unlink()
            elif functions_path.exists() and original_functions is None:
                functions_path.unlink()


if __name__ == "__main__":
    unittest.main()
