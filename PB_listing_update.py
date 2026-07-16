import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io, os
import traceback
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from PIL import Image, ImageOps

# --- 설정 ---
JSON_KEY_FILE = "key.json"
LOGO_PATH = "logo.png"
FONT_TITLE_PATH = "NanumSquareEB.ttf"
FONT_BODY_PATH = "NanumGothic.ttf"
SHEET_ID = "1oS1KrUvgTZdrzyJ_JcP1fEOXAn_A8M53Wq-Dn4DYpvY"
FOLDER_ID = "1eVBsfZMHL6vBfuwWBLvlR5rNXX9l4BM0"

# --- 폰트 및 초기화 함수 ---
@st.cache_resource
def register_fonts():
    pdfmetrics.registerFont(TTFont('NanumSquareEB', FONT_TITLE_PATH))
    pdfmetrics.registerFont(TTFont('NanumGothic', FONT_BODY_PATH))

@st.cache_resource
def get_gspread_client():
    creds = Credentials.from_service_account_file(JSON_KEY_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
    return gspread.authorize(creds), build('drive', 'v3', credentials=creds)

def load_data(gc):
    df = pd.DataFrame(gc.open_by_key(SHEET_ID).get_worksheet(0).get_all_records())
    df.columns = [str(col).strip() for col in df.columns]
    return df

def get_drive_image_map(drive_service, folder_id):
    file_map = {}
    page_token = None
    try:
        while True:
            results = drive_service.files().list(
                q=f"'{folder_id}' in parents and mimeType contains 'image/' and trashed = false",
                fields="nextPageToken, files(id, name)",
                pageSize=1000,
                pageToken=page_token
            ).execute()
            for f in results.get('files', []):
                file_map[os.path.splitext(f['name'])[0].strip()] = f['id']
            page_token = results.get('nextPageToken')
            if not page_token: break
        return file_map
    except: return {}

def download_image(drive_service, file_id):
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False: status, done = downloader.next_chunk()
    fh.seek(0)
    try:
        img = Image.open(fh)
        img = ImageOps.exif_transpose(img) 
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        else: img = img.convert('RGB')
        out_fh = io.BytesIO()
        img.save(out_fh, format="PNG")
        out_fh.seek(0)
        return out_fh
    except:
        fh.seek(0)
        return fh

# --- PDF 생성 로직 ---
def create_pdf(selected_data, image_map, items_per_page, drive_service):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    MARGIN_TOP, MARGIN_BOTTOM, MARGIN_LEFT = 160, 40, 40
    PAGE_INNER_W = width - (MARGIN_LEFT * 2)
    PAGE_INNER_H = height - MARGIN_TOP - MARGIN_BOTTOM
    
    if items_per_page == 1: cols, rows = 1, 1
    elif items_per_page == 2: cols, rows = 1, 2
    elif items_per_page == 4: cols, rows = 2, 2
    elif items_per_page == 6: cols, rows = 2, 3
    elif items_per_page == 9: cols, rows = 3, 3 
    else: cols, rows = 3, 4 
    
    cell_w, cell_h = PAGE_INNER_W / cols, PAGE_INNER_H / rows
    progress_bar = st.progress(0)
    total_items = len(selected_data)
    current_count = 0
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ItemTitle', fontName='NanumGothic', fontSize=8, leading=11, textColor=colors.black)
    target_blue = colors.HexColor("#2F75B5") 

    for category, group in selected_data.groupby('카테고리' if '카테고리' in selected_data.columns else selected_data.columns[0], sort=False):
        item_idx = 0
        for _, row in group.iterrows():
            if item_idx > 0 and item_idx % items_per_page == 0: c.showPage()
            if item_idx % items_per_page == 0:
                box_h = 100 
                box_y = height - 35 - box_h
                c.setFillColor(colors.HexColor("#F4F1EA"))
                c.rect(40, box_y, width - 80, box_h, fill=1, stroke=0)
                if os.path.exists(LOGO_PATH):
                    try: c.drawImage(LOGO_PATH, width - 150, box_y + 45, width=90, height=45, preserveAspectRatio=True, mask='auto')
                    except: pass
                c.setFont('NanumSquareEB', 22)
                c.setFillColor(colors.HexColor("#222222"))
                c.drawString(60, box_y + 40, f"{category} 리스트")
                c.setStrokeColor(target_blue)
                c.setLineWidth(1.2)
                c.line(60, box_y + 24, width - 60, box_y + 24)
                
            pos = item_idx % items_per_page
            c_idx, r_idx = pos % cols, pos // cols
            x = MARGIN_LEFT + (c_idx * cell_w)
            y = height - MARGIN_TOP - ((r_idx + 1) * cell_h)
            padding = 12
            content_x = x + padding          
            content_w = cell_w - (padding * 2) 
            
           # --- 수정된 좌표 계산 로직 ---
            p_code = str(row.get('품목코드', row.get('상품코드', ''))).strip()
            
            # 1. 정보 박스(56px)를 셀 하단에서 10px 띄워서 고정 배치
            spec_box_h = 56
            spec_box_y = y + 10 
            
            # 2. 상품명 텍스트 박스 계산
            item_name = str(row.get('품목명', '')).strip()
            formatted_name = f"{item_name[:item_name.index(']')+1]}<br/>{item_name[item_name.index(']')+1:].strip()}" if item_name.startswith('[') and ']' in item_name else item_name
            p_title = Paragraph(formatted_name, title_style)
            p_w, p_h = p_title.wrap(content_w, cell_h)
            
            # 3. 상품명을 정보 박스 위 5px 지점에 배치
            name_y = spec_box_y + spec_box_h + 5
            
            # 4. 이미지 배치는 상품명 위쪽 공간을 활용
            img_y = name_y + p_h + 5
            img_box_h = (y + cell_h) - img_y - 10 # 셀 상단 여백 고려
            
            # 그리기 실행 (순서: 이미지 -> 상품명 -> 정보박스)
            if p_code in image_map:
                try:
                    img_data = download_image(drive_service, image_map[p_code])
                    # 핵심: 이미지의 가로/세로 비율을 유지하면서 주어진 박스(content_w, img_box_h)에 맞춤
                    # anchor='c'를 통해 박스의 정중앙에 이미지를 위치시킵니다.
                    c.drawImage(
                        ImageReader(img_data), 
                        content_x, 
                        img_y, 
                        width=content_w, 
                        height=img_box_h, 
                        preserveAspectRatio=True, 
                        anchor='c'
                    )
                except Exception as e:
                    print(f"이미지 출력 오류: {e}")

            # 상품명을 이미지 위가 아닌, 위에서 계산한 name_y(이미지 아래)에 배치
            p_title.drawOn(c, content_x, name_y)
            
            # 정보 박스 및 테두리 그리기
            c.setFillColor(colors.white)
            c.rect(content_x, spec_box_y, content_w, spec_box_h, fill=1, stroke=0)
            
            c.setStrokeColor(colors.darkgray)
            c.setLineWidth(0.7)
            c.line(content_x, spec_box_y + spec_box_h, content_x + content_w, spec_box_y + spec_box_h) # 위선
            c.line(content_x, spec_box_y, content_x + content_w, spec_box_y) # 아래선
            
            # 기존 코드 (수정 전)
            # specs = [
            #     ("규격", str(row.get('규격', ''))),
            #     ...
            # ]
            
            # 수정된 코드 (수정 후)
            spec_y = spec_box_y + spec_box_h - 12
            specs = [
                ("규격", str(row.get('규격/입수량', ''))), # '규격' 대신 '규격/입수량'으로 변경
                ("보관방법", str(row.get('보관방법', ''))),
                ("소비기한", str(row.get('소비기한', row.get('유통기한', '')))),
                ("상품코드", p_code)
            ]
            
            for label, val in specs:
                c.setFont('NanumGothic', 7)
                c.setFillColor(colors.black)
                c.drawString(content_x + 8, spec_y, label)
                c.setFont('NanumSquareEB', 7)
                c.setFillColor(colors.black)
                c.drawRightString(content_x + content_w - 8, spec_y, val)
                spec_y -= 12

            item_idx += 1
            current_count += 1
            progress_bar.progress(min(current_count / total_items, 1.0))
        c.showPage()
    c.save()
    progress_bar.empty()
    buffer.seek(0)
    return buffer

# --- Streamlit UI ---
register_fonts()
st.set_page_config(page_title="PB 상품 카탈로그", layout="wide")
gc, drive_service = get_gspread_client()
st.markdown("# 📦 동원홈푸드 PB 상품 카탈로그")
df_raw = load_data(gc)
image_map = get_drive_image_map(drive_service, FOLDER_ID)
items_per_page = st.sidebar.selectbox("페이지당 품목 수", [1, 2, 4, 6, 9, 12], index=5)
selected_cats = st.multiselect("카테고리 선택", df_raw['카테고리'].unique(), default=df_raw['카테고리'].unique())

if selected_cats:
    filtered_df = df_raw[df_raw['카테고리'].isin(selected_cats)].copy()
    filtered_df.insert(0, '선택', True)
    final_df = st.data_editor(filtered_df, column_config={"선택": st.column_config.CheckboxColumn("선택", default=True)}, use_container_width=True, hide_index=True)
    if st.button("🚀 피드백 반영 카탈로그 빌드"):
        pdf_result = create_pdf(final_df[final_df['선택'] == True], image_map, items_per_page, drive_service)
        st.download_button("💾 PB 카탈로그 다운로드", data=pdf_result, file_name="PB_Catalog.pdf", mime="application/pdf")