import cv2
import os
import time
import numpy as np
from PIL import Image, ImageFilter
from screeninfo import get_monitors
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Thread, Event
from pymediainfo import MediaInfo
import json
import random
import functools
import sys
from datetime import datetime
import gc

# --- Nettoyage des sorties pour logs directs ---
print = functools.partial(print, flush=True)
sys.stderr = sys.stdout

# --- Extensions supportées ---
IMAGE_EXT = [".jpg", ".jpeg", ".png"]
VIDEO_EXT = [".mp4", ".avi", ".mov"]

# --- Répertoires ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "..", "config", "config.json")
MEDIA_FOLDER = os.path.join(BASE_DIR, "..", "media")

# --- États globaux ---
media_list = []
media_updated = Event()
apply_auto_night_mode = False


# === UTILITAIRES ===

def load_config():
    """Charge la configuration JSON"""
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r") as f:
        try:
            return json.load(f)
        except:
            return {}


def is_night_mode():
    """Renvoie True si on est dans la plage horaire de nuit"""
    if not apply_auto_night_mode:
        return False
    now = datetime.now().hour
    return now >= 22 or now < 7


def apply_overlay_if_needed(image):
    """Assombrit l'image en mode nuit"""
    if is_night_mode():
        overlay = np.zeros_like(image, dtype=np.uint8)
        alpha = 0.4
        image = cv2.addWeighted(image, 1 - alpha, overlay, alpha, 0)
    return image


def get_screen_resolution():
    """Retourne la résolution de l'écran principal"""
    monitor = get_monitors()[0]
    return monitor.width, monitor.height


def load_media_list():
    """Charge la liste des fichiers média valides"""
    files = sorted(os.listdir(MEDIA_FOLDER))
    return [
        os.path.join(MEDIA_FOLDER, f)
        for f in files
        if os.path.splitext(f)[1].lower() in IMAGE_EXT + VIDEO_EXT
    ]


# === AFFICHAGE ===

def fade_transition(current, next_img, steps=10, delay=0.05):
    """Transition fluide entre deux images"""
    current = apply_overlay_if_needed(current)
    next_img = apply_overlay_if_needed(next_img)
    for alpha in np.linspace(0, 1, steps):
        blended = cv2.addWeighted(current, 1 - alpha, next_img, alpha, 0)
        cv2.imshow("MediaViewer", blended)
        cv2.setWindowProperty("MediaViewer", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        if cv2.waitKey(int(delay * 1000)) & 0xFF == ord('q'):
            break


def show_image(path, screen_size):
    """Affiche une image centrée avec fond flou"""
    screen_w, screen_h = screen_size
    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:
        print(f"❌ Erreur ouverture image {path} : {e}")
        return np.zeros((screen_size[1], screen_size[0], 3), dtype=np.uint8)

    iw, ih = img.size
    ratio = screen_h / ih
    new_w = int(iw * ratio)
    img = img.resize((new_w, screen_h), Image.LANCZOS)

    blurred_bg = img.resize(screen_size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(20))
    x = (screen_w - new_w) // 2
    blurred_bg.paste(img, (x, 0))
    img = blurred_bg

    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def get_rotation(path):
    """Détermine la rotation à appliquer à une vidéo"""
    try:
        media_info = MediaInfo.parse(path)
        for track in media_info.tracks:
            if track.track_type == "Video":
                if hasattr(track, "rotation"):
                    return int(float(track.rotation))
                if track.width and track.height and track.height > track.width:
                    return 90
    except Exception as e:
        print(f"[ERROR] rotation detection: {e}")
    return 0


def rotate_frame(frame, angle):
    """Applique une rotation à une image vidéo"""
    if angle == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif angle == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    elif angle == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame


def show_video(path, screen_size):
    """Affiche une vidéo avec fond flou"""
    screen_w, screen_h = screen_size
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"❌ Impossible d'ouvrir la vidéo : {path}")
        return

    rotation = get_rotation(path)
    print(f"Rotation détectée pour {path}: {rotation}°")

    ret, first_frame = cap.read()
    if not ret:
        cap.release()
        return

    rotated_first = rotate_frame(first_frame, rotation)
    h, w = rotated_first.shape[:2]
    ratio = screen_h / h
    new_w = int(w * ratio)

    blurred_bg = cv2.resize(rotated_first, screen_size)
    blurred_bg = cv2.GaussianBlur(blurred_bg, (99, 99), 30)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret or media_updated.is_set():
            break

        frame = rotate_frame(frame, rotation)
        try:
            frame = cv2.resize(frame, (new_w, screen_h))
        except Exception as e:
            print(f"❌ Erreur resize vidéo {path} : {e}")
            break

        composed = blurred_bg.copy()
        x = (screen_w - new_w) // 2
        composed[0:screen_h, x:x+new_w] = frame
        composed = apply_overlay_if_needed(composed)

        cv2.imshow("MediaViewer", composed)
        cv2.setWindowProperty("MediaViewer", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        if cv2.waitKey(30) & 0xFF == ord('q'):
            break

    cap.release()
    del blurred_bg
    gc.collect()


# === SURVEILLANCE ===

class MediaWatcher(FileSystemEventHandler):
    def on_any_event(self, event):
        global media_list
        media_list[:] = load_media_list()
        media_updated.set()


def watch_folder():
    """Surveille le dossier media"""
    event_handler = MediaWatcher()
    observer = Observer()
    observer.schedule(event_handler, MEDIA_FOLDER, recursive=False)
    observer.start()


# === MAIN ===

def main():
    global media_list, apply_auto_night_mode

    screen_size = get_screen_resolution()
    cv2.namedWindow("MediaViewer", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("MediaViewer", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    # Démarrage du watcher
    Thread(target=watch_folder, daemon=True).start()

    current_img = np.zeros((screen_size[1], screen_size[0], 3), dtype=np.uint8)
    index = 0
    config = load_config()
    media_list = load_media_list()

    if config.get("apply_auto_night_mode", False):
        apply_auto_night_mode = True

    def apply_filters():
        filtered = media_list[:]
        if not config.get("show_images", True):
            filtered = [f for f in filtered if os.path.splitext(f)[1].lower() not in IMAGE_EXT]
        if not config.get("show_videos", True):
            filtered = [f for f in filtered if os.path.splitext(f)[1].lower() not in VIDEO_EXT]
        if config.get("display_order") == "random":
            random.shuffle(filtered)
        else:
            filtered.sort()
        return filtered

    display_list = apply_filters()

    while True:
        if media_updated.is_set():
            config = load_config()
            if config.get("black_screen", False):
                black_frame = np.zeros((screen_size[1], screen_size[0], 3), dtype=np.uint8)
                black_frame = apply_overlay_if_needed(black_frame)
                cv2.imshow("MediaViewer", black_frame)
                cv2.setWindowProperty("MediaViewer", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                if cv2.waitKey(1000) & 0xFF == ord('q'):
                    break
                continue
            media_list = load_media_list()
            new_display_list = apply_filters()
            media_updated.clear()
            if new_display_list != display_list:
                display_list = new_display_list
                index = 0

        if not display_list:
            time.sleep(1)
            continue

        if index >= len(display_list):
            index = 0

        config = load_config()
        display_list = apply_filters()
        path = display_list[index]
        ext = os.path.splitext(path)[1].lower()

        try:
            if ext in IMAGE_EXT:
                next_img = apply_overlay_if_needed(show_image(path, screen_size))
                fade_transition(current_img, next_img)
                current_img = next_img.copy()
                del next_img
                gc.collect()
                if cv2.waitKey(int(config.get("image_duration", 3)) * 1000) & 0xFF == ord('q'):
                    break
            elif ext in VIDEO_EXT:
                show_video(path, screen_size)
        except Exception as e:
            print(f"Erreur avec {path} : {e}")

        gc.collect()
        index += 1


if __name__ == "__main__":
    main()
