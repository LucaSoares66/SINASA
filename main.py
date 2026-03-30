import streamlit as st
import geopandas as gpd
import folium
from pathlib import Path
from streamlit_folium import st_folium
import os
import s3fs
import boto3
import tempfile


s3 = boto3.client(
    "s3",
    aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
    region_name=st.secrets["AWS_DEFAULT_REGION"],
)

fs = s3fs.S3FileSystem(
    key=st.secrets["AWS_ACCESS_KEY_ID"],
    secret=st.secrets["AWS_SECRET_ACCESS_KEY"],
    client_kwargs={
        "region_name": st.secrets["AWS_DEFAULT_REGION"]
    }
)


os.environ["OGR_ENABLE_PARTIAL_REPROJECTION"] = "TRUE"

st.set_page_config(layout="wide")
st.title("Mapa de Setores Censitários - UF e Município")

PASTA_DADOS = "s3://dataiesb-luca/gpkg"

# Lista automaticamente as UFs disponíveis
arquivos = fs.glob("dataiesb-luca/gpkg/*_setores_CD2022.gpkg")
ufs_disponiveis = sorted([Path(arq).name[:2] for arq in arquivos])

# -------------------------
# FUNÇÃO 1 - Carrega só metadados (rápido)
# -------------------------
@st.cache_data(show_spinner=False)
def carregar_colunas(uf):
    caminho = f"s3://dataiesb-luca/gpkg/{uf}_setores_CD2022.gpkg"
    gdf = gpd.read_file(caminho, rows=5)
    return gdf.columns

# -------------------------
# FUNÇÃO 2 - Carrega UF completa (cache)
# -------------------------
@st.cache_data
def carregar_uf(uf):
    s3_path = f"dataiesb-luca/gpkg/{uf}_setores_CD2022.gpkg"

    with tempfile.NamedTemporaryFile(suffix=".gpkg") as tmp:
        fs.get(s3_path, tmp.name)

        gdf = gpd.read_file(tmp.name)

    if gdf.crs != "EPSG:4326":
        gdf = gdf.to_crs(epsg=4326)

    return gdf

# -------------------------
# FILTRO 1: UF
# -------------------------
uf_selecionada = st.selectbox("Selecione a UF:", ufs_disponiveis)

if uf_selecionada:
    # Descobre qual coluna é município
    colunas = carregar_colunas(uf_selecionada)

    coluna_municipio = None
    for col in "NM_MUN":
        if col in colunas:
            coluna_municipio = col
            break

    if coluna_municipio is None:
        st.error("Coluna de município não encontrada no arquivo.")
        st.write("Colunas disponíveis:", colunas)
        st.stop()

    # Carrega UF (uma vez só, com cache)
    gdf_uf = carregar_uf(uf_selecionada)

    # Lista municípios disponíveis
    municipios = sorted(gdf_uf[coluna_municipio].dropna().unique())

    # -------------------------
    # FILTRO 2: MUNICÍPIO (digitável com sugestões)
    # -------------------------
    municipio_selecionado = st.selectbox(
        "Digite ou selecione o Município:",
        municipios
    )

    # Filtra apenas o município (GRANDE ganho de performance)
    gdf = gdf_uf[gdf_uf[coluna_municipio] == municipio_selecionado].copy()

    st.success(
        f"UF: {uf_selecionada} | Município: {municipio_selecionado} | "
        f"Setores: {len(gdf):,}"
    )

    # Centro do mapa (muito mais leve que centroid complexo)
    bounds = gdf.total_bounds
    lon = (bounds[0] + bounds[2]) / 2
    lat = (bounds[1] + bounds[3]) / 2

    # Simplificação (ESSENCIAL para setores censitários)
    gdf["geometry"] = gdf["geometry"].simplify(
        tolerance=0.0002,
        preserve_topology=True
    )

    # Cria mapa
    mapa = folium.Map(
        location=[lat, lon],
        zoom_start=11,  # zoom maior porque agora é município
        tiles="cartodbpositron"
    )

    # GeoJson leve
    folium.GeoJson(
        gdf,
        name="Setores Censitários",
        style_function=lambda x: {
            "fillOpacity": 0.3,
            "weight": 0.4
        }
    ).add_to(mapa)

    st_folium(mapa, width=1200, height=700)
