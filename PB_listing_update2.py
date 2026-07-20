import streamlit as st
import pandas as pd
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
import requests

# --- 설정 ---
SHEET_ID = "1oS1KrUvgTZdrzyJ_JcP1fEOXAn_A8M53Wq-Dn4DYpvY"

ENG_CATEGORY_MAP = {
    "가공식품": "processed foods", "조미식품": "sauce & seasoning",
    "농산물": "agricultural products", "수산물": "premium seafood",
    "축산물": "livestock products", "비식품": "expendables goods",
    "ck": "central kitchen", "디저트": "Dessert", "음료": "Beverage"
}

@st.cache_resource
def register_fonts():
    pdfmetrics.registerFont(TTFont('NanumSquareEB', "NanumSquareEB.ttf"))
    pdfmetrics.registerFont(TTFont('NanumGothic', "NanumGothic.ttf"))

@st.cache_resource
def get_image_map():
    return {} 

def load_data():
    SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"
    return pd.read_csv(SHEET_URL)

def create_pdf(selected_data, image_map, items_per_page):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    target_blue = colors.HexColor("#2F75B5")
    
    MARGIN_TOP, MARGIN_BOTTOM, MARGIN_LEFT = 160, 40, 40
    PAGE_INNER_W = width - (MARGIN_LEFT * 2)
    PAGE_INNER_H = height - MARGIN_TOP - MARGIN_BOTTOM
    
    cols = 2 if items_per_page <= 4 else 3
    rows = items_per_page // cols
    cell_w, cell_h = PAGE_INNER_W / cols, PAGE_INNER_H / rows
    title_style = ParagraphStyle('ItemTitle', fontName='NanumGothic', fontSize=8, leading=11)

    for category, group in selected_data.groupby('카테고리', sort=False):
        item_idx = 0
        for _, row in group.iterrows():
            if item_idx > 0 and item_idx % items_per_page == 0: c.showPage()
            if item_idx % items_per_page == 0:
                box_h, box_y = 100, height - 35 - 100
                c.setFillColor(colors.HexColor("#F4F1EA"))
                c.rect(40, box_y, width - 80, box_h, fill=1, stroke=0)
                eng_txt = ENG_CATEGORY_MAP.get(str(category).strip(), "Product")
                c.setFont('NanumSquareEB', 13)
                c.setFillColor(target_blue)
                c.drawString(60, box_y + 65, eng_txt)
                c.setFont('NanumSquareEB', 22)
                c.setFillColor(colors.HexColor("#222222"))
                c.drawString(60, box_y + 40, f"{category} 리스트")
                c.line(60, box_y + 24, width - 60, box_y + 24)

            pos = item_idx % items_per_page
            x = MARGIN_LEFT + (pos % cols) * cell_w
            y = height - MARGIN_TOP - ((pos // cols) + 1) * cell_h
            content_x, content_w = x + 12, cell_w - 24
            
            # 1. 상품명 출력
            p_title = Paragraph(str(row.get('품목명', '')).strip(), title_style)
            p_title.wrap(content_w, cell_h)
            p_title.drawOn(c, content_x, y + 66)

            # 2. 5가지 정보 출력 (수정된 부분)
            p_code = str(row.get('품목코드', '')).strip()
            spec = str(row.get('규격/입수량', '')).strip()
            storage = str(row.get('보관방법', '')).strip()
            unit = str(row.get('발주단위', '')).strip()
            shelf_life = str(row.get('소비기한', '')).strip()
            
            c.setFont('NanumGothic', 6.5) # 글자 크기를 조금 줄여서 5개 정보 배치
            c.setFillColor(colors.black)
            c.drawString(content_x, y + 48, f"코드: {p_code} | 규격: {spec}")
            c.drawString(content_x, y + 38, f"보관: {storage}")
            c.drawString(content_x, y + 28, f"단위: {unit} | 기한: {shelf_life}")

            c.setStrokeColor(colors.darkgray)
            c.line(content_x, y + 60, content_x + content_w, y + 60)
            c.line(content_x, y + 10, content_x + content_w, y + 10)
            item_idx += 1
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --- UI ---
st.set_page_config(page_title="PB 상품 카탈로그", layout="wide")
register_fonts()
image_map = get_image_map()
st.markdown("# 📦 동원홈푸드 PB 상품 카탈로그")
df_raw = load_data()
items_per_page = st.sidebar.selectbox("페이지당 품목 수", [1, 2, 4, 6, 9], index=4)
selected_cats = st.multiselect("카테고리 선택", df_raw['카테고리'].unique(), default=df_raw['카테고리'].unique())

if selected_cats:
    filtered_df = df_raw[df_raw['카테고리'].isin(selected_cats)].copy()
    filtered_df.insert(0, '선택', True)
    final_df = st.data_editor(filtered_df, use_container_width=True, hide_index=True)
    if st.button("🚀 피드백 반영 카탈로그 빌드"):
        pdf_result = create_pdf(final_df[final_df['선택'] == True], image_map, items_per_page)
        st.download_button("💾 PB 카탈로그 다운로드", data=pdf_result, file_name="PB_Catalog.pdf", mime="application/pdf")
