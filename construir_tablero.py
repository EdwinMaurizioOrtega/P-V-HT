"""Genera el tablero HTML final: inserta data.json en la plantilla.
Los datos se guardan comprimidos ("gz:" + gzip en base64) para que el HTML pese ~70% menos;
con --sin-comprimir se insertan como JSON normal.
Uso: python construir_tablero.py data.json tablero.html [--plantilla plantilla_tablero.html] [--sin-comprimir]"""
import sys, base64, gzip
datos, salida = sys.argv[1], sys.argv[2]
plantilla = sys.argv[sys.argv.index('--plantilla') + 1] if '--plantilla' in sys.argv else 'plantilla_tablero.html'
T = open(plantilla, encoding='utf-8').read()
assert T.count('__TPL__') == 1 and T.count('__DATA__') == 1, 'La plantilla debe tener __TPL__ y __DATA__ una sola vez'
data = open(datos, encoding='utf-8').read()
if '--sin-comprimir' in sys.argv:
    data = data.replace('</', '<\\/')
else:
    data = 'gz:' + base64.b64encode(gzip.compress(data.encode('utf-8'), 9)).decode()
html = T.replace('__TPL__', base64.b64encode(T.encode('utf-8')).decode()).replace('__DATA__', data)
open(salida, 'w', encoding='utf-8').write(html)
print(f'OK -> {salida} ({len(html)/1e6:.1f} MB)')
