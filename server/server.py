from flask import Flask, request, jsonify, render_template, send_from_directory
import os, json
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_FOLDER = os.path.join(BASE_DIR, "..", "media")
CONFIG_FILE = os.path.join(BASE_DIR, "..", "config", "config.json")
ARCHIVE_FOLDER = os.path.join(MEDIA_FOLDER, "archived")

os.makedirs(ARCHIVE_FOLDER, exist_ok=True)
os.makedirs(MEDIA_FOLDER, exist_ok=True)

# === ROUTES PRINCIPALES ===

@app.route('/')
def index():
    return render_template("index.html")


@app.route('/admin')
def admin():
    return render_template("admin.html")


@app.route('/media')
def list_media():
    files = sorted(os.listdir(MEDIA_FOLDER))
    return jsonify(files)


@app.route('/upload', methods=['POST'])
def upload():
    files = request.files.getlist('file')
    for file in files:
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(MEDIA_FOLDER, filename))
    return '', 204


@app.route('/delete', methods=['POST'])
def delete():
    data = request.get_json()
    filename = data.get("filename")
    path = os.path.join(MEDIA_FOLDER, filename)
    if os.path.exists(path):
        os.remove(path)
        return "Deleted", 200
    return "Not found", 404


@app.route('/archive', methods=['POST'])
def archive():
    data = request.get_json()
    filename = data.get("filename")
    src_path = os.path.join(MEDIA_FOLDER, filename)
    dst_path = os.path.join(ARCHIVE_FOLDER, filename)

    if os.path.exists(src_path):
        os.rename(src_path, dst_path)
        return "Archived", 200
    return "Not found", 404


# === CONFIGURATION ===

@app.route('/config', methods=['GET', 'POST'])
def config():
    if request.method == 'GET':
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return jsonify(json.load(f))
        return jsonify({})

    data = request.get_json() or {}
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                config = json.load(f)
            except:
                pass

    config.update(data)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    return "Updated", 200


# === MODES SPÉCIAUX ===

@app.route('/nightmode/toggle', methods=['POST'])
def toggle_night_mode():
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                config = json.load(f)
            except:
                pass

    current = config.get("apply_auto_night_mode", False)
    config["apply_auto_night_mode"] = not current

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

    return jsonify({"status": "ok", "apply_auto_night_mode": config["apply_auto_night_mode"]})


@app.route('/blackscreen/toggle', methods=['POST'])
def toggle_black_mode():
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                config = json.load(f)
            except:
                pass

    current = config.get("black_screen", False)
    config["black_screen"] = not current

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

    return jsonify({"status": "ok", "black_screen": config["black_screen"]})


@app.route('/nightmode', methods=['GET'])
def get_night_mode():
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                config = json.load(f)
            except:
                pass
    return jsonify({"apply_auto_night_mode": config.get("apply_auto_night_mode", False)})


@app.route('/blackscreen', methods=['GET'])
def get_black_mode():
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                config = json.load(f)
            except:
                pass
    return jsonify({"black_screen": config.get("black_screen", False)})


# === SERVEURS DE FICHIERS ===

@app.route('/media/<path:filename>')
def serve_file(filename):
    return send_from_directory(MEDIA_FOLDER, filename)


# === MAIN ===

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
