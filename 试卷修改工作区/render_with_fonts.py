"""Run canonical render_docx.py with a CJK font in its disposable LO profile."""
from pathlib import Path
import importlib.util
import shutil

RENDERER = '/Users/weiyao/.codex/plugins/cache/openai-primary-runtime/documents/26.426.12240/skills/documents/render_docx.py'
spec = importlib.util.spec_from_file_location('docx_renderer', RENDERER)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
original_build_env = renderer._build_lo_env


def build_env_with_fonts(profile):
    env = original_build_env(profile)
    fontdir = Path(profile) / 'user' / 'fonts'
    fontdir.mkdir(parents=True, exist_ok=True)
    shutil.copy('/Library/Fonts/Arial Unicode.ttf', fontdir / 'Arial Unicode.ttf')
    env['SAL_FONTPATH'] = str(fontdir)
    return env


renderer._build_lo_env = build_env_with_fonts

if __name__ == '__main__':
    renderer.main()
