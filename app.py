import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from pivottablejs import pivot_ui
import plotly.express as px
import streamlit.components.v1 as components
import tempfile
#instalar stremlit-aggrid   
from st_aggrid import AgGrid
st.set_page_config(page_title="Dashboard OLAP por Ciudad y Producto", layout="wide")
st.subheader("📊 OLAP – Ventas por Ciudad, Producto y Fecha")

# Conexión PostgreSQL
@st.cache_resource
def get_engine():
    user = "ventas_dw_user"
    password = "fYZ3oUwPYKihSRAoPvp2gShf0fZW2o8m"
    host = "dpg-d1jbkinfte5s73eorhi0-a.oregon-postgres.render.com"
    port = "5432"
    database = "ventas_dw"
    engine = create_engine(f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}")
    return engine

# Carga de datos
@st.cache_data
def cargar_datos(_engine):
    query = """
    SELECT
        c.ciudad,
        p.numero_articulo,
        EXTRACT(YEAR FROM t.fecha) AS anio,
        EXTRACT(MONTH FROM t.fecha) AS mes,
        SUM(f.cantidad) AS cantidad,
        SUM(f.total_bs) AS total
    FROM fact_ventas f
    JOIN dim_cliente c ON f.id_cliente = c.id_cliente
    JOIN dim_producto p ON f.id_producto = p.id_producto
    JOIN dim_tiempo t ON f.id_fecha = t.id_fecha
    WHERE p.numero_articulo IN (
        SELECT p.numero_articulo
        FROM fact_ventas f
        JOIN dim_producto p ON f.id_producto = p.id_producto
        GROUP BY p.numero_articulo
        HAVING count(f.cantidad) > 600
    )
    GROUP BY
        c.ciudad,
        p.numero_articulo,
        EXTRACT(YEAR FROM t.fecha),
        EXTRACT(MONTH FROM t.fecha)
    ORDER BY
        c.ciudad, anio, mes, cantidad DESC;
    """
    df = pd.read_sql(query, _engine)
    return df

# Cargar datos
engine = get_engine()
df = cargar_datos(engine)

# Filtros en Sidebar
st.sidebar.header("🔍 Filtros")
ciudades = sorted(df["ciudad"].dropna().unique())
productos = sorted(df["numero_articulo"].dropna().unique())
anios = sorted(df["anio"].dropna().unique())

ciudad_sel = st.sidebar.multiselect("Ciudad", ciudades, default=ciudades)
producto_sel = st.sidebar.multiselect("Producto", productos)
anio_sel = st.sidebar.multiselect("Año", anios, default=anios)

if not producto_sel:
    producto_sel = productos

# Filtrar datos
df_filtrado = df[
    (df["ciudad"].isin(ciudad_sel)) &
    (df["numero_articulo"].isin(producto_sel)) &
    (df["anio"].isin(anio_sel))
]

# Añadir columna fecha y codificar para cubo 3D
df_filtrado["fecha"] = df_filtrado["anio"].astype(str) + "-" + df_filtrado["mes"].astype(str).str.zfill(2)
df_filtrado["x_ciudad"] = df_filtrado["ciudad"].astype("category").cat.codes
df_filtrado["y_producto"] = df_filtrado["numero_articulo"].astype("category").cat.codes
df_filtrado["z_fecha"] = df_filtrado["fecha"].astype("category").cat.codes

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🧊 Cubo OLAP 3D", "📌 Pivot Table Interactiva", "📈 Datos Tabla"])

# ---------------- TAB 1: Dashboard ----------------
with tab1:
    st.subheader("📈 Indicadores Clave")
    col1, col2, col3 = st.columns(3)
    col1.metric("Ventas Totales", f"{df_filtrado['total'].sum():,.2f} Bs")
    col2.metric("Cantidad Total", df_filtrado["cantidad"].sum())
    col3.metric("Registros", df_filtrado.shape[0])

    st.subheader("🏙️ Ventas por Ciudad")
    fig1 = px.bar(df_filtrado.groupby("ciudad")["total"].sum().reset_index(),
                  x="ciudad", y="total", color="ciudad", title="Total Bs por Ciudad")
    st.plotly_chart(fig1, use_container_width=True)

    st.subheader("📅 Ventas por Mes y Año")
    df_time = df_filtrado.groupby(["anio", "mes"])["total"].sum().reset_index()
    fig2 = px.line(df_time, x="mes", y="total", color="anio", markers=True, title="Ventas por Mes")
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("🗺️ Ventas Totales por Ciudad y Producto (TreeMap)")
    df_tree = df_filtrado.groupby(["ciudad", "numero_articulo"])["total"].sum().reset_index()
    fig_tree = px.treemap(df_tree,
                          path=["ciudad", "numero_articulo"],
                          values="total",
                          color="ciudad",
                          title="Distribución de Ventas por Ciudad y Producto")
    st.plotly_chart(fig_tree, use_container_width=True)

# ---------------- TAB 2: Cubo OLAP 3D ----------------
with tab2:
    st.subheader("🧊 Cubo OLAP 3D Interactivo")
    medida = st.selectbox("Selecciona la medida:", ["total", "cantidad"], key="medida_3d")
    fig_cubo = px.scatter_3d(
        df_filtrado,
        x="x_ciudad",
        y="y_producto",
        z="z_fecha",
        color=medida,
        size=medida,
        hover_data=["ciudad", "numero_articulo", "fecha", "cantidad", "total"],
        color_continuous_scale="Viridis"
    )
    fig_cubo.update_layout(
        scene=dict(
            xaxis=dict(title="Ciudad", tickvals=df_filtrado["x_ciudad"], ticktext=df_filtrado["ciudad"]),
            yaxis=dict(title="Producto", tickvals=df_filtrado["y_producto"], ticktext=df_filtrado["numero_articulo"]),
            zaxis=dict(title="Fecha", tickvals=df_filtrado["z_fecha"], ticktext=df_filtrado["fecha"]),
        ),
        margin=dict(l=0, r=0, t=0, b=0)
    )
    st.plotly_chart(fig_cubo, use_container_width=True)

# ---------------- TAB 3: Pivot Table ----------------
with tab3:
    st.subheader("📌 Tabla OLAP (Pivot Interactiva)")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as f:
        pivot_ui(df_filtrado, outfile_path=f.name)
        with open(f.name, "r", encoding="utf-8") as file:
            html_content = file.read()
        components.html(html_content, height=600, scrolling=True)
with tab4:
    st.subheader("📈 Tabla OLAP (Datos)")
    AgGrid(df_filtrado, enable_enterprise_modules=True, height=600)

