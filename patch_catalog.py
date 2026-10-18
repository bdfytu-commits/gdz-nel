import json

with open('app/data/catalog.json') as f:
    data = json.load(f)

def make_sub(id, title, icon, books):
    return {'id': id, 'title': title, 'active': True, 'icon': icon, 'textbooks': [{'id': b[0], 'title': b[1], 'file': b[2]} for b in books]}

for g in data['grades']:
    if g['id'] == '7':
        g['active'] = True
        g['subjects'] = [
            make_sub('math', 'Алгебра', 'math', [('makarichev-7', 'Макарычев', 'algebra/makarichev-7.json')]),
            make_sub('russian', 'Русский язык', 'russian', [('baranov-7-1', 'Баранов. Ч.1', 'russian/baranov-7-1.json'), ('baranov-7-2', 'Баранов. Ч.2', 'russian/baranov-7-2.json')]),
            make_sub('geo', 'География', 'globe', [('matveev-7', 'Матвеев', 'geo/matveev-7.json')]),
            make_sub('history-maps', 'История (карты)', 'history', [('torop-7', 'Тороп', 'history-maps/torop-7.json')])
        ]
    if g['id'] == '8':
        g['active'] = True
        g['subjects'] = [
            make_sub('math', 'Алгебра', 'math', [('makarichev-8', 'Макарычев', 'algebra/makarichev-8.json')]),
            make_sub('russian', 'Русский язык', 'russian', [('barhudarov-8', 'Бархударов', 'russian/barhudarov-8.json')]),
            make_sub('geo', 'География', 'globe', [('matveev-8', 'Матвеев', 'geo/matveev-8.json')]),
            make_sub('history-maps', 'История (карты)', 'history', [('torop-8', 'Тороп', 'history-maps/torop-8.json')])
        ]
    if g['id'] == '9':
        g['active'] = True
        g['subjects'] = [
            make_sub('russian', 'Русский язык', 'russian', [('barhudarov-9', 'Бархударов', 'russian/barhudarov-9.json')]),
            make_sub('geo', 'География', 'globe', [('matveev-9', 'Матвеев', 'geo/matveev-9.json')])
        ]

with open('app/data/catalog.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('Catalog updated!')
