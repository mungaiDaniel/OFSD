import os
import re

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    orig_content = content

    # Layout
    content = content.replace('"min-h-screen flex items-center justify-center p-4"', '"min-vh-100 d-flex align-items-center justify-content-center p-4 py-5"')
    content = content.replace('"flex items-center justify-center"', '"d-flex align-items-center justify-content-center"')
    content = content.replace('"flex justify-center"', '"d-flex justify-content-center"')
    content = content.replace('"flex items-center justify-between"', '"d-flex align-items-center justify-content-between"')
    content = content.replace('"flex items-center gap-2"', '"d-flex align-items-center gap-2"')
    content = content.replace('"flex items-center gap-3"', '"d-flex align-items-center gap-3"')
    content = content.replace('"flex flex-col"', '"d-flex flex-column"')
    
    # Typography
    content = content.replace('"text-xl font-bold', '"fs-4 fw-bold')
    content = content.replace('"text-[22px] font-bold', '"fs-4 fw-bold')
    content = content.replace('font-bold', 'fw-bold')
    content = content.replace('font-semibold', 'fw-bold')
    content = content.replace('"text-sm text-center mb-8"', '"text-center mb-4 text-muted"')
    
    # Cards
    content = content.replace('"rounded-lg border overflow-hidden"', '"card shadow-lg rounded-4 overflow-hidden border-0"')
    content = content.replace('"w-full max-w-md rounded-lg border p-8"', '"card shadow-lg rounded-4 border-0 p-5 bg-dark w-100 my-4"')
    content = content.replace('"bg-white rounded-lg border p-6"', '"card shadow-lg rounded-4 border-0 p-5"')
    
    # Inputs
    content = re.sub(r'"w-full rounded-md px-3 py-2\.5 text-sm outline-none border.*?"', '"form-control py-3 border-secondary"', content)
    content = re.sub(r'"w-full rounded-md px-3 py-2 text-sm outline-none border.*?"', '"form-control py-3 border-secondary"', content)
    
    # Buttons
    content = re.sub(r'"w-full rounded-md py-2\.5 text-sm font-semibold transition-colors cursor-pointer.*?"', '"btn btn-primary btn-lg rounded-pill w-100 fw-bold mt-2"', content)
    content = re.sub(r'"px-4 py-2 bg-brand-400 text-white rounded-md text-sm font-medium.*?"', '"btn btn-primary btn-lg rounded-pill fw-bold"', content)
    
    # Grids
    content = content.replace('grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6', 'row row-cols-1 row-cols-sm-2 row-cols-lg-4 g-3 mb-4')
    content = content.replace('grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6', 'row row-cols-1 row-cols-lg-2 g-4 mb-4')
    
    # Margins and specific fixes
    content = content.replace('mb-6', 'mb-4')
    content = content.replace('mb-8', 'mb-4')
    
    if content != orig_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated: {filepath}")

def main():
    base_dirs = [
        r"c:\Users\Dantez\Downloads\ofds\ofds-frontend\src\pages",
        r"c:\Users\Dantez\Downloads\ofds\ofds-frontend\src\components"
    ]
    for d in base_dirs:
        for root, _, files in os.walk(d):
            for file in files:
                if file.endswith('.tsx'):
                    process_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
