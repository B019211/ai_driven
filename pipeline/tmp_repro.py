from pathlib import Path
import tempfile
import sys
sys.path.insert(0, str(Path('..').resolve()))
import pipeline.ai_pipeline as ai

tmp = tempfile.mkdtemp()
safe_root = Path(tmp) / 'generated' / 'files'
(safe_root / 'src').mkdir(parents=True)
functions_path = safe_root / 'src' / 'functions.php'
functions_path.write_text('<?php function foo() { echo "hi"; }\n', encoding='utf-8')
validation_errors = [{
    'type': 'php_lint',
    'file': str(functions_path),
    'stdout': '',
    'stderr': 'parse error',
}]

def fake_regen(path, architecture, context_data, rules, format_rules):
    print('fake_regen path=', path)
    print('context errors file=', [e['file'] for e in context_data['errors']])
    return '<?php function foo() { echo "hi"; }'

ai.regenerate_file_with_context = fake_regen
ai.repair_validation_errors(
    validation_errors,
    '',
    '',
    architecture='',
    rules='',
    format_rules='',
    safe_root=safe_root,
)
