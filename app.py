import os
import uuid
import subprocess
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_from_directory,
    redirect,
    url_for,
)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

VIDEO_DIR = "/videos"
GIF_DIR = "/gifs"

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(GIF_DIR, exist_ok=True)


def make_gif(input_path, start, end, output_path):
    cmd = [
        "ffmpeg",
        "-ss", start,
        "-to", end,
        "-i", input_path,
        "-vf", "fps=12,scale=480:-1:flags=lanczos",
        "-y",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def concat_gifs(gif_paths, output_path):
    cmd = ["ffmpeg"]

    for gif in gif_paths:
        cmd += ["-i", gif]

    concat_filter = "".join([f"[{i}:v]" for i in range(len(gif_paths))])
    concat_filter += f"concat=n={len(gif_paths)}:v=1 [v]"

    cmd += [
        "-filter_complex", concat_filter,
        "-map", "[v]",
        "-y",
        output_path
    ]

    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@app.route("/listdir")
def listdir():
    rel = request.args.get("path", "").strip("/")
    abs_path = os.path.join(VIDEO_DIR, rel)

    if not abs_path.startswith(VIDEO_DIR):
        return jsonify({"error": "Invalid path"}), 400

    dirs, files = [], []

    for name in os.listdir(abs_path):
        full = os.path.join(abs_path, name)
        if os.path.isdir(full):
            dirs.append(name)
        else:
            files.append(name)

    dirs.sort(key=str.lower)
    files.sort(key=str.lower)

    return jsonify({"path": rel, "dirs": dirs, "files": files})


@app.route("/listgifs")
def listgifs():
    gifs = [
        name for name in os.listdir(GIF_DIR)
        if os.path.isfile(os.path.join(GIF_DIR, name)) and name.lower().endswith(".gif")
    ]
    gifs.sort(key=str.lower)
    return jsonify(gifs)


@app.route("/gif/<path:filename>")
def serve_gif(filename):
    return send_from_directory(GIF_DIR, filename)


@app.route("/delete_gif", methods=["POST"])
def delete_gif():
    filename = request.json.get("filename")
    if not filename:
        return jsonify({"error": "No filename"}), 400

    path = os.path.join(GIF_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
        return jsonify({"status": "ok"})
    return jsonify({"error": "Not found"}), 404


@app.route("/delete_all_gifs", methods=["POST"])
def delete_all_gifs():
    deleted = 0
    for name in os.listdir(GIF_DIR):
        if name.lower().endswith(".gif"):
            try:
                os.remove(os.path.join(GIF_DIR, name))
                deleted += 1
            except:
                pass
    return jsonify({"status": "ok", "deleted": deleted})


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        uploaded_file = request.files.get("video")
        host_path = request.form.get("hostpath", "").strip()
        youtube_url = request.form.get("youtube", "").strip()

        starts = request.form.getlist("start[]")
        ends = request.form.getlist("end[]")

        temp_upload_path = None

        # YouTube
        if youtube_url:
            temp_upload_path = os.path.join(
                app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.mp4"
            )
            cmd = [
                "yt-dlp",
                "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
                "-o", temp_upload_path,
                youtube_url
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            input_path = temp_upload_path

        # Host path
        elif host_path:
            if not os.path.exists(host_path):
                return f"Host file not found: {host_path}", 400
            input_path = host_path

        # Upload
        elif uploaded_file:
            filename = f"{uuid.uuid4()}_{uploaded_file.filename}"
            temp_upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            uploaded_file.save(temp_upload_path)
            input_path = temp_upload_path

        else:
            return "No video source provided", 400

        # Generate GIFs for each segment
        temp_gifs = []

        for start, end in zip(starts, ends):
            if not start or not end:
                continue

            gif_name = f"{uuid.uuid4()}.gif"
            gif_path = os.path.join(GIF_DIR, gif_name)

            make_gif(input_path, start, end, gif_path)
            temp_gifs.append(gif_path)

        if not temp_gifs:
            return "No valid segments provided", 400

        # Stitch if multiple
        if len(temp_gifs) == 1:
            final_gif_name = os.path.basename(temp_gifs[0])
        else:
            final_gif_name = f"{uuid.uuid4()}.gif"
            final_gif_path = os.path.join(GIF_DIR, final_gif_name)

            concat_gifs(temp_gifs, final_gif_path)

            # cleanup
            for gif in temp_gifs:
                os.remove(gif)

        # Cleanup temp YouTube or upload
        if temp_upload_path and os.path.exists(temp_upload_path):
            os.remove(temp_upload_path)

        return redirect(url_for(
            "index",
            gif=final_gif_name,
            last_hostpath=host_path,
            last_youtube=youtube_url
        ))

    gif_name = request.args.get("gif")
    gif_path = f"/gif/{gif_name}" if gif_name else None

    return render_template(
        "index.html",
        gif_path=gif_path,
        last_hostpath=request.args.get("last_hostpath", ""),
        last_youtube=request.args.get("last_youtube", "")
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
