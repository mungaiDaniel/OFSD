from pathlib import Path
p = Path('app/Valuation/route.py')
with p.open('rb') as f:
    b = f.read()
print('size', len(b))
print('nulls', b.count(b'\x00'))
print(repr(b[:200]))
