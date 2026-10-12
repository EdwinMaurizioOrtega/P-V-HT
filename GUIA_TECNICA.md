# Tablero de ventas 2026: guía técnica para conectarlo a SAP

**Documento confidencial.** El tablero y sus datos son información interna del grupo. No compartir fuera del equipo autorizado.

## 1. Contenido del paquete

| Archivo | Para qué sirve |
| --- | --- |
| `plantilla_tablero.html` | El tablero completo (HTML, CSS y JavaScript en un solo archivo) sin datos. Tiene dos marcadores: `__DATA__` (el JSON de datos) y `__TPL__` (copia de la propia plantilla, usada por la función de actualización manual). |
| `construir_tablero.py` | Inserta un `data.json` en la plantilla y genera el HTML final. |
| `etl_referencia.py` | ETL de referencia en Python: lee las exportaciones de SAP, aplica todas las reglas de negocio y produce `data.json`. Probado con los archivos reales: reproduce exactamente los totales del tablero actual. |
| `data_ejemplo.json` y `tablero_ejemplo_datos_ficticios.html` | Datos **inventados** con la misma estructura, para desarrollar y probar sin exponer información real. |
| `tablero_CONFIDENCIAL_datos_reales.html` | El tablero tal como está hoy, con los datos reales. Solo para validar resultados. |

## 2. Cómo funciona hoy

1. Se exportan de SAP los cubos de ventas de cada empresa y los listados de IMEI vendidos.
2. Las marcas envían el listado de IMEI activos.
3. Los archivos se suben al tablero, que los procesa en el navegador y guarda el resultado como un JSON incrustado en el HTML.

El tablero no consulta ninguna base de datos: todo lo que muestra sale del bloque `<script id="data" type="application/json">`.

## 3. Arquitectura propuesta

```
SAP (usuario de solo lectura)
   │  API / vistas
   ▼
ETL programado (etl_referencia.py adaptado)  ── cada hora o cada noche
   │  data.json
   ▼
construir_tablero.py  ──►  tablero.html
   │
   ▼
Servidor interno con autenticación (intranet, SharePoint, servidor web con login)
```

**Recomendación: inyectar el JSON del lado del servidor** con `construir_tablero.py`. Así no hace falta tocar el JavaScript del tablero.

Alternativa: servir `data.json` desde un endpoint autenticado y cambiar en la plantilla la línea

```js
const RAW = JSON.parse(document.getElementById('data').textContent);
```

por una carga asíncrona antes de iniciar el tablero. Requiere reorganizar el arranque del script, porque hoy todo el código se ejecuta de forma síncrona a partir de `RAW`.

## 4. Datos que debe entregar SAP

El ETL espera las mismas columnas que traen hoy las exportaciones. Al conectarse por API, basta con que cada consulta devuelva estos campos.

**Ventas (una fila por línea de factura o nota de crédito, por empresa)**

| Campo | Uso |
| --- | --- |
| Fecha | Fecha de contabilización |
| Numero Documento | Identifica la factura (conteo de facturas y ticket) |
| Cancelado | `N` válido; `Y` anulado; `C` reverso de anulación (Y y C se excluyen) |
| Vendedor | Nombre del vendedor |
| Nombre Cliente, Grupo Cliente, Ciudad | Cliente, canal y ciudad |
| Nombre Exterior (o Nombre Item) | Descripción del artículo; de aquí sale el modelo |
| Grupo | Marca |
| Nombre Grupo | Tipo de producto (CELULARES, ACCESORIOS, TABLETS…) |
| Bodega o Sucursal | Bodega (Lidenar) o sucursal (Movilcelistic, de donde salen las 5 tiendas) |
| Cantidad, Neto, Total, Utilidad | Unidades, venta sin IVA, venta con IVA y utilidad. Las notas de crédito deben venir en negativo |

**IMEI vendidos (una fila por número de serie facturado)**: Número de serie, Fecha de contabilización, Nombre de cliente/proveedor, Nombre de empleado del departamento de ventas, Destinatario de factura: Ciudad, Descripción artículo/serv., y marca (columna `Name` en Lidenar; en Movilcelistic se toma de la primera palabra de la descripción).

**Inventario de Lidenar**: por artículo, Nombre, Categoría, Marca, Costo Total, Costo Unitario y Stock, con su fecha de corte.

**IMEI activos**: no viene de SAP, lo envían las marcas (Transsion y Xiaomi). Hay que definir cómo llega: archivo en una carpeta compartida o API del fabricante.

Referencia para SAP Business One (validar con el consultor SAP): facturas `OINV/INV1`, notas de crédito `ORIN/RIN1`, números de serie `OSRI/SRI1` (o el objeto de números de serie en Service Layer), stock por bodega `OITW`. En S/4HANA se usarían las vistas CDS de facturación y de stock equivalentes. La versión de SAP define el conector exacto.

## 5. Reglas de negocio (ya implementadas en el ETL)

1. Excluir facturas anuladas: `Cancelado` = Y o C.
2. Las notas de crédito restan (cantidades y montos negativos).
3. Modelo sin color: se corta la descripción antes de `COLOR:` y de `ARCOTEL:`; se quita el sufijo `- SS`.
4. Daule y Guayas se reportan como Guayaquil.
5. Clientes únicos por nombre; en el consolidado un cliente que compra a ambas empresas cuenta una vez.
6. Ventas entre empresas (clientes LIDENAR S.A. y MOVILCELISTIC DEL ECUADOR S.A.) se incluyen y se marcan.
7. IMEI: solo números de 15 dígitos de Infinix, Tecno y Xiaomi. Si un IMEI se facturó más de una vez, cuenta solo la última venta.
8. Inventario: stock actual = stock al corte menos lo vendido después del corte. El corte es el último domingo antes de la semana en curso.
9. Semanas ISO (lunes a domingo); el WOS usa las 4 últimas semanas completas.

## 6. Estructura de `data.json`

Formato columnar para que el archivo sea liviano. Cada arreglo de `cols` tiene la misma longitud (`rows`); la posición *i* de cada arreglo describe la misma línea agregada.

| Clave | Contenido |
| --- | --- |
| `dims` | Catálogos de texto: `v` vendedores, `c` clientes, `m` modelos, `g` grupos de cliente, `p` tipos de producto, `b` marcas, `w` bodegas o sucursales, `ci` ciudades. Las columnas guardan el índice dentro de cada catálogo. |
| `cols` | Ventas agregadas por día, empresa, vendedor, cliente, modelo, grupo, tipo, marca, bodega, ciudad y documento. `d` = días desde el 1-ene-2026; `e` = empresa (0 Lidenar, 1 Movilcelistic); `doc` = índice del documento; `q` unidades; `n` venta sin IVA; `t` con IVA; `u` utilidad. |
| `imei` | IMEI agregados: `e`, `d`, `v`, `c`, `m`, `b`, `ci`, `g` (canal principal del cliente), `a` (1 activado, 0 no), `q` cantidad de IMEI. |
| `inv` | Inventario de Lidenar: `corte` (día) e `items` {modelo: [stock, costo total, categoría, marca]}. |
| `metas` | Metas por mes: {"10": [{"v": vendedor, "cli": meta de clientes, "fac": meta de facturación}]}. |
| `meta` | Fechas de última venta por empresa e IMEI, y fecha de actualización. |
| `empresas`, `icClients` | Nombres de empresas e índices de los clientes intercompañía. |

`data_ejemplo.json` sirve como referencia exacta del formato.

## 7. Funciones que dependen de claude.ai

Fuera de claude.ai, estas dos funciones no pueden guardar:

- **Actualizar datos** (subir archivos desde el tablero): con el ETL automático ya no se necesita. Se puede ocultar con `#openUp{display:none}`.
- **Editar y guardar metas**: hoy se guardan dentro del propio HTML. Al migrar, las metas deben vivir en una tabla o archivo del servidor que el ETL lea y pase como `--metas metas.json`.

Todo lo demás (filtros, pestañas, gráficos, cálculos) funciona igual en cualquier servidor.

## 7.1 Ventas desde la API de SAP

En **Actualizar datos → Traer ventas desde SAP** se eligen la empresa y un rango de fechas libre (puede abarcar varios años). El tablero consulta:

```
GET http://192.168.0.154:2143/b1t/api/power_bi/cubo_de_ventas_by_company?empresa=RUC&fecha_inicio=AAAA-MM-DD&fecha_fin=AAAA-MM-DD
```

| RUC | Base SAP | Empresa en el tablero |
| --- | --- | --- |
| `0992537442001` | `EC_SBO_LIDENAR` | Lidenar (0) |
| `1792161037001` | `EC_SBO_CELISTICS` | Movilcelistic (1) |

- `fecha_fin` es inclusiva. El rango se pide en tramos mensuales para no traer respuestas enormes.
- Los campos de la API son los del cubo con `_` en lugar de espacios (`NUMERO_DOCUMENTO` = `Numero Documento`), así que se aplican las mismas reglas que al subir el cubo.
- **Todo de la API:** las ventas de la empresa elegida se **reemplazan completas** por lo que devuelve la API para ese rango (no se mezclan con datos anteriores). Con "Ambas" se reemplazan las dos empresas. IMEI, inventario y metas no vienen de esta API.
- La plantilla puede abrirse **sin datos incrustados**: servir `plantilla_tablero.html` tal cual (por ejemplo `python3 -m http.server 8080` y abrir `http://localhost:8080/plantilla_tablero.html`). Al no tener datos, abre sola la ventana para traer de SAP. No hace falta `data.json` ni `construir_tablero.py`.
- Los días se cuentan desde el 1-ene del año base (clave `anio` del JSON; si no viene, 2026) y los meses se numeran de forma continua (1–12 = año base, 13–24 = el siguiente…). El año base se ajusta al año más antiguo que haya en los datos. Con datos de más de un año, los meses y fechas se muestran con el año (por ejemplo, "Dic 25").
- Fuera de claude.ai lo traído no se guarda: al recargar la página hay que volver a traerlo (un año completo de ambas empresas tarda alrededor de 1 minuto).
- La URL y los RUC están en las constantes `API_URL` y `API_RUC` de la plantilla. La API debe permitir CORS (hoy lo permite) y, si el tablero se publica por `https`, la API también debe servirse por `https` (el navegador bloquea llamadas `http` desde páginas `https`).

## 8. Dependencias externas

El HTML carga Chart.js 4.4.1 (cdn.jsdelivr.net), las fuentes Barlow (Google Fonts) y, solo al subir archivos, SheetJS 0.18.5 (cdnjs). Si el servidor no tiene salida a internet, hay que alojar estos archivos internamente y cambiar sus URL en la plantilla.

## 9. Seguridad y confidencialidad

- El HTML generado contiene **todos los datos** (clientes, vendedores, montos, márgenes). Publicarlo solo detrás de autenticación; nunca en un enlace público.
- Usar un usuario de SAP de **solo lectura**, con acceso únicamente a las vistas necesarias.
- Para desarrollo y pruebas con terceros, usar `data_ejemplo.json` (datos ficticios), no los datos reales.

## 10. Validación

Con los archivos usados hasta hoy, el ETL debe dar exactamente:

| | Lidenar | Movilcelistic |
| --- | --- | --- |
| Venta sin IVA | 73,140,665 | 22,541,846 |
| Unidades | 463,371 | 150,711 |
| Utilidad | 6,190,190 | 3,753,896 |
| Clientes con compra | 1,607 | 6,215 |
| Líneas agregadas (total) | 54,589 | |
| IMEI únicos / activados | 389,046 / 296,032 | |

Ventas de Lidenar al 6-oct-2026 y de Movilcelistic al 29-sep-2026.
