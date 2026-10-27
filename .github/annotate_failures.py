# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn unittest failure blocks into GitHub annotations, which the public API exposes."""
import re
import sys

text = open(sys.argv[1], encoding='utf-8', errors='replace').read()
blocks = re.split(r'\n(?==+\n(?:ERROR|FAIL): )', text)
failures = [b.strip('=\n') for b in blocks if re.match(r'=+\n(?:ERROR|FAIL): ', b.lstrip('\n'))]
if not failures:
    failures = [text[-3000:]]
for block in failures[:10]:
    message = block[-3000:].replace('%', '%25').replace('\r', '').replace('\n', '%0A')
    print(f'::error title=Test failure::{message}')
