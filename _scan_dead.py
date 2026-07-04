import re, os
all_js = ''
for fn in sorted(os.listdir('static/js')):
    if fn.endswith('.js'):
        with open('static/js/'+fn,'r',encoding='utf-8') as f:
            all_js += f.read() + '\n'
funcs = {}
for m in re.finditer(r'function (\w+)\(', all_js):
    name = m.group(1)
    funcs[name] = funcs.get(name,0)+1

uncalled = []
skip = ['esc','_fmt','formatCurrency','formatDate','showToast','closeModal']
for name, dc in funcs.items():
    rc = len(re.findall(r'\b'+name+r'\b', all_js))
    if rc <= dc and len(name) > 3 and name not in skip:
        uncalled.append(name)

with open('dead_fe.txt','w',encoding='utf-8') as f:
    f.write(f'Total: {len(funcs)} functions, Dead: {len(uncalled)}\n')
    for u in sorted(uncalled):
        f.write(f'  {u}\n')
print(f'{len(uncalled)} dead out of {len(funcs)}')
