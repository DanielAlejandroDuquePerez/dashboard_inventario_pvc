import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import datetime
import requests
import io

# ID y GID de tu hoja en Google Sheets
SPREADSHEET_ID = "1EBrgo8zAYJtrS5uHT9BcptRhlQB2xR1701ZC7hekPfw"
GID_INVENTARIO = "1179061386"

SPREADSHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"

# PEGA AQUÍ EL ENLACE QUE TE DIO "PUBLICAR EN LA WEB":
URL_PUBLICADA_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRFZDj_GF-dBj0aAbd0WGgnXkLPj-ye97AyG9gyBuZIgtFW8Gpd1mvmABQSCjEUeWEppErS_hhdMx1W/pub?gid=1179061327&single=true&output=csv" 

def get_gsheets_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def format_currency_short(val: float) -> str:
    if val >= 1e9:
        return f"${val/1e9:.2f} B COP"
    elif val >= 1e6:
        return f"${val/1e6:.1f} M COP"
    elif val >= 1e3:
        return f"${val/1e3:.0f} k COP"
    return f"${val:,.0f} COP"

def clean_numeric_val(val):
    """Convierte cadenas numéricas de Google Sheets a float."""
    if pd.isna(val) or val is None:
        return 0.0
    val_str = str(val).strip()
    if val_str in ['-', '- ', ' -', '', 'None', 'nan']:
        return 0.0
    
    val_str = val_str.replace('$', '').replace(' ', '')
    
    if val_str.count('.') > 1:
        val_str = val_str.replace('.', '')
    elif val_str.count('.') == 1 and len(val_str.split('.')[1]) == 3 and val_str.split('.')[0].isdigit():
        val_str = val_str.replace('.', '')
        
    val_str = val_str.replace(',', '.')
    
    try:
        return float(val_str)
    except ValueError:
        return 0.0

@st.cache_data(ttl=10)
def load_data_from_sheets():
    df_raw = None

    # Método 1: URL Publicada en la Web (El método más estable y libre de bloqueos HTTP)
    if URL_PUBLICADA_CSV.strip() and "2PACX" in URL_PUBLICADA_CSV:
        try:
            df_raw = pd.read_csv(URL_PUBLICADA_CSV)
        except Exception:
            df_raw = None

    # Método 2: Endpoint GViz Estándar
    if df_raw is None or df_raw.empty:
        try:
            gviz_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet=INVENTARIO"
            df_raw = pd.read_csv(gviz_url)
        except Exception:
            df_raw = None

    # Método 3: Conexión nativa st-gsheets
    if df_raw is None or df_raw.empty:
        try:
            conn = get_gsheets_connection()
            df_raw = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="INVENTARIO", ttl=0)
        except Exception:
            df_raw = None

    if df_raw is None or df_raw.empty:
        st.error("⚠️ No se pudo obtener datos de Google Sheets. Verifica haber copiado el enlace de 'Publicar en la web'.")
        return pd.DataFrame(columns=['CODIGO', 'REFERENCIA', 'DETALLE', 'STOCK_ACTUAL', 'CTO_UNIT', 'PRECIO_VENTA', 'ENTRADAS', 'SALIDAS', 'VALOR_TOTAL', 'CATEGORIA'])

    # Normalización de encabezados
    df_raw.columns = df_raw.columns.astype(str).str.strip()

    col_detalle = [c for c in df_raw.columns if 'DETALLE' in c.upper()]
    if not col_detalle:
        return pd.DataFrame(columns=['CODIGO', 'REFERENCIA', 'DETALLE', 'STOCK_ACTUAL', 'CTO_UNIT', 'PRECIO_VENTA', 'ENTRADAS', 'SALIDAS', 'VALOR_TOTAL', 'CATEGORIA'])

    detalle_col = col_detalle[0]

    # Descartar resúmenes de cartera al final de la hoja
    cutoff_idx = df_raw[df_raw[detalle_col].astype(str).str.contains('TOTAL VENTAS|TOTAL GASTOS|CARTERA CLIENTES', case=False, na=False)].index.min()
    if pd.notna(cutoff_idx):
        df = df_raw.iloc[:cutoff_idx].copy()
    else:
        df = df_raw.copy()

    df = df.dropna(subset=[detalle_col]).copy()
    df = df[df[detalle_col].astype(str).str.strip() != ''].copy()

    if df.empty:
        return pd.DataFrame(columns=['CODIGO', 'REFERENCIA', 'DETALLE', 'STOCK_ACTUAL', 'CTO_UNIT', 'PRECIO_VENTA', 'ENTRADAS', 'SALIDAS', 'VALOR_TOTAL', 'CATEGORIA'])

    df['CODIGO'] = df['CODIGO'].astype(str).str.strip() if 'CODIGO' in df.columns else ''
    df['REFERENCIA'] = df['REFERENCIA'].astype(str).str.strip() if 'REFERENCIA' in df.columns else ''
    df['DETALLE'] = df[detalle_col].astype(str).str.strip()

    # Reconciliación de Stock (Columna J 'STOCK' y Columna E '11/7/2026')
    col_stock_j = [c for c in df.columns if c.upper() == 'STOCK']
    col_stock_e = [c for c in df.columns if '11/7/2026' in c or 'INVENTARIO' in c.upper()]

    stock_j = df[col_stock_j[0]].apply(clean_numeric_val) if col_stock_j else pd.Series(0.0, index=df.index)
    stock_e = df[col_stock_e[0]].apply(clean_numeric_val) if col_stock_e else pd.Series(0.0, index=df.index)

    df['STOCK_ACTUAL'] = pd.Series([
        j if j > 0 else e for j, e in zip(stock_j, stock_e)
    ], index=df.index).astype(float)

    col_costo = [c for c in df.columns if 'CTO UNIT' in c.upper() or 'COSTO' in c.upper()]
    df['CTO_UNIT'] = df[col_costo[0]].apply(clean_numeric_val).astype(float) if col_costo else 0.0

    df['PRECIO_VENTA'] = (df['CTO_UNIT'] * 1.30).astype(float)
    df['ENTRADAS'] = df['ENTRADAS'].apply(clean_numeric_val).astype(float) if 'ENTRADAS' in df.columns else 0.0
    df['SALIDAS'] = df['SALIDAS'].apply(clean_numeric_val).astype(float) if 'SALIDAS' in df.columns else 0.0
    df['VALOR_TOTAL'] = (df['STOCK_ACTUAL'] * df['CTO_UNIT']).astype(float)

    def asignar_categoria(row):
        codigo = str(row.get('CODIGO', '')).upper()
        detalle = str(row.get('DETALLE', '')).upper()
        text = f"{codigo} {detalle}"
        
        if 'CIELO RASO' in text or 'MACHIMBRE' in text:
            return 'Cielo Raso PVC'
        elif 'PARED' in text or 'MARMOL' in text or 'PANEL' in text or 'UV' in text:
            return 'Paredes & Paneles UV'
        elif any(k in text for k in ['TORNILLO', 'CHAZO', 'OMEGA', 'PERFIL', 'ANGULO', 'CANAL', 'PERIMETRAL', 'UNION']):
            return 'Perfilería & Tornillería'
        elif any(k in text for k in ['TUBO', 'TUBERIA', 'ACCESORIO', 'CODO', 'SIFON']):
            return 'Tuberías & Accesorios'
        elif any(k in text for k in ['MANGUERA', 'AEROSOL', 'CINTA', 'ADHESIVO', 'PEGANTE', 'BROCA']):
            return 'Insumos & Ferretería'
        else:
            return 'Otros Materiales'

    df['CATEGORIA'] = df.apply(asignar_categoria, axis=1)

    cols_finales = ['CODIGO', 'REFERENCIA', 'DETALLE', 'STOCK_ACTUAL', 'CTO_UNIT', 'PRECIO_VENTA', 'ENTRADAS', 'SALIDAS', 'VALOR_TOTAL', 'CATEGORIA']
    return df[cols_finales].copy()

def guardar_movimiento_rapido_gsheets(codigo_producto, tipo_movimiento, cantidad, nuevo_costo=0.0):
    conn = get_gsheets_connection()
    df_raw = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="INVENTARIO", ttl=0)
    df_raw.columns = df_raw.columns.astype(str).str.strip()
    
    idx = df_raw[df_raw['CODIGO'] == codigo_producto].index
    if idx.empty:
        return False, "Producto no encontrado."
    
    i = idx[0]
    col_stock = 'STOCK' if 'STOCK' in df_raw.columns else df_raw.columns[4]

    curr_stock = clean_numeric_val(df_raw.loc[i, col_stock])
    curr_ent = clean_numeric_val(df_raw.loc[i, 'ENTRADAS']) if 'ENTRADAS' in df_raw.columns else 0.0
    curr_sal = clean_numeric_val(df_raw.loc[i, 'SALIDAS']) if 'SALIDAS' in df_raw.columns else 0.0

    if tipo_movimiento == "Entrada (+ Stock)":
        df_raw.loc[i, col_stock] = curr_stock + cantidad
        if 'ENTRADAS' in df_raw.columns:
            df_raw.loc[i, 'ENTRADAS'] = curr_ent + cantidad
    elif tipo_movimiento == "Salida (- Stock)":
        df_raw.loc[i, col_stock] = max(0.0, curr_stock - cantidad)
        if 'SALIDAS' in df_raw.columns:
            df_raw.loc[i, 'SALIDAS'] = curr_sal + cantidad
    elif tipo_movimiento == "Ajuste Directo de Stock":
        df_raw.loc[i, col_stock] = cantidad

    if nuevo_costo > 0 and 'CTO UNIT' in df_raw.columns:
        df_raw.loc[i, 'CTO UNIT'] = nuevo_costo

    conn.update(spreadsheet=SPREADSHEET_URL, worksheet="INVENTARIO", data=df_raw)
    load_data_from_sheets.clear()
    return True, "Movimiento guardado exitosamente en Google Sheets."

def procesar_venta_pos_gsheets(carrito_items):
    conn = get_gsheets_connection()
    df_raw = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="INVENTARIO", ttl=0)
    df_raw.columns = df_raw.columns.astype(str).str.strip()
    col_stock = 'STOCK' if 'STOCK' in df_raw.columns else df_raw.columns[4]

    id_factura = f"FAC-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    fecha_actual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    registro_ventas = []

    for item in carrito_items:
        codigo = item['CODIGO']
        cant_vendida = item['CANTIDAD']
        precio_venta = item['PRECIO_UNIT']
        subtotal = item['SUBTOTAL']

        idx = df_raw[df_raw['CODIGO'] == codigo].index
        if not idx.empty:
            i = idx[0]
            curr_stock = clean_numeric_val(df_raw.loc[i, col_stock])
            curr_salidas = clean_numeric_val(df_raw.loc[i, 'SALIDAS']) if 'SALIDAS' in df_raw.columns else 0.0

            df_raw.loc[i, col_stock] = max(0.0, curr_stock - cant_vendida)
            if 'SALIDAS' in df_raw.columns:
                df_raw.loc[i, 'SALIDAS'] = curr_salidas + cant_vendida

            registro_ventas.append({
                'ID_FACTURA': id_factura,
                'FECHA_HORA': fecha_actual,
                'CODIGO': codigo,
                'DETALLE': item['DETALLE'],
                'CANTIDAD': cant_vendida,
                'PRECIO_UNITARIO': precio_venta,
                'SUBTOTAL': subtotal
            })

    conn.update(spreadsheet=SPREADSHEET_URL, worksheet="INVENTARIO", data=df_raw)

    try:
        df_ventas_existentes = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="HISTORIAL_VENTAS", ttl=0)
        df_nuevas = pd.DataFrame(registro_ventas)
        df_final = pd.concat([df_ventas_existentes, df_nuevas], ignore_index=True)
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet="HISTORIAL_VENTAS", data=df_final)
    except Exception:
        df_nuevas = pd.DataFrame(registro_ventas)
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet="HISTORIAL_VENTAS", data=df_nuevas)

    load_data_from_sheets.clear()
    return True, id_factura

def guardar_cambios_masivos_gsheets(df_edited):
    conn = get_gsheets_connection()
    df_raw = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="INVENTARIO", ttl=0)
    df_raw.columns = df_raw.columns.astype(str).str.strip()
    col_stock = 'STOCK' if 'STOCK' in df_raw.columns else df_raw.columns[4]

    for _, row in df_edited.iterrows():
        codigo = row['CODIGO']
        if pd.notna(codigo):
            idx = df_raw[df_raw['CODIGO'] == codigo].index
            if not idx.empty:
                i = idx[0]
                df_raw.loc[i, col_stock] = row['STOCK_ACTUAL']
                if 'CTO UNIT' in df_raw.columns:
                    df_raw.loc[i, 'CTO UNIT'] = row['CTO_UNIT']
                if 'ENTRADAS' in df_raw.columns:
                    df_raw.loc[i, 'ENTRADAS'] = row['ENTRADAS']
                if 'SALIDAS' in df_raw.columns:
                    df_raw.loc[i, 'SALIDAS'] = row['SALIDAS']
                if 'DETALLE' in df_raw.columns:
                    df_raw.loc[i, 'DETALLE'] = row['DETALLE']

    conn.update(spreadsheet=SPREADSHEET_URL, worksheet="INVENTARIO", data=df_raw)
    load_data_from_sheets.clear()
    return True