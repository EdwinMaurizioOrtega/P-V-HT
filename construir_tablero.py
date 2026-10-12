"""Genera el tablero HTML final: inserta data.json en la plantilla.
Uso: python construir_tablero.py data.json tablero.html [--plantilla plantilla_tablero.html]"""
import sys, base64
datos, salida = sys.argv[1], sys.argv[2]
plantilla = sys.argv[sys.argv.index('--plantilla') + 1] if '--plantilla' in sys.argv else 'plantilla_tablero.html'
T = open(plantilla, encoding='utf-8').read()
assert T.count('__TPL__') == 1 and T.count('__DATA__') == 1, 'La plantilla debe tener __TPL__ y __DATA__ una sola vez'
data = open(datos, encoding='utf-8').read().replace('</', '<\\/')
html = T.replace('__TPL__', base64.b64encode(T.encode('utf-8')).decode()).replace('__DATA__', data)
open(salida, 'w', encoding='utf-8').write(html)
print(f'OK -> {salida} ({len(html)/1e6:.1f} MB)')
