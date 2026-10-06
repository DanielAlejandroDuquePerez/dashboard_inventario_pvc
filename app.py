import streamlit as st
import plotly.express as px
import pandas as pd
from src.utils import (
    load_data_from_sheets, 
    format_currency_short, 
    guardar_movimiento_rapido_gsheets, 
    guardar_cambios_masivos_gsheets,
    procesar_venta_pos_gsheets
)

# Configuración de página
st.set_page_config(
    page_title="Gestión de Inventario PVC",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Inyección de CSS Responsivo & Mobile-First
st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .stMetric {
        background-color: #1E293B;
        border: 1px solid #334155;
        padding: 14px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .stButton > button {
        min-height: 48px !important;
        border-radius: 10px !important;
        font-size: 16px !important;
        font-weight: 600 !important;
    }
    .stTextInput input, .stSelectbox div[role="combobox"], .stNumberInput input {
        min-height: 46px !important;
        font-size: 16px !important;
        border-radius: 8px !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #0F172A;
        padding: 6px;
        border-radius: 12px;
        border: 1px solid #1E293B;
        overflow-x: auto;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        white-space: nowrap;
        border-radius: 8px;
        padding: 0px 16px;
        color: #94A3B8;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1E293B !important;
        color: #0EA5E9 !important;
        border: 1px solid #0EA5E9 !important;
    }
    </style>
""", unsafe_allow_html=True)

# Cargar datos desde Google Sheets
st.cache_data.clear()
df = load_data_from_sheets()


if 'carrito' not in st.session_state:
    st.session_state.carrito = []

# SIDEBAR: FILTROS
st.sidebar.image("https://img.icons8.com/color/96/pipes.png", width=60)
st.sidebar.title("Filtros de Control")

categorias = ["Todas"] + sorted(list(df['CATEGORIA'].unique()))
cat_selected = st.sidebar.selectbox("Seleccionar Categoría", categorias, key="sidebar_categoria_select")
stock_threshold = st.sidebar.slider("Umbral Mínimo de Alerta de Stock", 0, 50, 10, key="sidebar_stock_slider")

df_filtered = df.copy()
if cat_selected != "Todas":
    df_filtered = df_filtered[df_filtered['CATEGORIA'] == cat_selected]

# ENCABEZADO
st.title("📦 Sistema de Gestión e Inventario")
st.caption("Conectado en tiempo real a Google Sheets.")

tab_pos, tab_dash, tab_rapido, tab_editor = st.tabs([
    "🛒 Caja Registradora",
    "📊 Dashboard Gerencial", 
    "⚡ Entradas / Ajustes", 
    "✏️ Editor Masivo"
])

# ==========================================
# PESTAÑA 1: CAJA REGISTRADORA (POS)
# ==========================================
with tab_pos:
    st.subheader("🛒 Punto de Venta")
    col_pos_left, col_pos_right = st.columns([1.1, 1])

    with col_pos_left:
        st.markdown("##### 1. Buscar y Seleccionar Producto")
        df_valid = df[df['STOCK_ACTUAL'] > 0].dropna(subset=['CODIGO', 'DETALLE']).copy()
        opciones_pos = [f"{row['CODIGO']} | {row['DETALLE']} (Disp: {int(row['STOCK_ACTUAL'])})" for _, row in df_valid.iterrows()]

        if opciones_pos:
            prod_pos_selected = st.selectbox("Buscar por Código o Nombre:", opciones_pos, key="pos_select_producto")
            
            if prod_pos_selected:
                cod_pos = prod_pos_selected.split(" | ")[0].strip()
                item_data = df[df['CODIGO'] == cod_pos].iloc[0]

                c_p1, c_p2, c_p3 = st.columns(3)
                with c_p1:
                    stock_disp = int(item_data['STOCK_ACTUAL'])
                    st.metric("Stock Disponible", f"{stock_disp} Unds")
                with c_p2:
                    precio_sugerido = float(item_data['CTO_UNIT'])
                    precio_venta = st.number_input("Precio ($ COP):", min_value=0.0, value=precio_sugerido, step=1000.0, key="pos_precio_input")
                with c_p3:
                    cant_venta = st.number_input("Cantidad:", min_value=1, max_value=max(1, stock_disp), value=1, step=1, key="pos_cant_input")

                if st.button("➕ Agregar al Carrito", use_container_width=True, type="secondary", key="pos_btn_add_cart"):
                    subtotal = cant_venta * precio_venta
                    existe = False
                    for item in st.session_state.carrito:
                        if item['CODIGO'] == cod_pos:
                            item['CANTIDAD'] += cant_venta
                            item['SUBTOTAL'] = item['CANTIDAD'] * item['PRECIO_UNIT']
                            existe = True
                            break
                    if not existe:
                        st.session_state.carrito.append({
                            'CODIGO': cod_pos,
                            'DETALLE': item_data['DETALLE'],
                            'CANTIDAD': cant_venta,
                            'PRECIO_UNIT': precio_venta,
                            'SUBTOTAL': subtotal
                        })
                    st.success(f"Añadido: {cant_venta} x {item_data['DETALLE']}")
                    st.rerun()
        else:
            st.warning("No hay productos con stock disponible para la venta.")

    with col_pos_right:
        st.markdown("##### 2. Carrito de Compras")
        if st.session_state.carrito:
            df_cart = pd.DataFrame(st.session_state.carrito)
            st.dataframe(
                df_cart[['DETALLE', 'CANTIDAD', 'PRECIO_UNIT', 'SUBTOTAL']],
                column_config={
                    "DETALLE": "Producto",
                    "CANTIDAD": st.column_config.NumberColumn("Cant", format="%d"),
                    "PRECIO_UNIT": st.column_config.NumberColumn("Precio", format="$%d COP"),
                    "SUBTOTAL": st.column_config.NumberColumn("Subtotal", format="$%d COP")
                },
                use_container_width=True,
                hide_index=True
            )
            total_factura = df_cart['SUBTOTAL'].sum()
            st.markdown(f"### **TOTAL: `${total_factura:,.0f} COP`**")

            btn_c1, btn_c2 = st.columns(2)
            with btn_c1:
                if st.button("🗑️ Vaciar Carrito", use_container_width=True, key="pos_btn_vaciar"):
                    st.session_state.carrito = []
                    st.rerun()

            with btn_c2:
                if st.button("✅ FACTURAR", type="primary", use_container_width=True, key="pos_btn_facturar"):
                    ok, fac_id = procesar_venta_pos_gsheets(st.session_state.carrito)
                    if ok:
                        st.balloons()
                        st.success(f"🎉 ¡Venta Guardada en Google Sheets! Factura: **{fac_id}**")
                        st.session_state.carrito = []
                        st.rerun()
        else:
            st.info("🛒 El carrito está vacío.")

# ==========================================
# PESTAÑA 2: DASHBOARD GERENCIAL
# ==========================================
with tab_dash:
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    total_articulos = int(df_filtered['STOCK_ACTUAL'].sum())
    val_total = df_filtered['VALOR_TOTAL'].sum()
    prod_bajos = df_filtered[df_filtered['STOCK_ACTUAL'] <= stock_threshold].shape[0]

    df_muerto = df_filtered[(df_filtered['STOCK_ACTUAL'] > 0) & (df_filtered['SALIDAS'] == 0)]
    cap_inmovilizado = df_muerto['VALOR_TOTAL'].sum()
    porcentaje_muerto = (cap_inmovilizado / val_total * 100) if val_total > 0 else 0

    kpi1.metric("Unidades en Bodega", f"{total_articulos:,.0f}")
    kpi2.metric("Valoración Total", format_currency_short(val_total))
    kpi3.metric("Capital Inmovilizado", format_currency_short(cap_inmovilizado), f"{porcentaje_muerto:.1f}% sin salidas", delta_color="inverse")
    kpi4.metric("Alertas de Quiebre", f"{prod_bajos} SKUs", delta_color="inverse")

    st.markdown("---")
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("📊 Valoración por Categoría")
        df_cat = df_filtered.groupby('CATEGORIA')['VALOR_TOTAL'].sum().reset_index().sort_values('VALOR_TOTAL', ascending=True)
        fig_bar = px.bar(
            df_cat,
            x='VALOR_TOTAL',
            y='CATEGORIA',
            orientation='h',
            text_auto='.2s',
            color='CATEGORIA',
            color_discrete_sequence=px.colors.qualitative.Bold,
            labels={'VALOR_TOTAL': 'Inversión ($ COP)', 'CATEGORIA': 'Categoría'}
        )
        fig_bar.update_layout(showlegend=False, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_right:
        st.subheader("🏆 Top 10 Productos en Inversión")
        
        # Conversión de seguridad a numérico
        df_filtered['VALOR_TOTAL'] = pd.to_numeric(df_filtered['VALOR_TOTAL'], errors='coerce').fillna(0.0)
        df_top10 = df_filtered.nlargest(10, 'VALOR_TOTAL').sort_values('VALOR_TOTAL', ascending=True)
        
        # Generación del gráfico de barras horizontales
        fig_top = px.bar(
            df_top10,
            x='VALOR_TOTAL',
            y='DETALLE',
            orientation='h',
            text_auto='.2s',
            color='CATEGORIA',
            color_discrete_sequence=px.colors.qualitative.Prism,
            labels={'VALOR_TOTAL': 'Valor Total ($ COP)', 'DETALLE': 'Producto'}
        )
        
        fig_top.update_layout(
            showlegend=False, 
            template="plotly_dark", 
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_top, use_container_width=True)

    st.markdown("---")
    st.subheader("🎯 Matriz de Movimiento y Rotación")
    df_scatter = df_filtered[(df_filtered['STOCK_ACTUAL'] > 0) | (df_filtered['SALIDAS'] > 0)].copy()

    if not df_scatter.empty:
        fig_scatter = px.scatter(
            df_scatter,
            x='STOCK_ACTUAL',
            y='SALIDAS',
            size='VALOR_TOTAL',
            color='CATEGORIA',
            hover_name='DETALLE',
            hover_data=['CODIGO', 'CTO_UNIT'],
            log_x=True,
            labels={'STOCK_ACTUAL': 'Stock Disponible (Unds - Escala Log)', 'SALIDAS': 'Rotación / Salidas (Unds)'},
            color_discrete_sequence=px.colors.qualitative.Vivid
        )
        fig_scatter.add_vline(x=df_scatter['STOCK_ACTUAL'].median(), line_width=1, line_dash="dash", line_color="gray")
        fig_scatter.add_hline(y=df_scatter['SALIDAS'].median(), line_width=1, line_dash="dash", line_color="gray")
        fig_scatter.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_scatter, use_container_width=True)

    st.markdown("---")
    st.subheader("📋 Tabla General de Inventario")
    search_term = st.text_input("🔍 Buscar por Código o Descripción", "", key="dash_search_input")
    
    df_display = df_filtered.copy()
    if search_term:
        df_display = df_display[
            df_display['DETALLE'].str.contains(search_term, case=False, na=False) |
            df_display['CODIGO'].str.contains(search_term, case=False, na=False)
        ]
        
    st.dataframe(
        df_display[['CODIGO', 'DETALLE', 'CATEGORIA', 'STOCK_ACTUAL', 'SALIDAS', 'CTO_UNIT', 'VALOR_TOTAL']],
        column_config={
            "CODIGO": "Código",
            "DETALLE": "Descripción del Producto",
            "CATEGORIA": "Categoría",
            "STOCK_ACTUAL": st.column_config.NumberColumn("Stock Actual", format="%d"),
            "SALIDAS": st.column_config.NumberColumn("Salidas", format="%d"),
            "CTO_UNIT": st.column_config.NumberColumn("Costo Unitario", format="$%d COP"),
            "VALOR_TOTAL": st.column_config.NumberColumn("Valor Total", format="$%d COP"),
        },
        use_container_width=True,
        hide_index=True
    )

# ==========================================
# PESTAÑA 3: REGISTRO DE ENTRADAS Y AJUSTES
# ==========================================
with tab_rapido:
    st.subheader("⚡ Registrar Entrada o Ajuste Manual")
    df_valid = df.dropna(subset=['CODIGO', 'DETALLE']).copy()
    opciones_prod = [f"{row['CODIGO']} | {row['DETALLE']}" for _, row in df_valid.iterrows()]

    with st.form("form_movimiento_rapido", clear_on_submit=True):
        prod_seleccionado = st.selectbox("1. Selecciona el Producto:", opciones_prod, key="rapido_select_producto")
        tipo_mov = st.radio("2. Tipo de Acción:", ["Entrada (+ Stock)", "Salida (- Stock)", "Ajuste Directo de Stock"], horizontal=True, key="rapido_radio_tipo")
        
        c1, c2 = st.columns(2)
        with c1:
            cantidad = st.number_input("3. Cantidad de Unidades:", min_value=1, value=1, step=1, key="rapido_cant_input")
        with c2:
            nuevo_costo = st.number_input("4. Nuevo Costo Unitario (Opcional - $ COP):", min_value=0.0, value=0.0, step=500.0, key="rapido_costo_input")

        submitted = st.form_submit_button("💾 Guardar en Google Sheets", use_container_width=True)

        if submitted and prod_seleccionado:
            codigo_prod = prod_seleccionado.split(" | ")[0].strip()
            ok, msg = guardar_movimiento_rapido_gsheets(codigo_prod, tipo_mov, cantidad, nuevo_costo)
            if ok:
                st.success(f"✅ ¡Éxito! {msg}")
                st.rerun()

# ==========================================
# PESTAÑA 4: EDITOR MASIVO (CONTADORA)
# ==========================================
with tab_editor:
    st.subheader("✏️ Editor Masivo (Estilo Excel)")
    df_editable = df_filtered[['CODIGO', 'DETALLE', 'CATEGORIA', 'STOCK_ACTUAL', 'CTO_UNIT', 'ENTRADAS', 'SALIDAS']].copy()

    edited_df = st.data_editor(
        df_editable,
        column_config={
            "CODIGO": st.column_config.TextColumn("Código", disabled=True),
            "DETALLE": st.column_config.TextColumn("Descripción"),
            "CATEGORIA": st.column_config.TextColumn("Categoría", disabled=True),
            "STOCK_ACTUAL": st.column_config.NumberColumn("Stock Actual", format="%d"),
            "CTO_UNIT": st.column_config.NumberColumn("Costo Unitario ($ COP)", format="$%d"),
            "ENTRADAS": st.column_config.NumberColumn("Entradas", format="%d"),
            "SALIDAS": st.column_config.NumberColumn("Salidas", format="%d"),
        },
        use_container_width=True,
        hide_index=True,
        key="editor_masivo_data_table"
    )

    if st.button("💾 Guardar Cambios Masivos en Google Sheets", type="primary", use_container_width=True, key="btn_guardar_masivo"):
        guardar_cambios_masivos_gsheets(edited_df)
        st.success("✅ ¡Todos los cambios han sido guardados en Google Sheets!")
        st.rerun()