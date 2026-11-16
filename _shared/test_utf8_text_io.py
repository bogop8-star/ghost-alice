"""Regression tests: Core modules read and write text files as UTF-8 on any locale.

On a Korean Windows locale (cp949) a locale-default read_text() fails on UTF-8 JSON that holds
non-ASCII text, such as a settings.json with a Korean path. These tests do not depend on the host locale.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SHARED = Path(os.environ.get('GHOST_ALICE_TEST_SHARED_ROOT', Path(__file__).parent))


class Utf8TextIoTests(unittest.TestCase):
    def test_core_modules_pass_encoding_to_read_text_and_write_text(self):
        """Every Path.read_text/write_text call in a non-test Core module names its encoding."""
        missing = []
        for path in sorted(SHARED.glob('*.py')):
            if path.name.startswith('test_'):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ('read_text', 'write_text')
                        and not any(k.arg in ('encoding', None) for k in node.keywords)):
                    missing.append(f'{path.name}:{node.lineno}:{node.func.attr}')
        self.assertEqual(missing, [])

    def test_installed_ledger_lookup_reads_install_state_as_utf8(self):
        """response_route reads install-state JSON with a Korean source root without a locale-default decode."""
        with tempfile.TemporaryDirectory() as tmp:
            ghost = Path(tmp) / 'ghost'
            source_root = Path(tmp) / '설치 원본'
            (ghost / 'install-state').mkdir(parents=True)
            (ghost / 'install-state' / 'claude.json').write_text(
                json.dumps(dict(platform='claude', source_root=str(source_root)), ensure_ascii=False), encoding='utf-8')
            probe = ('import sys, response_route\n'
                     'try:\n'
                     '    response_route._load_installed_ledger("claude")\n'
                     'except response_route.RouteBindingError as error:\n'
                     '    print("binding-error", error)\n'
                     'except (ImportError, OSError) as error:\n'
                     '    print("loaded-source-root", type(error).__name__)\n')
            env = {k: v for k, v in os.environ.items()
                   if k not in ('GHOST_ALICE_CORE_ROOT', 'GHOST_ALICE_SKILLS_DIR')}
            env.update(GHOST_ALICE_GHOST_ROOT=str(ghost), PYTHONUTF8='0', PYTHONDONTWRITEBYTECODE='1')
            run = subprocess.run([sys.executable, '-B', '-X', 'warn_default_encoding', '-W', 'error::EncodingWarning',
                                  '-c', probe], cwd=SHARED, capture_output=True, env=env)
            self.assertNotIn(b'EncodingWarning', run.stderr, run.stderr.decode('utf-8', 'replace'))
            self.assertNotIn(b'UnicodeDecodeError', run.stderr, run.stderr.decode('utf-8', 'replace'))


if __name__ == '__main__':
    unittest.main()
