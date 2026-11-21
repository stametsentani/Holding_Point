import streamlit as st
import requests
import datetime
from PIL import Image, ImageDraw, ImageFont
import io
import os
import math
from collections import Counter

# Setup Halaman Streamlit
st.set_page_config(page_title="QC & Auto Holding Area Forecast", layout="wide")
st.title("🛫 Toare Holding Area Forecast")
st.caption("Stasiun Meteorologi Kelas I Sentani - Jayapura")

# --- FUNGSI HELPER ---
def send_to_whatsapp_bot(image_bytes, target_id, caption=""):
    url = "http://127.0.0.1:3000/send-infographic"
    files = {"image": ("holding.png", image_bytes, "image/png")}
    data = {"target": target_id, "caption": caption}
    try:
        res = requests.post(url, files=files, data=data, timeout=15)
        return res.status_code == 200
    except Exception as e:
        return False

def get_cardinal_direction(degree):
    if degree is None:
        return "N/A"
    dirs = ["NORTH", "NORTH EAST", "EAST", "SOUTH EAST", "SOUTH", "SOUTH WEST", "WEST", "NORTH WEST"]
    idx = int((degree + 22.5) // 45) % 8
    return dirs[idx]

def map_wmo_code(code):
    wmo_map = {
        0: "SUNNY",                           # Clear sky
        1: "PARTLY CLOUD", 2: "PARTLY CLOUD", # Mainly clear, Partly cloudy
        3: "CLOUDY",                          # Overcast
        51: "LOCAL RAIN", 53: "LOCAL RAIN", 55: "LOCAL RAIN", # Drizzle
        61: "LOCAL RAIN",                     # Rain: Slight
        63: "MODERATE RAIN",                  # Rain: Moderate
        65: "HEAVY RAIN",                     # Rain: Heavy (Perbaikan)
        66: "MODERATE RAIN", 67: "HEAVY RAIN",# Freezing Rain
        80: "LOCAL RAIN",                     # Rain showers: Slight
        81: "MODERATE RAIN",                  # Rain showers: Moderate
        82: "HEAVY RAIN",                     # Rain showers: Violent/Heavy
        95: "RAIN & TS", 96: "RAIN & TS",     # Thunderstorm with slight/moderate rain
        99: "THUNDERSTORM (TS)"               # Thunderstorm with heavy hail/rain
    }
    return wmo_map.get(code, "PARTLY CLOUD")

def get_dominant_element(lst):
    valid_lst = [x for x in lst if x is not None]
    if not valid_lst:
        return None
    counts = Counter(valid_lst)
    return counts.most_common(1)[0][0]

def calculate_vector_avg_wind(hourly, speed_key, dir_key, hours_range):
    speeds_all = hourly.get(speed_key) or hourly.get(speed_key.lower()) or hourly.get(speed_key.replace("hPa", "hpa")) or []
    dirs_all = hourly.get(dir_key) or hourly.get(dir_key.lower()) or hourly.get(dir_key.replace("hPa", "hpa")) or []
    
    u_list, v_list = [], []
    for h in hours_range:
        if len(speeds_all) > h and len(dirs_all) > h:
            s = speeds_all[h]
            d = dirs_all[h]
            if s is not None and d is not None:
                rad = math.radians(d)
                u = -s * math.sin(rad)
                v = -s * math.cos(rad)
                u_list.append(u)
                v_list.append(v)
                
    if not u_list:
        return "CALM"
        
    avg_u = sum(u_list) / len(u_list)
    avg_v = sum(v_list) / len(v_list)
    avg_speed = math.sqrt(avg_u**2 + avg_v**2)
    
    if avg_speed < 1:
        return "CALM"
        
    avg_dir_rad = math.atan2(-avg_u, -avg_v)
    avg_dir_deg = (math.degrees(avg_dir_rad)) % 360
    
    cardinal = get_cardinal_direction(avg_dir_deg)
    return f"{cardinal} AT {round(avg_speed)} KTS"

def fetch_open_meteo(lat, lon, date_str):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": [
            "weather_code",
            "visibility",
            "wind_speed_850hPa",
            "wind_direction_850hPa",
            "wind_speed_700hPa",
            "wind_direction_700hPa",
            "wind_speed_500hPa",
            "wind_direction_500hPa"
        ],
        "wind_speed_unit": "kn",
        "timezone": "Asia/Jayapura",
        "start_date": date_str,
        "end_date": date_str
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        if res.status_code != 200:
            err_msg = res.json().get("reason", res.text)
            st.error(f"Gagal mengambil data ({res.status_code}): {err_msg}")
            return None
        return res.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Gagal menghubungi server Open-Meteo: {e}")
        return None

def render_infographic(template_path, data):
    if not os.path.exists(template_path):
        st.error(f"⚠️ Template gambar '{template_path}' tidak ditemukan di direktori kerja.")
        return None

    img = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    
    font_path = "Poppins-Bold.ttf"
    if os.path.exists(font_path):
        font_date = ImageFont.truetype(font_path, 16)
        font_wind = ImageFont.truetype(font_path, 14)
        font_vis  = ImageFont.truetype(font_path, 22)
    else:
        try:
            font_date = ImageFont.truetype("arialbd.ttf", 16)
            font_wind = ImageFont.truetype("arialbd.ttf", 14)
            font_vis  = ImageFont.truetype("arialbd.ttf", 22)
        except:
            font_date = font_wind = font_vis = ImageFont.load_default()

    def format_multiline_wind(text):
        if " AT " in text and "\n" not in text:
            return text.replace(" AT ", "\nAT ")
        return text

    # 1. Publication Date Header
    draw.text((710, 111), data["validity"], fill="white", font=font_date)

    # 2. Weather Icon Mapping Sesuai Legenda
    weather_icon_map = {
        "SUNNY": "icons/sunny.png",
        "PARTLY CLOUD": "icons/partly_cloud.png",
        "CLOUDY": "icons/cloudy.png",
        "LOCAL RAIN": "icons/local_rain.png",
        "MODERATE RAIN": "icons/moderate_rain.png",
        "HEAVY RAIN": "icons/heavy_rain.png",
        "RAIN & TS": "icons/rain_ts.png",
        "THUNDERSTORM (TS)": "icons/thunderstorm.png"
    }

    icon_file = weather_icon_map.get(data["weather"])
    if icon_file and os.path.exists(icon_file):
        icon_img = Image.open(icon_file).convert("RGBA")
        icon_size = (90, 90)
        icon_img = icon_img.resize(icon_size)
        
        pos_x = 600 - (icon_size[0] // 2)
        pos_y = 615 - (icon_size[1] // 2)
        
        img.paste(icon_img, (pos_x, pos_y), icon_img)
    else:
        draw.text((700, 615), data["weather"], fill="white", font=font_vis, anchor="mm")

    # Visibility
    draw.text((425, 715), data["visibility"], fill="white", font=font_vis, anchor="mm")

    # 3. Profil Angin per FL
    draw.text((1220, 320), format_multiline_wind(data["wind_fl180"]), fill="white", font=font_wind, anchor="mm", align="center")
    draw.text((1030, 500), format_multiline_wind(data["wind_fl100"]), fill="white", font=font_wind, anchor="mm", align="center")
    draw.text((1220, 700), format_multiline_wind(data["wind_fl050"]), fill="white", font=font_wind, anchor="mm", align="center")

    return img

# --- SIDEBAR KONFIGURASI ---
st.sidebar.header("📍 Parameter Stasiun")

today = datetime.date.today()
max_date = today + datetime.timedelta(days=3)

target_date = st.sidebar.date_input(
    "Tanggal Prediksi",
    value=today,
    min_value=today,
    max_value=max_date
)

holding_point = "TOARE"
lat = -2.7712
lon = 140.6246

st.sidebar.markdown(f"**Holding Point:** {holding_point}")
st.sidebar.markdown(f"**Koordinat:** {lat}, {lon}")

# --- STATE STORAGE QC ---
if "qc_data" not in st.session_state:
    st.session_state.qc_data = None
if "downloaded_date" not in st.session_state:
    st.session_state.downloaded_date = None

if st.sidebar.button("Download Data", type="primary"):
    with st.spinner("Mengolah data atmosfer 6-jam (3 Shift pada Tanggal Sama)..."):
        d_str = target_date.strftime("%Y-%m-%d")
        raw = fetch_open_meteo(lat, lon, d_str)
        
        if raw and "hourly" in raw:
            hourly = raw.get("hourly", {})
            
            shifts_config = [
                {
                    "key": "s1", 
                    "name": "Shift 1 (02.00 - 08.00 LT)", 
                    "h_range": list(range(2, 8)), 
                    "t_str": f"02.00 LT {target_date.strftime('%d %B')} to 08.00 LT {target_date.strftime('%d %B %Y')}"
                },
                {
                    "key": "s2", 
                    "name": "Shift 2 (08.00 - 14.00 LT)", 
                    "h_range": list(range(8, 14)), 
                    "t_str": f"08.00 LT {target_date.strftime('%d %B')} to 14.00 LT {target_date.strftime('%d %B %Y')}"
                },
                {
                    "key": "s3", 
                    "name": "Shift 3 (14.00 - 20.00 LT)", 
                    "h_range": list(range(14, 20)), 
                    "t_str": f"14.00 LT {target_date.strftime('%d %B')} to 20.00 LT {target_date.strftime('%d %B %Y')}"
                }
            ]
            
            parsed = []
            for s in shifts_config:
                hr_list = s["h_range"]
                
                wx_all = hourly.get("weather_code") or hourly.get("weathercode") or [0]*24
                wx_6h = [map_wmo_code(wx_all[h]) for h in hr_list if len(wx_all) > h]
                dom_wx = get_dominant_element(wx_6h) or "PARTLY CLOUD"
                
                vis_all = hourly.get("visibility", [])
                vis_6h = [min(int(vis_all[h] / 1000), 10) for h in hr_list if len(vis_all) > h and vis_all[h] is not None]
                dom_vis_val = get_dominant_element(vis_6h) or 10
                dom_vis_str = f"{dom_vis_val} KM"
                
                w180_str = calculate_vector_avg_wind(hourly, "wind_speed_500hPa", "wind_direction_500hPa", hr_list)
                w100_str = calculate_vector_avg_wind(hourly, "wind_speed_700hPa", "wind_direction_700hPa", hr_list)
                w050_str = calculate_vector_avg_wind(hourly, "wind_speed_850hPa", "wind_direction_850hPa", hr_list)
                
                parsed.append({
                    "label": s["name"],
                    "validity": s["t_str"],
                    "weather": dom_wx,
                    "visibility": dom_vis_str,
                    "w180": w180_str,
                    "w100": w100_str,
                    "w050": w050_str,
                })
                
            st.session_state.qc_data = parsed
            st.session_state.downloaded_date = target_date
            st.success("Data berhasil ditarik dan diperbarui! Silakan lakukan Quality Control di bawah.")
        else:
            st.session_state.qc_data = None

# --- DISPLAY FORM QC & PREVIEW ---
if st.session_state.qc_data:
    if st.session_state.get("downloaded_date") != target_date:
        st.warning(f"⚠️ Kamu baru saja mengubah Tanggal Prediksi ke **{target_date.strftime('%d-%m-%Y')}**. Silakan klik tombol **'Download Data'** di sebelah kiri untuk menarik data cuaca baru!")
    else:
        st.subheader("📝 Tahap Quality Control (Intervensi Prakirawan)")
        st.info("Periksa dan koreksi data di bawah jika berbeda dengan analisis radar/satelit lokal.")
        
        # Pilihan Shift via Radio Button (Tersimpan di session state)
        shift_options = [s["label"] for s in st.session_state.qc_data]
        selected_shift_label = st.radio(
            "📌 Pilih Shift yang ingin diedit:", 
            options=shift_options, 
            horizontal=True,
            key="active_shift_tab"
        )
        
        # Cari index shift terpilih
        idx = shift_options.index(selected_shift_label)
        d = st.session_state.qc_data[idx]
        date_code = target_date.strftime("%d%m%Y")

        c1, c2 = st.columns([1, 1.2])
        
        with c1:
            st.markdown(f"**Edit Parameter {d['label']}**")
            
            # Memanggil nilai langsung dari dictionary qc_data (Preserve Value)
            validity_input = st.text_input("Validity Period", value=d["validity"], key=f"val_input_{idx}")
            
            # Pilihan Opsi Cuaca Sesuai Legenda Gambar
            wx_options = [
                "SUNNY", 
                "PARTLY CLOUD", 
                "CLOUDY", 
                "LOCAL RAIN", 
                "MODERATE RAIN", 
                "HEAVY RAIN", 
                "RAIN & TS", 
                "THUNDERSTORM (TS)"
            ]
            wx_default_idx = wx_options.index(d["weather"]) if d["weather"] in wx_options else 1
            weather_input = st.selectbox("Cuaca", wx_options, index=wx_default_idx, key=f"wx_input_{idx}")
            
            vis_input = st.text_input("Visibilitas", value=d["visibility"], key=f"vis_input_{idx}")
            w180_input = st.text_input("Wind FL 180", value=d["w180"], key=f"w180_input_{idx}")
            w100_input = st.text_input("Wind FL 100", value=d["w100"], key=f"w100_input_{idx}")
            w050_input = st.text_input("Wind FL 050", value=d["w050"], key=f"w050_input_{idx}")
            
            # Update memory session_state secara real-time
            st.session_state.qc_data[idx]["validity"] = validity_input
            st.session_state.qc_data[idx]["weather"] = weather_input
            st.session_state.qc_data[idx]["visibility"] = vis_input
            st.session_state.qc_data[idx]["w180"] = w180_input
            st.session_state.qc_data[idx]["w100"] = w100_input
            st.session_state.qc_data[idx]["w050"] = w050_input

            shift_data = {
                "validity": validity_input,
                "weather": weather_input,
                "visibility": vis_input,
                "wind_fl180": w180_input,
                "wind_fl100": w100_input,
                "wind_fl050": w050_input
            }
        
        with c2:
            st.markdown("**Preview Infografis Target**")
            rendered_img = render_infographic("holding_point.png", shift_data)
            
            if rendered_img:
                st.image(rendered_img, use_container_width=True)
                
                buf = io.BytesIO()
                rendered_img.save(buf, format="PNG")
                img_bytes = buf.getvalue()
                
                st.download_button(
                    label=f"📥 Download Gambar {d['label'][:7]}",
                    data=img_bytes,
                    file_name=f"Holding_{holding_point}_{d['label'][:7]}_{date_code}.png",
                    mime="image/png",
                    key=f"dl_{idx}"
                )
                
                st.write("")
                
                target_group_id = "6282199660289-1476434585@g.us"
                
                if st.button(f"📤 Kirim {d['label'][:7]} ke WA Group", key=f"wa_btn_{idx}", type="primary"):
                    with st.spinner("Mengirim infografis ke WhatsApp Group..."):
                        is_sent = send_to_whatsapp_bot(img_bytes, target_group_id, caption="")
                        if is_sent:
                            st.success("✅ Infografis berhasil terkirim ke WhatsApp Group!")
                        else:
                            st.error("❌ Gagal mengirim. Pastikan server Node.js (`server.js`) tetap menyala di background.")
else:
    st.warning("Silakan pilih tanggal dan klik tombol 'Download Data' pada sidebar di sebelah kiri.")

# --- FOOTER / TRADEMARK ---
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #888888; font-size: 0.85rem; padding-bottom: 10px;'>"
    "© Kedeng V"
    "</div>",
    unsafe_allow_html=True
)
