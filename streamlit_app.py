import os, re, io, tempfile, time, platform, subprocess
import numpy as np
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, afx

st.set_page_config(page_title="MNWS TikTok — iPad ready (30s + 3 batch)", layout="centered")

# --- Schrijf naar temp (Streamlit Cloud is read-only in repo) ---
OUT_DIR = os.path.join(tempfile.gettempdir(), "mnws_output")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------- helpers ----------
def load_font(size: int):
    # Werkt op Streamlit Cloud (Linux) + Windows fallback
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for fp in candidates:
        if os.path.isfile(fp):
            try:
                return ImageFont.truetype(fp, size=size)
            except Exception:
                pass
    return ImageFont.load_default()

def hex_to_rgb(h):
    if h and h.startswith("#") and len(h) in (4,7):
        if len(h)==4:
            h = "#" + "".join([c*2 for c in h[1:]])
        return (int(h[1:3],16), int(h[3:5],16), int(h[5:7],16))
    return (239,239,239)

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        bbox = draw.textbbox((0,0), t, font=font)
        if bbox[2]-bbox[0] <= max_width or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def make_title_overlay(W, H, title, desc, font_size=58, txt="#000000",
                       bar="#FFFFFF", opacity=0.85, top=220, padding=24, radius=28):
    overlay = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(overlay)
    f_title = load_font(font_size)
    f_desc  = load_font(max(28, int(font_size*0.55)))

    lines = []
    max_w = int(W*0.9)
    for ln in wrap_text(draw, title, f_title, max_w):
        lines.append(("t", ln))
    if desc.strip():
        lines.append(("g",""))
        for ln in wrap_text(draw, desc, f_desc, max_w):
            lines.append(("d", ln))

    heights, widths = [], []
    for kind, ln in lines:
        f = f_title if kind in ("t","g") else f_desc
        bbox = draw.textbbox((0,0), ln, font=f)
        w = bbox[2]-bbox[0]
        h = bbox[3]-bbox[1] if ln else int(font_size*0.35)
        widths.append(w); heights.append(h)

    text_w = max(widths) if widths else 0
    text_h = sum(heights) + (len(lines)-1)*int(font_size*0.25)

    box_w = min(text_w + padding*2, int(W*0.95))
    box_h = text_h + padding*2
    x = (W - box_w)//2
    y = max(0, min(H - box_h, top))

    a = int(255*float(opacity))
    r,g,b = hex_to_rgb(bar)
    draw.rounded_rectangle((x,y,x+box_w,y+box_h), radius=radius, fill=(r,g,b,a))

    ty = y + padding
    for i,(kind, ln) in enumerate(lines):
        f = f_title if kind in ("t","g") else f_desc
        lw = draw.textbbox((0,0), ln, font=f)[2]
        lx = x + (box_w - lw)//2
        if ln:
            draw.text((lx, ty), ln, font=f, fill=txt)
        ty += heights[i] + int(font_size*0.25)

    return overlay

def make_cover_clip(img, W, H, duration):
    base = ImageClip(img)
    scale = max(W/base.w, H/base.h)
    return base.resize(scale).crop(
        x_center=base.w*scale/2, y_center=base.h*scale/2, width=W, height=H
    ).set_duration(duration)

def make_solid_bg(W,H,duration,color="#EFEFEF"):
    img = Image.new("RGB",(W,H),hex_to_rgb(color))
    return ImageClip(np.array(img)).set_duration(duration)

def caption_from(title, desc):
    base = ["#nieuws","#marokko","#mnws","#tiktoknews","#viral"]
    main = "#" + re.sub(r"[^A-Za-z0-9]+","", title)[:30].lower()
    tags = [main] + base
    return (f"{title}\n{desc}\n\n" if desc.strip() else f"{title}\n\n") + " ".join(tags[:6])

def sanitize(text): 
    text = re.sub(r"[^\w\-]+","_", text.strip())
    return text[:60].strip("_") or f"video_{int(time.time())}"

def render_video(title, desc, *, bg_file=None, logo_file=None, music_file=None,
                 W=1080, H=1920, font_size=58, txt="#000000", bar="#FFFFFF",
                 opacity=0.85, top=220, logo_pos="topleft", logo_w=200,
                 fps=30, duration=30):
    # achtergrond
    if bg_file:
        bg = make_cover_clip(bg_file, W, H, duration)
    else:
        bg = make_solid_bg(W,H,duration)

    # overlay
    ov = make_title_overlay(W,H,title,desc,font_size,font_size and txt,bar,opacity,top)
    title_clip = ImageClip(np.array(ov)).set_duration(duration)

    layers = [bg, title_clip]

    # logo
    if logo_file:
        from PIL import Image as PILImage
        logo = PILImage.open(logo_file).convert("RGBA")
        ratio = logo_w / logo.width
        new_logo = logo.resize((logo_w, int(logo.height*ratio)), Image.Resampling.LANCZOS)
        logo_clip = ImageClip(np.array(new_logo)).set_duration(duration)
        m=24
        if logo_pos=="topleft": pos=(m,m)
        elif logo_pos=="topright": pos=(W-new_logo.width-m, m)
        elif logo_pos=="bottomleft": pos=(m, H-new_logo.height-m)
        else: pos=(W-new_logo.width-m, H-new_logo.height-m)
        layers.append(logo_clip.set_position(pos))

    final = CompositeVideoClip(layers, size=(W,H))

    # audio (optioneel)
    if music_file:
        try:
            mus = AudioFileClip(music_file)
            mus = mus.subclip(0, min(duration, getattr(mus,"duration",duration)))
            mus = afx.audio_fadein(mus, 0.6)
            mus = afx.audio_fadeout(mus, 0.6)
            final = final.set_audio(mus.volumex(0.5))
        except Exception:
            pass

    out = os.path.join(OUT_DIR, f"{sanitize(title)}.mp4")
    final.write_videofile(out, fps=fps, codec="libx264", audio_codec="aac", threads=4, preset="medium")
    try:
        final.close()
    except Exception:
        pass
    return out

# ---------- UI ----------
st.title("🎬 MNWS TikTok — 30s + Beschrijving + Batch (iPad ready)")
st.caption("Draait op Streamlit Cloud of lokaal; upload assets direct vanaf je iPad.")

# Uploads (allemaal optioneel)
bg_up   = st.file_uploader("Achtergrond (jpg/png) — laat leeg voor effen grijs", type=["jpg","jpeg","png"])
logo_up = st.file_uploader("Logo (PNG transparant aangeraden)", type=["png"])
music_up= st.file_uploader("Muziek (mp3) — laat leeg voor stil", type=["mp3"])

# Single
st.subheader("🎥 Eén clip (30s)")
title = st.text_input("Titel", "Voorbeeldtitel")
desc  = st.text_area("Korte beschrijving", "Korte uitleg of context bij dit nieuws.")
col1,col2 = st.columns(2)
with col1:
    font_size = st.slider("Titel lettergrootte", 36, 96, 58)
    title_color = st.color_picker("Tekstkleur", "#000000")
with col2:
    bar_color = st.color_picker("Balkkleur", "#FFFFFF")
    bar_opacity = st.slider("Balk opaciteit", 0.0, 1.0, 0.85)

top = st.slider("Titel vertical offset (px vanaf boven)", 0, 800, 220)
logo_pos = st.selectbox("Logo positie", ["topleft","topright","bottomleft","bottomright"], index=0)
logo_w   = st.slider("Logo breedte (px)", 80, 400, 200)

if st.button("▶️ Render 1 video (30s)"):
    if not title.strip():
        st.error("Titel is verplicht.")
    else:
        try:
            t_bg   = io.BytesIO(bg_up.read()) if bg_up else None
            t_logo = io.BytesIO(logo_up.read()) if logo_up else None
            t_mus  = io.BytesIO(music_up.read()) if music_up else None

            path = render_video(
                title, desc, bg_file=t_bg, logo_file=t_logo, music_file=t_mus,
                font_size=font_size, txt=title_color, bar=bar_color,
                opacity=bar_opacity, top=top, logo_pos=logo_pos, logo_w=logo_w,
                duration=30
            )
            st.success(f"Klaar: {os.path.basename(path)}")
            with open(path,"rb") as f:
                st.download_button("⬇️ Download MP4", f, file_name=os.path.basename(path), mime="video/mp4")
            st.code(caption_from(title, desc), language=None)
        except Exception as e:
            st.error(f"Fout: {e}")

st.divider()

# Batch 3
st.subheader("🔁 Batch voor 3 artikels (zonder CSV)")
c1,c2 = st.columns(2)
with c1:
    t1 = st.text_input("Titel 1", "")
    t2 = st.text_input("Titel 2", "")
    t3 = st.text_input("Titel 3", "")
with c2:
    d1 = st.text_area("Beschrijving 1", "", height=80)
    d2 = st.text_area("Beschrijving 2", "", height=80)
    d3 = st.text_area("Beschrijving 3", "", height=80)

if st.button("🚀 Render 3 video’s (30s elk)"):
    items = [(t1.strip(), d1.strip()), (t2.strip(), d2.strip()), (t3.strip(), d3.strip())]
    items = [(t,d) for (t,d) in items if t]
    if not items:
        st.error("Vul minstens één titel in.")
    else:
        done = []
        try:
            t_bg   = io.BytesIO(bg_up.read()) if bg_up else None
            if bg_up: bg_up.seek(0)
            t_logo = io.BytesIO(logo_up.read()) if logo_up else None
            if logo_up: logo_up.seek(0)
            t_mus  = io.BytesIO(music_up.read()) if music_up else None
            if music_up: music_up.seek(0)
        except Exception:
            t_bg=t_logo=t_mus=None

        for i,(tt,dd) in enumerate(items, start=1):
            st.write(f"▶ Renderen: {tt}")
            try:
                # reset streams each loop
                bg_bytes   = io.BytesIO(t_bg.getvalue()) if t_bg else None
                logo_bytes = io.BytesIO(t_logo.getvalue()) if t_logo else None
                mus_bytes  = io.BytesIO(t_mus.getvalue()) if t_mus else None

                path = render_video(
                    tt, dd, bg_file=bg_bytes, logo_file=logo_bytes, music_file=mus_bytes,
                    font_size=font_size, txt=title_color, bar=bar_color,
                    opacity=bar_opacity, top=top, logo_pos=logo_pos, logo_w=logo_w,
                    duration=30
                )
                done.append(path)
            except Exception as e:
                st.error(f"Fout bij “{tt}”: {e}")

        if done:
            st.success(f"{len(done)} clips klaar!")
            for p in done:
                with open(p,"rb") as f:
                    st.download_button(f"⬇️ {os.path.basename(p)}", f, file_name=os.path.basename(p), mime="video/mp4")
