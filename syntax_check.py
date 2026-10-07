#!/usr/bin/env python3
import sys
import py_compile

files_to_check = [
    "app/Reports/model.py",
    "app/Reports/route.py",
]

errors = []
for fpath in files_to_check:
    try:
        py_compile.compile(fpath, doraise=True)
        print(f"✓ {fpath} - OK")
    except py_compile.PyCompileError as e:
        print(f"✗ {fpath} - ERROR")
        print(f"  {e}")
        errors.append(fpath)

if errors:
    print(f"\n{len(errors)} file(s) with syntax errors")
    sys.exit(1)
else:
    print(f"\nAll {len(files_to_check)} files compiled successfully!")
    sys.exit(0)
