#!/usr/bin/env python
import ast
import sys

try:
    with open('customers/views.py', 'r') as f:
        code = f.read()
    ast.parse(code)
    print("✓ Syntax is OK")
    sys.exit(0)
except SyntaxError as e:
    print(f"✗ Syntax Error at line {e.lineno}: {e.msg}")
    if e.text:
        print(f"  {e.text}")
        if e.offset:
            print(f"  {' ' * (e.offset - 1)}^")
    sys.exit(1)
