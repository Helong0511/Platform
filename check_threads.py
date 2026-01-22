import threading

print('当前运行的线程:')
for t in threading.enumerate():
    print(f'  {t.name} (ID: {t.ident}, 存活: {t.is_alive()})')