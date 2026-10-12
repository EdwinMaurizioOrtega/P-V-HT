"""
ETL de referencia del tablero de ventas 2026.

Convierte las exportaciones de SAP (cubos de ventas, IMEI vendidos, IMEI activos e
inventario) en el JSON que consume el tablero (ver ESQUEMA_DATOS.md).

Hoy lee archivos. Para conectarlo a SAP, reemplazar las funciones leer_*() por
consultas a la API o a vistas de solo lectura que devuelvan las MISMAS columnas.
Todo lo demás (reglas de negocio y codificación) se conserva igual.

Uso:
  python etl_referencia.py --cubo-lidenar cubo_L.xlsx --cubo-movil cubo_M.xlsx \
      --imei-lidenar imei_L.xlsx --imei-movil imei_M.xlsx --imei-activos activos.xlsx \
      [--metas metas.json] --salida data.json

Requisitos: Python 3.10+, pandas, openpyxl.
"""
import argparse, json, re, datetime as dt
import pandas as pd

BASE = pd.Timestamp('2026-01-01')          # día 0 del tablero
EMPRESAS = ['Lidenar', 'Movilcelistic']      # índice 0 y 1
INTERCOMPANY = {'LIDENAR S.A.', 'MOVILCELISTIC DEL ECUADOR S.A.'}
CIUDADES_A_GUAYAQUIL = {'DAULE', 'GUAYAS'}
MARCAS_ACTIVACION = {'INFINIX', 'TECNO', 'XIAOMI'}
SIN_CANAL = 'SIN CANAL (sin compras en cubo)'

# ---------------------------------------------------------------- utilidades
def sp(v):
    return re.sub(r'\s+', ' ', '' if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)).strip()

def o_guion(v):
    s = sp(v); return s if s else '—'

def num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return 0.0
    if isinstance(v, (int, float)): return float(v)
    try: return float(str(v).replace(',', ''))
    except ValueError: return 0.0

def modelo(s):
    """Nombre del modelo sin color: 'INFINIX HOT 70 (4+256GB) COLOR: NEGRO' -> 'INFINIX HOT 70 (4+256GB)'."""
    s = sp(s)
    if not s: return 'SIN DESCRIPCIÓN'
    s = re.split(r'\s+COLOR\s*:', s)[0]
    s = re.split(r'\s+ARCOTEL\s*:', s)[0]
    return re.sub(r'\s*-\s*SS$', '', s).strip()

def ciudad_venta(v):
    s = o_guion(v); return 'GUAYAQUIL' if s.upper() in CIUDADES_A_GUAYAQUIL else s

def ciudad_imei(v):
    s = o_guion(v).upper(); return 'GUAYAQUIL' if s in CIUDADES_A_GUAYAQUIL else s

def dia(v):
    """Días desde 1-ene-2026. Acepta fecha, serial de Excel o texto d/m/aaaa."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == '': return None
    if isinstance(v, (int, float)): return int(v) - 46023
    if isinstance(v, (pd.Timestamp, dt.datetime, dt.date)): return (pd.Timestamp(v).normalize() - BASE).days
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})', str(v).strip())
    if m: return (pd.Timestamp(int(m[3]), int(m[2]), int(m[1])) - BASE).days
    return (pd.Timestamp(v).normalize() - BASE).days

def col(df, *nombres, req=True):
    low = {sp(c).lower(): c for c in df.columns}
    for n in nombres:
        if n.lower() in low: return low[n.lower()]
    if req: raise KeyError(f'No encontré la columna {nombres[0]!r}')
    return None

# ---------------------------------------------------------------- lectura (reemplazar por SAP)
def leer_tabla(ruta):
    """Lee el cubo de SAP: .xlsx (hoja con 'Numero Documento') o .xls que en realidad es texto UTF-16 con tabulaciones."""
    with open(ruta, 'rb') as f: cab = f.read(4)
    if cab[:2] == b'PK':
        hojas = pd.read_excel(ruta, sheet_name=None, dtype=object)
        for df in hojas.values():
            if any(sp(c).lower() == 'numero documento' for c in df.columns): return df, hojas
        return next(iter(hojas.values())), hojas
    enc = 'utf-16' if cab[:2] in (b'\xff\xfe', b'\xfe\xff') or cab[1:2] == b'\x00' else 'utf-8'
    return pd.read_csv(ruta, sep='\t', dtype=object, encoding=enc), {}

# ---------------------------------------------------------------- reglas de negocio
def ventas(ruta, e):
    df, hojas = leer_tabla(ruta)
    c = lambda *n, req=True: col(df, *n, req=req)
    df = df[df[c('Cancelado')].map(sp) == 'N']                     # fuera anuladas (Y) y sus reversos (C)
    desc = df[c('Nombre Exterior')]
    item = c('Nombre Item', req=False)
    if item: desc = desc.where(desc.map(sp) != '', df[item])
    bod = c('Bodega', req=False) if e == 0 else None
    bod = bod or c('Sucursal', 'Bodega')
    out = pd.DataFrame({
        'd': df[c('Fecha')].map(dia), 'e': e,
        'v': df[c('Vendedor')].map(o_guion), 'c': df[c('Nombre Cliente')].map(o_guion),
        'm': desc.map(modelo), 'g': df[c('Grupo Cliente')].map(o_guion),
        'p': df[c('Nombre Grupo')].map(lambda x: sp(x) or 'SIN GRUPO'),
        'b': df[c('Grupo')].map(lambda x: sp(x) or 'SIN MARCA'),
        'w': df[bod].map(o_guion).map(lambda x: x if e == 0 else x.upper()),
        'ci': df[c('Ciudad')].map(ciudad_venta),
        'doc': str(e) + '-' + df[c('Numero Documento')].map(sp),
        'q': df[c('Cantidad')].map(num), 'n': df[c('Neto')].map(num),
        't': df[c('Total')].map(num), 'u': df[c('Utilidad')].map(num)})
    out = out[out.d.notna()]
    keys = ['d', 'e', 'v', 'c', 'm', 'g', 'p', 'b', 'w', 'ci', 'doc']
    out = out.groupby(keys, as_index=False)[['q', 'n', 't', 'u']].sum()
    return out, hojas

def inventario(hojas, max_dia):
    """Hoja de stock del libro de Lidenar: Nombre, Categoria, Marca, Costo Total, Costo Unitario, STOCK."""
    items = {}
    for df in hojas.values():
        filas = [df.columns.tolist()] + df.values.tolist()
        if not any(any(re.fullmatch(r'stock', sp(x), re.I) for x in f) for f in filas[:12]): continue
        for f in filas:
            k = next((i for i, x in enumerate(f) if isinstance(x, str) and '(' in x and len(x) > 10), None)
            if k is None or len(f) < k + 6: continue
            ct, st = f[k + 3], f[k + 5]
            if not isinstance(ct, (int, float)) or not isinstance(st, (int, float)): continue
            it = items.setdefault(modelo(f[k]), [0, 0.0, sp(f[k + 1]).upper(), sp(f[k + 2]).upper()])
            it[0] += st; it[1] += ct
    if not items: return None
    wd = (BASE + pd.Timedelta(days=max_dia)).weekday()          # 0 = lunes
    corte = max_dia if wd == 6 else max_dia - wd - 1             # último domingo antes de la semana en curso
    return {'corte': int(corte), 'items': items}

def imeis(ruta, e):
    df = pd.read_excel(ruta, dtype=object)
    c = lambda *n, req=True: col(df, *n, req=req)
    marca = c('Name', req=False)
    desc = df[c('Descripción artículo/serv.')]
    out = pd.DataFrame({
        'imei': df[c('Número de serie')].map(sp), 'e': e, 'ord': range(len(df)),
        'd': df[c('Fecha de contabilización')].map(dia),
        'c': df[c('Nombre de cliente/proveedor')].map(o_guion),
        'v': df[c('Nombre de empleado del departamento de ventas')].map(o_guion),
        'ci': df[c('Destinatario de factura: Ciudad')].map(ciudad_imei),
        'm': desc.map(modelo),
        'b': (df[marca].map(sp) if marca else desc.map(lambda x: (sp(x).split(' ') or [''])[0])).str.upper()})
    return out[out.imei.str.fullmatch(r'\d{15}') & out.b.isin(MARCAS_ACTIVACION) & out.d.notna()]

def activos(ruta):
    ai, ax = set(), set()
    for nombre, df in pd.read_excel(ruta, sheet_name=None, header=None, dtype=str).items():
        dest = ax if 'XIAOMI' in nombre.upper() else ai
        dest.update(x for x in df.iloc[:, 0].map(sp) if re.fullmatch(r'\d{15}', x))
    return ai, ax

# ---------------------------------------------------------------- codificación al formato del tablero
def codificar(sales, imei_rows):
    dims = {k: sorted(sales[k].unique()) for k in ['v', 'c', 'm', 'g', 'p', 'b', 'w', 'ci']}
    for k in ['v', 'c', 'm', 'ci', 'b']:
        conocidos = set(dims[k])
        for x in imei_rows[k].unique():
            if x not in conocidos: dims[k].append(x); conocidos.add(x)
    dims['g'].append(SIN_CANAL)
    idx = {k: {x: i for i, x in enumerate(v)} for k, v in dims.items()}
    docs = {x: i for i, x in enumerate(sales['doc'].unique())}
    cols = {k: sales[k].map(idx[k]).astype(int).tolist() for k in ['v', 'c', 'm', 'g', 'p', 'b', 'w', 'ci']}
    cols['doc'] = sales['doc'].map(docs).tolist()
    cols['d'] = sales['d'].astype(int).tolist(); cols['e'] = sales['e'].astype(int).tolist()
    cols['q'] = sales['q'].round().astype(int).tolist()
    for k in ['n', 't', 'u']: cols[k] = sales[k].round(2).tolist()
    # canal de cada cliente = grupo donde más compra
    canal = sales.groupby(['c', 'g']).n.sum().reset_index().sort_values('n').drop_duplicates('c', keep='last')
    canal = dict(zip(canal.c, canal.g))
    im = imei_rows.assign(g=imei_rows.c.map(lambda x: canal.get(x, SIN_CANAL)))
    for k in ['v', 'c', 'm', 'b', 'ci', 'g']: im[k] = im[k].map(idx[k])
    im['a'] = im['a'].astype(int)
    agg = im.groupby(['e', 'd', 'v', 'c', 'm', 'b', 'ci', 'g', 'a']).size().reset_index(name='q')
    imei = {k: agg[k].astype(int).tolist() for k in agg.columns}; imei['rows'] = len(agg)
    return {'dims': dims, 'cols': cols, 'rows': len(sales), 'empresas': EMPRESAS,
            'icClients': [idx['c'][x] for x in INTERCOMPANY if x in idx['c']], 'imei': imei}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cubo-lidenar', required=True); ap.add_argument('--cubo-movil', required=True)
    ap.add_argument('--imei-lidenar', required=True); ap.add_argument('--imei-movil', required=True)
    ap.add_argument('--imei-activos', required=True); ap.add_argument('--metas'); ap.add_argument('--salida', default='data.json')
    a = ap.parse_args()
    sL, hojasL = ventas(a.cubo_lidenar, 0)
    sM, _ = ventas(a.cubo_movil, 1)
    sales = pd.concat([sL, sM], ignore_index=True)
    vend = pd.concat([imeis(a.imei_lidenar, 0), imeis(a.imei_movil, 1)], ignore_index=True)
    vend = vend.sort_values(['d', 'e', 'ord']).drop_duplicates('imei', keep='last')   # última venta de cada IMEI
    ai, ax = activos(a.imei_activos)
    vend['a'] = [(i in ax) if b == 'XIAOMI' else (i in ai) for i, b in zip(vend.imei, vend.b)]
    data = codificar(sales, vend)
    data['inv'] = inventario(hojasL, int(sL.d.max()))
    data['metas'] = json.load(open(a.metas, encoding='utf-8')) if a.metas else {}
    data['meta'] = {'ventasL': int(sL.d.max()), 'ventasM': int(sM.d.max()), 'imei': int(vend.d.max()),
                    'actualizado': dt.datetime.now(dt.timezone.utc).isoformat()}
    with open(a.salida, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    print(f"OK: {len(sales):,} líneas de venta, {len(vend):,} IMEI, {sum(1 for x in vend.a if x):,} activados -> {a.salida}")

if __name__ == '__main__':
    main()
