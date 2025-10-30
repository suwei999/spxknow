import sys
import os
import zipfile
import xml.etree.ElementTree as ET


def validate_docx(path: str) -> int:
    print('[INFO] checking:', path)
    if not os.path.exists(path):
        print('[ERROR] 文件不存在')
        return 2
    try:
        with zipfile.ZipFile(path, 'r') as zf:
            names = set(zf.namelist())
            print('[INFO] entries:', len(names))
    except Exception as e:
        print('[ERROR] 非法ZIP/DOCX:', e)
        return 2

    required = {'[Content_Types].xml', '_rels/.rels', 'word/document.xml'}
    missing = [n for n in required if n not in names]
    if missing:
        print('[FAIL] 缺少核心条目:', ', '.join(missing))
        return 1
    else:
        print('[OK] 核心条目存在')

    if 'NULL' in {n.upper() for n in names}:
        print('[FAIL] 包内存在名为 NULL 的部件')
        return 1

    rels_files = [n for n in names if n.endswith('.rels')]
    issues = []
    for rel_path in rels_files:
        try:
            with zipfile.ZipFile(path, 'r').open(rel_path) as fp:
                tree = ET.parse(fp)
                root = tree.getroot()
                for rel in root.findall('.//{*}Relationship'):
                    target = (rel.get('Target') or '').strip()
                    r_type = rel.get('Type') or ''
                    if target.upper() == 'NULL':
                        issues.append(f"{rel_path}: Target='NULL'")
                        continue
                    if target.startswith('http://') or target.startswith('https://'):
                        continue
                    base_dir = rel_path.rsplit('/', 1)[0] if '/' in rel_path else ''
                    normalized = (f"{base_dir}/{target}" if base_dir else target).replace('\\', '/').lstrip('./')
                    while normalized.startswith('../'):
                        normalized = normalized[3:]
                    if normalized not in names:
                        hint = ' (officeDocument)' if r_type.endswith('/officeDocument') else ''
                        issues.append(f"{rel_path}: 缺失部件 -> {target}{hint}")
        except Exception as e:
            issues.append(f"{rel_path}: 解析失败 -> {e}")

    if issues:
        print('[FAIL] 关系/部件问题:')
        for x in issues:
            print(' -', x)
        return 1

    print('[OK] 关系完整')
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python scripts/validate_docx.py <path-to-docx>')
        sys.exit(2)
    sys.exit(validate_docx(sys.argv[1]))


