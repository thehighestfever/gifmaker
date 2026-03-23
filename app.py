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

VIDEO_ROOT = "/videos"      # mounted from /mnt/rewind/plex
MEDIA_ROOT = "./media"      # generated GIFs/MP4s
UPLOAD_ROOT = "./uploads"   # uploaded files

os.makedirs(MEDIA_ROOT, exist_ok=True)
os.makedirs(UPLOAD_ROOT, exist_ok=True)

# track remuxed mp4s so we can safely delete them after use
TEMP_REMUXED = set()


# ----------------- helpers -----------------
def parse_hms(t):
    parts = t.split(":")
    if len(parts) != 3:
        return 0.0
    h, m, s = parts
    return int(h) * 3600 + int(m) * 60 + float(s)


def format_seconds(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def q(v: str) -> str:
    return quote_plus(v) if v is not None else ""


# ----------------- static host videos -----------------
@app.route("/videos/<path:filename>")
def serve_videos(filename):
    return send_from_directory(VIDEO_ROOT, filename)


# ----------------- index -----------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        return process_generation()

    media_path = request.args.get("media")
    last_youtube = request.args.get("youtube", "")
    last_hostpath = request.args.get("hostpath", "")
    last_format = request.args.get("format", "gif")
    last_start = request.args.get("start", "")
    last_end = request.args.get("end", "")

    return render_template(
        "index.html",
        media_path=media_path,
        last_youtube=last_youtube,
        last_hostpath=last_hostpath,
        last_format=last_format,
        last_start=last_start,
        last_end=last_end,
    )


# ----------------- directory browser -----------------
@app.get("/listdir")
def listdir():
    rel = request.args.get("path", "")
    abs_path = os.path.join(VIDEO_ROOT, rel)

    dirs = []
    files = []

    for entry in os.listdir(abs_path):
        full = os.path.join(abs_path, entry)
        if os.path.isdir(full):
            dirs.append(entry)
        else:
            files.append(entry)

    return jsonify(
        {
            "path": rel,
            "dirs": sorted(dirs),
            "files": sorted(files),
        }
    )


# ----------------- list generated media -----------------
@app.get("/listmedia")
def listmedia():
    items = sorted(os.listdir(MEDIA_ROOT))
    return jsonify(items)


# ----------------- delete one media -----------------
@app.post("/delete_media")
def delete_media():
    data = request.get_json()
    filename = data.get("filename")
    path = os.path.join(MEDIA_ROOT, filename)

    if os.path.exists(path):
        os.remove(path)

    return jsonify({"ok": True})


# ----------------- delete all media -----------------
@app.post("/delete_all_media")
def delete_all_media():
    for f in os.listdir(MEDIA_ROOT):
        os.remove(os.path.join(MEDIA_ROOT, f))
    return jsonify({"ok": True})


# ----------------- mkv remux -----------------
@app.post("/remux")
def remux():
    data = request.get_json()
    src = data.get("path")

    print("REMUX REQUESTED PATH:", src)
    print("FILE EXISTS?", os.path.exists(src))

    if not src or not src.lower().endswith(".mkv"):
        return jsonify({"error": "Not an MKV"}), 400

    fs_path = src
    mp4_fs = fs_path.rsplit(".", 1)[0] + ".mp4"
    mp4_web = src.rsplit(".", 1)[0] + ".mp4"

    if os.path.exists(mp4_fs):
        # treat existing mp4 as temp for this session
        TEMP_REMUXED.add(mp4_fs)
        return jsonify({"output": mp4_web})

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        fs_path,
        "-c",
        "copy",
        mp4_fs,
    ]

    print("RUNNING FFMPEG:", " ".join(cmd))
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    print("MP4 EXISTS AFTER REMUX?", os.path.exists(mp4_fs))

    if not os.path.exists(mp4_fs):
        return jsonify({"error": "Remux failed"}), 500

    TEMP_REMUXED.add(mp4_fs)
    return jsonify({"output": mp4_web})


# ----------------- main generation -----------------
def process_generation():
    print("PROCESS GENERATION CALLED")

    youtube_url = request.form.get("youtube", "").strip()
    hostpath = request.form.get("hostpath", "").strip()
    upload = request.files.get("video")

    input_path = None

    # 1) uploaded file
    if upload and upload.filename:
        ext = upload.filename.rsplit(".", 1)[-1].lower()
        fname = f"{uuid.uuid4()}.{ext}"
        input_path = os.path.join(UPLOAD_ROOT, fname)
        upload.save(input_path)

    # 2) YouTube (not implemented here)
    elif youtube_url:
        return "YouTube download not implemented in this version", 500

    # 3) host video (/videos/...)
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

        # assume 30fps
        s_adj = sf / 30.0
        e_adj = ef / 30.0

        if start_signs[i] == "-":
            start_sec = base_s - s_adj
        else:
            start_sec = base_s + s_adj

        if end_signs[i] == "-":
            end_sec = base_e - e_adj
        else:
            end_sec = base_e + e_adj

        if start_sec < 0:
            start_sec = 0
        if end_sec <= start_sec:
            end_sec = start_sec + 0.1

        ss = format_seconds(start_sec)
        ee = format_seconds(end_sec)

        clip_name = f"{uuid.uuid4()}.mp4"
        clip_path = os.path.join(MEDIA_ROOT, clip_name)

        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            ss,
            "-to",
            ee,
            "-i",
            input_path,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            clip_path,
        ]
        print("CLIP CMD:", " ".join(cmd))
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        concat_list.append(clip_path)

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
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file,
            "-c",
            "copy",
            final_path,
        ]
        print("STITCH CMD:", " ".join(cmd))
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # cleanup remuxed mp4 if this was one of ours
    if input_path.startswith("/videos/") and input_path.lower().endswith(".mp4"):
        fs_path = input_path  # same string we stored in TEMP_REMUXED
        if fs_path in TEMP_REMUXED and os.path.exists(fs_path):
            print("CLEANING REMUXED MP4:", fs_path)
            os.remove(fs_path)
            TEMP_REMUXED.discard(fs_path)

    # build redirect with context so page can remember last values
    first_start = starts[0] if starts else ""
    first_end = ends[0] if ends else ""

    base_media = f"/media/{os.path.basename(final_path)}"
    query_parts = [
        f"media={q(base_media)}",
        f"hostpath={q(hostpath)}",
        f"format={q(fmt)}",
        f"start={q(first_start)}",
        f"end={q(first_end)}",
    ]
    if youtube_url:
        query_parts.append(f"youtube={q(youtube_url)}")

    query = "&".join(p for p in query_parts if p)
    if fmt == "gif":
        # if gif, final_path is mp4; we created gif separately
        # but we still want the gif in media param
        # so override media in query
        gif_name = f"{uuid.uuid4()}.gif"
        gif_path = os.path.join(MEDIA_ROOT, gif_name)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            final_path,
            "-vf",
            "fps=12,scale=480:-1:flags=lanczos",
            gif_path,
        ]
        print("GIF CMD:", " ".join(cmd))
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        base_media = f"/media/{gif_name}"
        query_parts[0] = f"media={q(base_media)}"
        query = "&".join(p for p in query_parts if p)

    return redirect(f"/?{query}")


# ----------------- serve generated media -----------------
@app.route("/media/<path:filename>")
def serve_media(filename):
    return send_from_directory(MEDIA_ROOT, filename)


# ----------------- stitch existing -----------------
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
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        list_file,
        "-c",
        "copy",
        output,
    ]
    print("STITCH_EXISTING CMD:", " ".join(cmd))
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    return jsonify({"output": "/media/stitched.mp4"})


# ----------------- regenerate last -----------------
@app.post("/regenerate")
def regenerate():
    data = request.get_json()
    last = data.get("last")

    if not last:
        return jsonify({"error": "No last output"}), 400

    filename = last.split("/")[-1]
    path = os.path.join(MEDIA_ROOT, filename)

    if os.path.exists(path):
        os.remove(path)

    return jsonify({"redirect": "/"})


# ----------------- main -----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

