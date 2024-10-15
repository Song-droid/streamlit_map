import os
import json
import pandas as pd
import folium
from folium.plugins import MarkerCluster
import streamlit as st
from io import BytesIO
import base64
import requests
import numpy as np

# Streamlit 앱 설정
st.title("부산광역시 설계공모 당선작 지도")
st.markdown("엑셀 파일을 업로드하여 건물 정보의 위치와 사진을 지도에 표시합니다.")

# 데이터프레임 초기화
df = pd.DataFrame()

# 사이드바에서 엑셀 파일 업로드
uploaded_file = st.sidebar.file_uploader("건물 정보가 담긴 엑셀 파일을 업로드하세요.", type=["xlsx"])

# 사이드바에서 사진 파일 업로드
uploaded_images = st.sidebar.file_uploader("사진 파일을 업로드하세요.", type=["jpg", "png"], accept_multiple_files=True)

# GeoJSON URL
geojson_base_url = "https://raw.githubusercontent.com/raqoon886/Local_HangJeongDong/master/hangjeongdong_부산광역시.geojson"
response = requests.get(geojson_base_url)

if response.status_code == 200:
    geojson_data = response.json()
else:
    st.error("GeoJSON 파일을 불러오는 데 오류가 발생했습니다.")
    st.stop()

# Mapping `시군구` names to `sgg` codes
sgg_mapping = {
    "중구": "26110",
    "서구": "26140",
    "동구": "26170",
    "영도구": "26200",
    "부산진구": "26230",
    "동래구": "26260",
    "남구": "26290",
    "북구": "26320",
    "해운대구": "26350",
    "사하구": "26380",
    "금정구": "26410",
    "강서구": "26440",
    "연제구": "26470",
    "수영구": "26500",
    "사상구": "26530",
    "기장군": "26710"
}

# 각 시군구에 대한 색상 매핑
sgg_color_mapping = {
    "26110": "lightblue",
    "26140": "lightgreen",
    "26170": "yellow",
    "26200": "pink",
    "26230": "orange",
    "26260": "purple",
    "26290": "lightcoral",
    "26320": "lightcyan",
    "26350": "lightgrey",
    "26380": "plum",
    "26410": "salmon",
    "26440": "khaki",
    "26470": "peachpuff",
    "26500": "lavender",
    "26530": "mistyrose",
    "26710": "lightsteelblue"
}

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)

        # 데이터 검증: 필요한 열이 존재하는지 확인
        required_columns = ['사업명', '주소', '시군구', '용도', '대지면적', '연면적', '총사업비', '설계자', '당선작 발표', '위도', '경도', '사진 경로']
        if not all(col in df.columns for col in required_columns):
            st.error("엑셀 파일에 필수 열이 없습니다.")
        else:
            st.write("업로드된 데이터:")
            st.write(df)

            # 위도와 경도 열의 데이터 형식을 숫자형으로 변환 (문자열이 있으면 NaN으로 처리)
            df['위도'] = pd.to_numeric(df['위도'], errors='coerce')
            df['경도'] = pd.to_numeric(df['경도'], errors='coerce')

            # 유효하지 않은 위도 및 경도 행 제거
            df = df.dropna(subset=['위도', '경도'])

            # 필터 옵션 추출
            시군구_options = df['시군구'].unique().tolist()
            용도_options = df['용도'].unique().tolist()

    except Exception as e:
        st.error(f"엑셀 파일을 읽는 중 오류 발생: {e}")

    # '부산시 전체' 옵션을 추가
    selected_시군구 = st.sidebar.multiselect("시군구 선택 (부산시 전체 포함)", ['부산시 전체'] + 시군구_options)
    selected_용도 = st.sidebar.multiselect("용도 선택", 용도_options)

    # Convert selected `시군구` names to their corresponding `sgg` codes
    selected_sgg_codes = []
    if "부산시 전체" in selected_시군구:
        selected_sgg_codes = list(sgg_mapping.values())
    else:
        selected_sgg_codes = [sgg_mapping[sgg] for sgg in selected_시군구 if sgg in sgg_mapping]

    # 필터링
    filtered_df = df.copy()

    if selected_시군구:
        if "부산시 전체" in selected_시군구:
            filtered_df = filtered_df
        else:
            filtered_df = filtered_df[filtered_df['시군구'].isin(selected_시군구)]

    if selected_용도:
        filtered_df = filtered_df[filtered_df['용도'].isin(selected_용도)]

    # 초기 지도 생성
    initial_zoom_level = 11
    map_center = [df['위도'].mean(), df['경도'].mean()]
    map = folium.Map(location=map_center, zoom_start=initial_zoom_level, tiles='cartodbpositron')

    if not filtered_df.empty:
        # 선택된 시군구에 대한 GeoJSON 레이어 추가
        geojson_features = []
        for feature in geojson_data['features']:
            if feature['properties']['sgg'] in selected_sgg_codes:
                geojson_features.append(feature)

        filtered_geojson_data = {
            "type": "FeatureCollection",
            "features": geojson_features
        }

        folium.GeoJson(
            filtered_geojson_data,
            name='자치구',
            style_function=lambda feature: {
                'fillColor': sgg_color_mapping.get(feature['properties']['sgg'], 'gray'),
                'color': 'white',
                'weight': 1.4,
                'fillOpacity': 0.4
            }
        ).add_to(map)

        # 시군구별 평균 위치 계산 및 마커 추가
        sgg_mean_positions = {}

        for feature in filtered_geojson_data['features']:
            sgg_code = feature['properties']['sgg']
            if sgg_code not in sgg_mean_positions:
                sgg_mean_positions[sgg_code] = []

            polygons = feature['geometry']['coordinates']
            for polygon in polygons:
                coordinates = np.array(polygon[0])  # 첫 번째 링을 선택
                sgg_mean_positions[sgg_code].extend(coordinates)

        # Zoom Level에 기반한 폰트 크기 계산 함수
        def get_font_size(zoom_level):
            if zoom_level <= 10:
                return "14px"
            elif zoom_level <= 12:
                return "10px"
            else:
                return "8px"

        # 시군구별 평균 좌표 계산 및 마커 추가
        for sgg_code, coordinates in sgg_mean_positions.items():
            avg_coordinates = np.mean(coordinates, axis=0)
            mean_latitude = avg_coordinates[1]
            mean_longitude = avg_coordinates[0]

            sgg_name = [feature['properties'].get('sggnm', 'Unknown') for feature in filtered_geojson_data['features'] if feature['properties']['sgg'] == sgg_code]

            # 초기 줌 레벨을 사용한 폰트 크기 설정
            folium.Marker(
                location=[mean_latitude, mean_longitude],
                popup=None,
                icon=folium.DivIcon(
                    html=f"<div style='font-size: {get_font_size(initial_zoom_level)}; color: gray; letter-spacing: 0.2px; font-weight: bold; opacity: 0.7;'><b>{sgg_name[0]}</b></div>"
                )
            ).add_to(map)

        # 이미지 업로드된 파일을 사전형으로 변환
        image_dict = {}
        if uploaded_images:
            for img in uploaded_images:
                image_dict[img.name] = img.read()

        # 시군구별 MarkerCluster 생성
        clusters = {}
        for idx, row in filtered_df.iterrows():
            if pd.notnull(row['위도']) and pd.notnull(row['경도']):
                sgg_code = sgg_mapping[row['시군구']]

                # 클러스터가 생성되지 않았다면 추가
                if sgg_code not in clusters:
                    clusters[sgg_code] = MarkerCluster(
                        max_cluster_radius=75,
                        showCoverageOnHover=False,
                        icon_create_function="""
                            function (cluster) {
                                return new L.DivIcon({
                                    html: '<div style="background-color: lightblue; border-radius: 50%; width: 30px; height: 30px; text-align: center; line-height: 30px; font-size: 12px;">' + 
                                          cluster.getChildCount() + 
                                          '</div>',
                                    className: 'my-div',
                                    iconSize: L.point(30, 30)
                                });
                            }
                        """ 
                    )
                    clusters[sgg_code].add_to(map)

                # Popup 내용 생성
                image_name = row['사진 경로']
                img_data = image_dict.get(image_name)
                all_images_html = ""

                if img_data is not None:
                    img_base64 = base64.b64encode(img_data).decode()
                    all_images_html += f"<img src='data:image/jpeg;base64,{img_base64}' style='width:100px; height:auto;'>"

                # Popup 내용 생성
                popup_text = (f"<div style='font-family: sans-serif; font-size: 12px;'>"
                              f"<b>[사업명] {row['사업명']}</b><br>"
                              f"[주소] {row['주소']}<br>"
                              f"[용도] {row['용도']}<br>"
                              f"[대지면적] {row['대지면적']} m²<br>"
                              f"[연면적] {row['연면적']} m²<br>"
                              f"[총사업비] {row['총사업비']:,} 원<br>"
                              f"[설계자] {row['설계자']}<br>"
                              f"[당선작 발표] {row['당선작 발표']}<br>"
                              f"</div>"
                              f"<div style='padding-top: 5px;'>"
                              f"{all_images_html}"
                              f"</div>")

                folium.Marker(location=[row['위도'], row['경도']],
                              popup=folium.Popup(popup_text, max_width=300),
                              tooltip=f"사업명: {row['사업명']}").add_to(clusters[sgg_code])

        # HTML 파일을 메모리에서 바이너리로 저장
        html_data = BytesIO()
        map.save(html_data, close_file=False)

        # HTML 데이터를 Streamlit에 표시
        st.components.v1.html(html_data.getvalue().decode('utf-8'), height=500)

        # 다운로드 버튼
        st.download_button(label="HTML 파일 다운로드",
                           data=html_data.getvalue(),
                           file_name="map.html",
                           mime="text/html")
    else:
        st.write("선택한 조건에 대한 정보가 없습니다.")
