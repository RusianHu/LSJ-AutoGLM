# -*- coding: utf-8 -*-
"""扫描 gui/pages/ 和 gui/main_window.py 中未 key 化的中文硬编码文案。"""
import re
import pathlib

CN_PATTERN = re.compile(r'[\u4e00-\u9fff]{2,}')

# 已 key 化的标志（跳过含这些模式的行）
SAFE_PATTERNS = [
    re.compile(r'self\._t\('),
    re.compile(r'i18n_manager\.t\('),
    re.compile(r'_log\(f'),
    re.compile(r'logging\.'),
    re.compile(r'setToolTip\('),  # tooltip 暂不要求 i18n
]

files = sorted(pathlib.Path('gui/pages').glob('*.py')) + [pathlib.Path('gui/main_window.py')]

results = []
for fp in files:
    with open(fp, encoding='utf-8') as f:
        lines = f.readlines()
    in_docstring = False
    docstring_char = None
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # 追踪多行 docstring
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                dc = stripped[:3]
                # 单行 docstring
                if stripped.count(dc) >= 2 and len(stripped) > 3:
                    continue
                in_docstring = True
                docstring_char = dc
                continue
        else:
            if docstring_char in stripped:
                in_docstring = False
            continue

        # 跳过注释行
        if stripped.startswith('#'):
            continue
        # 跳过空行
        if not stripped:
            continue
        # 跳过含中文的注释（# 后面）
        comment_pos = line.find('#')
        code_part = line[:comment_pos] if comment_pos >= 0 else line

        if not CN_PATTERN.search(code_part):
            continue

        # 跳过安全模式
        if any(p.search(code_part) for p in SAFE_PATTERNS):
            continue

        results.append(f'{fp.name}:{i}: {stripped[:100]}')

if results:
    print(f'发现 {len(results)} 处可能未 key 化的中文:')
    for r in results:
        print(' ', r)
else:
    print('未发现明显硬编码残留。')
