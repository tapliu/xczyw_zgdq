import openpyxl, json

wb = openpyxl.load_workbook('xczyw_xs.xlsx', data_only=True)
ws = wb.active

rows = []
for r in ws.iter_rows(min_row=2, values_only=True):
    r = list(r)
    for i in range(len(r)):
        if r[i] is None:
            r[i] = 0 if i in (0,2,3,4,5,6,10) else ''
    rows.append(r)

chars = []
for r in rows:
    chars.append({
        'id': r[0],
        'name': r[1],
        'leadership': r[2],
        'martial': r[3],
        'intelligence': r[4],
        'politics': r[5],
        'total_score': r[6],
        'rating': r[7],
        'wu_avg': r[8],
        'wen_avg': r[9],
        'max_stat': r[10],
        'wu_rating': r[11],
        'wen_rating': r[12],
        'total_rating': r[13],
        'type': r[14]
    })

# Verify
for c in chars[:3]:
    print(f"id={c['id']}, name={c['name']}, type={c['type']}")

with open('data.js', 'w', encoding='utf-8') as f:
    f.write('const CHARACTERS = ' + json.dumps(chars, ensure_ascii=False, indent=2) + ';\n')

print('Done - data.js written')
