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
# 💡 이미지 회전 메타데이터 보정을 위한 라이브러리 추가
from PIL import Image, ImageOps

# --- 설정 (현재 코드 기준 유지) ---
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
    except: 
        return {}

# 🛠 [수정 완료] 스마트폰 촬영 사진(EXIF 회전 데이터)을 자동으로 감지해 똑바로 세우는 다운로더
def download_image(drive_service, file_id):
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    
    try:
        # 이미지를 열어서 스마트폰 내부의 회전 값을 분석 후 정방향으로 강제 물리 회전시킵니다.
        img = Image.open(fh)
        img = ImageOps.exif_transpose(img) 
        
        # reportlab 엔진이 깨지지 않고 읽을 수 있게 다시 메모리 포맷(BytesIO)으로 변환합니다.
        out_fh = io.BytesIO()
        img.save(out_fh, format="PNG")
        out_fh.seek(0)
        return out_fh
    except:
        fh.seek(0)
        return fh

# --- PDF 생성 로직 (과거 코드 레이아웃 및 분할 적용) ---
def create_pdf(selected_data, image_map, items_per_page, drive_service):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    MARGIN_TOP = 160 
    MARGIN_BOTTOM = 40
    MARGIN_LEFT = 40
    PAGE_INNER_W = width - (MARGIN_LEFT * 2)
    PAGE_INNER_H = height - MARGIN_TOP - MARGIN_BOTTOM
    
    if items_per_page == 1: cols, rows = 1, 1
    elif items_per_page == 2: cols, rows = 1, 2
    elif items_per_page == 4: cols, rows = 2, 2
    elif items_per_page == 6: cols, rows = 2, 3
    elif items_per_page == 9: cols, rows = 3, 3 
    else: cols, rows = 3, 4 
    
    cell_w = PAGE_INNER_W / cols
    cell_h = PAGE_INNER_H / rows
    
    progress_bar = st.progress(0)
    total_items = len(selected_data)
    current_count = 0

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ItemTitle', fontName='NanumGothic', fontSize=8,
        leading=11, textColor=colors.black
    )

    eng_category_map = {
        "축산물": "Premium Meat", "수산물": "Premium Seafood", "농산물": "Premium Produce", 
        "소스류": "Premium Sauce", "디저트": "Dessert", "조미식품": "Premium Seasoning", "음료": "Beverage"
    }

    target_blue = colors.HexColor("#2F75B5") 

    if '카테고리' in selected_data.columns:
        groupby_target = '카테고리'
    else:
        groupby_target = selected_data.columns[0]

    for category, group in selected_data.groupby(groupby_target, sort=False):
        item_idx = 0
        for _, row in group.iterrows():
            if item_idx > 0 and item_idx % items_per_page == 0:
                c.showPage()
                
            if item_idx % items_per_page == 0:
                box_h = 100 
                box_y = height - 35 - box_h
                c.setFillColor(colors.HexColor("#F4F1EA"))
                c.rect(40, box_y, width - 80, box_h, fill=1, stroke=0)
                
                if os.path.exists(LOGO_PATH):
                    try:
                        c.drawImage(LOGO_PATH, width - 150, box_y + 45, width=90, height=45, preserveAspectRatio=True, mask='auto')
                    except: 
                        pass
                
                eng_txt = eng_category_map.get(str(category).strip(), "Premium Product")
                c.setFont('NanumSquareEB', 13)
                c.setFillColor(target_blue)
                c.drawString(60, box_y + 72, eng_txt)
                
                c.setFont('NanumSquareEB', 22)
                c.setFillColor(colors.HexColor("#222222"))
                c.drawString(60, box_y + 40, f"{category} 리스트")
                
                c.setStrokeColor(target_blue)
                c.setLineWidth(1.2)
                c.line(60, box_y + 24, width - 60, box_y + 24)
                
            pos = item_idx % items_per_page
            c_idx = pos % cols
            r_idx = pos // cols
            
            x = MARGIN_LEFT + (c_idx * cell_w)
            y = height - MARGIN_TOP - ((r_idx + 1) * cell_h)
            
            padding = 12
            content_x = x + padding          
            content_w = cell_w - (padding * 2) 
            
            if items_per_page == 12:
                img_box_h = cell_h * 0.40  
                title_font_size = 7.5
                spec_box_h = 44
                line_spacing = 9
            else:
                img_box_h = cell_h * 0.50
                title_font_size = 8
                spec_box_h = 52
                line_spacing = 11
                
            title_style.fontSize = title_font_size
            title_style.leading = title_font_size + 3
            
            p_code = str(row.get('품목코드', row.get('상품코드', ''))).strip()
            
            img_y = y + (cell_h - img_box_h) - 4
            if p_code in image_map:
                try:
                    img_data = download_image(drive_service, image_map[p_code])
                    img = ImageReader(img_data)
                    c.drawImage(img, content_x, img_y, 
                                width=content_w, height=img_box_h, 
                                preserveAspectRatio=True, anchor='c')
                except: pass

            item_name = str(row.get('품목명', '')).strip()
            
            if item_name.startswith('[') and ']' in item_name:
                split_idx = item_name.index(']') + 1
                brand_part = item_name[:split_idx]
                name_part = item_name[split_idx:].strip()
                formatted_name = f"{brand_part}<br/>{name_part}"
            else:
                formatted_name = item_name
                
            p_title = Paragraph(formatted_name, title_style)
            
            text_y_start = img_y - 6
            p_w, p_h = p_title.wrap(content_w, cell_h)
            p_title.drawOn(c, content_x, text_y_start - p_h)
            
            spec_box_top_y = text_y_start - p_h - 4
            spec_box_y = spec_box_top_y - spec_box_h
            
            c.setFillColor(colors.HexColor("#F8F9FA"))
            c.rect(content_x, spec_box_y, content_w, spec_box_h, fill=1, stroke=0)
            
            spec_y = spec_box_top_y - 10
            
            specs = [
                ("규격", str(row.get('규격', ''))),
                ("보관방법", str(row.get('보관방법', ''))),
                ("소비기한", str(row.get('소비기한', row.get('유통기한', '')))),
                ("상품코드", p_code)
            ]
            
            for label, val in specs:
                c.setFont('NanumGothic', 7)
                c.setFillColor(colors.HexColor("#555555"))
                c.drawString(content_x + 6, spec_y, label)
                
                c.setFont('NanumGothic', 7)
                c.setFillColor(colors.HexColor("#111111"))
                c.drawRightString(content_x + content_w - 6, spec_y, val)
                spec_y -= line_spacing

            item_idx += 1
            current_count += 1
            progress_bar.progress(min(current_count / total_items, 1.0))
            
        c.showPage()

    c.save()
    progress_bar.empty()
    buffer.seek(0)
    return buffer

# --- Streamlit UI 대시보드 마스터 ---
register_fonts()
st.set_page_config(page_title="PB 상품 카탈로그", layout="wide")

if not os.path.exists(FONT_TITLE_PATH) or not os.path.exists(FONT_BODY_PATH):
    st.error("🚨 프로젝트 폴더 내에 'NanumSquareEB.ttf' 및 'NanumGothic.ttf' 파일이 유실되었습니다.")
    st.stop()

gc, drive_service = get_gspread_client()

if gc:
    try:
        st.markdown("# 📦 동원홈푸드 PB 상품 카탈로그")
        
        with st.spinner("🔄 구글 스프레드시트 실시간 데이터 패킹 동기화 중..."):
            df_raw = load_data(gc)
            image_map = get_drive_image_map(drive_service, FOLDER_ID)
        
        with st.sidebar:
            st.header("⚙️ 레이아웃 설정")
            items_per_page = st.selectbox("페이지당 품목 수 분할", [1, 2, 4, 6, 9, 12], index=5)
            st.success("🤖 구글 및 나눔 서체 엔진 정상 세팅됨")

        if '카테고리' in df_raw.columns:
            all_categories = df_raw['카테고리'].unique()
        else:
            st.error("🚨 스프레드시트에 '카테고리' 컬럼을 찾을 수 없습니다.")
            st.stop()
        
        st.markdown("### 🎯 1. 카테고리 선택")
        selected_cats = st.multiselect("카테고리 선택", all_categories, default=all_categories, label_visibility="collapsed")
        
        if selected_cats:
            filtered_df = df_raw[df_raw['카테고리'].isin(selected_cats)].copy()
            if '선택' not in filtered_df.columns:
                filtered_df.insert(0, '선택', True)

            st.markdown("### 📝 2. 인쇄 대상 품목 관리 테이블")
            edited_df = st.data_editor(
                filtered_df,
                column_config={"선택": st.column_config.CheckboxColumn("선택", default=True)},
                use_container_width=True,
                hide_index=True
            )

            final_df = edited_df[edited_df['선택'] == True].copy()
            st.write(f"📊 현재 체크박스 선택 품목 수: **{len(final_df)}개**")

            if st.button("🚀 피드백 반영 카탈로그 빌드"):
                if final_df.empty:
                    st.warning("선택된 품목이 없으므로 인쇄 빌드를 시작할 수 없습니다.")
                else:
                    with st.spinner("🎨 나눔스퀘어 및 고화질 디자인 레이아웃 마스킹 렌더링 중..."):
                        pdf_result = create_pdf(final_df, image_map, items_per_page, drive_service)
                        
                        st.download_button(
                            label="💾 PB 카탈로그 다운로드",
                            data=pdf_result,
                            file_name="PB_Catalog.pdf",
                            mime="application/pdf"
                        )
    except Exception as e:
        st.error("⚠️ 시스템 로드 중 치명적인 에러가 발생했습니다.")
        st.code(traceback.format_exc())