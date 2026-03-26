import os
import uuid
import subprocess
from urllib.parse import quote_plus

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    send_from_directory,
    redirect,
)

app = Flask(__name__)

# ------------------------------
# PATHS (MATCH YOUR COMPOSE)
# ------------------------------
VIDEO_ROOT = "/videos"            # Plex library mount
MEDIA_ROOT = "/app/media"         # Generated clips/GIFs
UPLOAD_ROOT = "/app/uploads"      # Uploaded files

# Ensure directories exist
os.makedirs(MEDIA_ROOT, exist_ok=True)
os.makedirs(UPLOAD_ROOT, exist_ok=True)


# ------------------------------
# UTILITIES
# ------------------------------
def parse_hms(t):
    """Parse HH:MM:SS.xxx into seconds."""
    if not t or ":" not in t:
        return 0.0
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def format_seconds(sec):
    """Format seconds into HH:MM:SS.xxx."""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def q(v):
    return quote_plus(v) if v else ""


# ------------------------------
# STATIC SERVING
# ------------------------------
@app.route("/videos/<path:filename>")
def serve_videos(filename):
    return send_from_directory(VIDEO_ROOT, filename)


@app.route("/media/<path:filename>")
def serve_media(filename):
    return send_from_directory(MEDIA_ROOT, filename)


# ------------------------------
# INDEX
# ------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        return process_generation()

    return render_template(
        "index.html",
        media_path=request.args.get("media", ""),
        last_hostpath=request.args.get("hostpath", ""),
        last_format=request.args.get("format", "gif"),
        last_start=request.args.get("start", ""),
        last_end=request.args.get("end", ""),
    )


# ------------------------------
# DIRECTORY BROWSER
# ------------------------------
@app.get("/listdir")
def listdir():
    rel = request.args.get("path", "")
    abs_path = os.path.join(VIDEO_ROOT, rel)

    if not os.path.exists(abs_path):
        return jsonify({"path": rel, "dirs": [], "files": []})

    dirs, files = [], []
    for entry in os.listdir(abs_path):
        full = os.path.join(abs_path, entry)
        if os.path.isdir(full):
            dirs.append(entry)
        else:
            files.append(entry)

    return jsonify({
        "path": rel,
        "dirs": sorted(dirs),
        "files": sorted(files),
    })


# ------------------------------
# MEDIA LISTING
# ------------------------------
@app.get("/listmedia")
def listmedia():
    try:
        items = sorted(os.listdir(MEDIA_ROOT))
    except Exception:
        return jsonify([])
    return jsonify(items)


@app.post("/delete_media")
def delete_media():
    data = request.get_json()
    filename = data.get("filename")
    path = os.path.join(MEDIA_ROOT, filename)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"ok": True})


@app.post("/delete_all_media")
def delete_all_media():
    for f in os.listdir(MEDIA_ROOT):
        os.remove(os.path.join(MEDIA_ROOT, f))
    return jsonify({"ok": True})


# ------------------------------
# MAIN GENERATION PIPELINE
# ------------------------------
def process_generation():
    hostpath = request.form.get("hostpath", "").strip()
    upload = request.files.get("video")

    input_path = None

    # 1. Uploaded file
    if upload and upload.filename:
        ext = upload.filename.rsplit(".", 1)[-1].lower()
        fname = f"{uuid.uuid4()}.{ext}"
        input_path = os.path.join(UPLOAD_ROOT, fname)
        upload.save(input_path)

    # 2. Host video
    elif hostpath:
        input_path = hostpath

    else:
        return "No input source provided", 500

    fmt = request.form.get("format", "gif")

    starts = request.form.getlist("start[]")
    ends = request.form.getlist("end[]")
    start_signs = request.form.getlist("start_sign[]")
    end_signs = request.form.getlist("end_sign[]")
    start_frames = request.form.getlist("start_frames[]")
    end_frames = request.form.getlist("end_frames[]")

    if not starts or not ends:
        return "Missing segments", 500

    concat_list = []

    for i in range(len(starts)):
        base_s = parse_hms(starts[i])
        base_e = parse_hms(ends[i])

        sf = int(start_frames[i] or 0)
        ef = int(end_frames[i] or 0)

        s_adj = sf / 30.0
        e_adj = ef / 30.0

        start_sec = base_s + (s_adj if start_signs[i] == "+" else -s_adj)
        end_sec = base_e + (e_adj if end_signs[i] == "+" else -e_adj)

        if start_sec < 0:
            start_sec = 0
        if end_sec <= start_sec:
            end_sec = start_sec + 0.1

        ss = format_seconds(start_sec)
        ee = format_seconds(end_sec)

        clip_name = f"{uuid.uuid4()}.mp4"
        clip_path = os.path.join(MEDIA_ROOT, clip_name)

        cmd = [
            "ffmpeg", "-y",
            "-ss", ss,
            "-to", ee,
            "-i", input_path,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            clip_path,
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        concat_list.append(clip_path)

    # Stitch if needed
    if len(concat_list) == 1:
        final_path = concat_list[0]
    else:
        list_file = os.path.join(MEDIA_ROOT, "concat.txt")
        with open(list_file, "w") as f:
            for p in concat_list:
                f.write(f"file '{p}'\n")

        final_name = f"{uuid.uuid4()}.mp4"
        final_path = os.path.join(MEDIA_ROOT, final_name)

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            final_path,
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # GIF conversion
    if fmt == "gif":
        gif_name = f"{uuid.uuid4()}.gif"
        gif_path = os.path.join(MEDIA_ROOT, gif_name)

        cmd = [
            "ffmpeg", "-y",
            "-i", final_path,
            "-vf", "fps=12,scale=480:-1:flags=lanczos",
            gif_path,
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        media_url = f"/media/{gif_name}"
    else:
        media_url = f"/media/{os.path.basename(final_path)}"

    # Sticky values
    query = "&".join([
        f"media={q(media_url)}",
        f"hostpath={q(input_path)}",
        f"format={q(fmt)}",
        f"start={q(starts[0])}",
        f"end={q(ends[0])}",
    ])

    return redirect(f"/?{query}")


# ------------------------------
# STITCH EXISTING
# ------------------------------
@app.post("/stitch_existing")
def stitch_existing():
    data = request.get_json()
    files = data.get("files", [])

    if len(files) < 2:
        return jsonify({"error": "Need at least two files"}), 400

    inputs = [os.path.join(MEDIA_ROOT, f) for f in files]

    list_file = os.path.join(MEDIA_ROOT, "concat.txt")
    with open(list_file, "w") as f:
        for p in inputs:
            f.write(f"file '{p}'\n")

    output = os.path.join(MEDIA_ROOT, "stitched.mp4")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output,
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    return jsonify({"output": "/media/stitched.mp4"})


# ------------------------------
# MAIN
# ------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

