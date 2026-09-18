"""
Yuanx Personal System Assistant - Discord Edition
Pure command dispatch
"""

import os
import io
import re
import time
import random
import queue
import asyncio
import threading
import subprocess
import webbrowser
import urllib.parse
import urllib.request
import json
from pathlib import Path
import cv2
import shutil
import tempfile
import numpy as np
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from ctypes import POINTER, cast
from comtypes import CLSCTX_ALL
import sounddevice as sd
from pynput import mouse, keyboard
from scipy.io.wavfile import write as write_wav
import credentials

import discord
from PIL import ImageGrab
import psutil
import pyautogui
from playwright.async_api import async_playwright

DISCORD_BOT_TOKEN = credentials.fetch_discord_bot_token()
AUTHORIZED_USER_ID = credentials.fetch_authorized_user_id()
PREFIX = "."

PLAYLIST_FILE = "playlists.txt"
APP_FILE = "apps.txt"
SPOTIFY_PROFILE = Path(__file__).resolve().parent / "spotify_playwright_profile"
SPOTIFY_PLAY_BUTTON = Path(__file__).resolve().parent / "spotify_images" / "play.png"
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

ONLINE_QUOTES = [
    "🟢 Yuanx online. Ready to roll, boss.",
    "🟢 Core systems nominal. What's the move?",
    "🟢 Yuanx loaded and standing by. Keep me busy.",
]

IS_ARMED = False
ARM_LOCK = False
SENTINEL_LISTENERS_STARTED = False

# =========================
# Storage
# =========================

def load_playlists():
    if not os.path.exists(PLAYLIST_FILE):
        return {}
    playlists = {}
    with open(PLAYLIST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "=" not in line:
                continue
            name, url = line.split("=", 1)
            url = url.strip()
            if url.startswith("https://open.spotify.com/"):
                playlists[name.strip().lower()] = url
    return playlists

def save_playlists(playlists):
    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        for name, url in playlists.items():
            f.write(f"{name}={url}\n")

PLAYLISTS = load_playlists()
PENDING_PLAYLISTS = {}

def load_apps():
    if not os.path.exists(APP_FILE):
        return {}
    apps = {}
    with open(APP_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "=" not in line:
                continue
            name, path = line.split("=", 1)
            if path.strip():
                apps[name.strip().lower()] = path.strip()
    return apps

def save_apps(apps):
    with open(APP_FILE, "w", encoding="utf-8") as f:
        for name, path in apps.items():
            f.write(f"{name}={path}\n")

APPS = load_apps()

# =========================
# Spotify
# =========================

def extract_context_info(url):
    match = re.search(
        r"https?://open\.spotify\.com/(?:playlist|album)/([A-Za-z0-9]+)",
        url,
    )
    if not match:
        raise ValueError("Invalid Spotify playlist/album link.")
    context_id = match.group(1)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    context_si = query.get("si", [None])[0]
    if not context_si:
        raise ValueError("The playlist/album link must contain its 'si' value.")
    return context_id, context_si

def extract_track_id(url):
    match = re.search(
        r"https?://open\.spotify\.com/track/([A-Za-z0-9]+)",
        url,
    )
    if not match:
        raise ValueError("Invalid Spotify track link.")
    return match.group(1)

def build_spotify_url(track_url, context_url):
    track_id = extract_track_id(track_url)
    context_id, context_si = extract_context_info(context_url)
    return (
        f"https://open.spotify.com/track/{track_id}"
        f"?context=spotify:playlist:{context_id}"
        f"&si={context_si}"
    )

spotify_jobs = queue.Queue()

def spotify_process_running():
    for process in psutil.process_iter(["name"]):
        try:
            if (process.info["name"] or "").lower() == "spotify.exe":
                return True
        except Exception:
            pass
    return False

def kill_spotify():
    subprocess.run(
        "taskkill /f /im Spotify.exe",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
def find_spotify_play_button():
    time.sleep(2)
    screenshot = pyautogui.screenshot()
    frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    lower = np.array([35, 100, 100])
    upper = np.array([90, 255, 255])
    mask = cv2.inRange(hsv, lower, upper)

    h, w = mask.shape
    roi = mask[int(h * 0.10):int(h * 0.40), int(w * 0.20):int(w * 0.80)]

    contours, _ = cv2.findContours(
        roi,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    candidates = []

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 300 or area > 20000:
            continue

        x, y, cw, ch = cv2.boundingRect(contour)
        ratio = cw / ch

        if 0.75 <= ratio <= 1.25:
            cx = x + cw // 2 + int(w * 0.20)
            cy = y + ch // 2 + int(h * 0.10)
            candidates.append((area, cx, cy, cw, ch))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    _, x, y, _, _ = candidates[0]
    return x, y

async def playwright_open_spotify(url):
    context = None
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                str(SPOTIFY_PROFILE),
                headless=False,
                viewport=None,
                args=[
                    "--start-maximized",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            page = context.pages[0] if context.pages else await context.wait_for_event(
                "page", timeout=10000
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            for _ in range(100):
                if spotify_process_running():
                    await asyncio.sleep(3)
                    return "Spotify opened successfully."
                await asyncio.sleep(0.1)

            await asyncio.sleep(3)
            return "Spotify launch was triggered, but Spotify.exe was not detected."
    except Exception as e:
        return f"Playwright Spotify error: {e}"
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass

def spotify_worker():
    while True:
        url, result_queue = spotify_jobs.get()
        try:
            result_queue.put(asyncio.run(playwright_open_spotify(url)))
        except Exception as e:
            result_queue.put(f"Playwright Spotify error: {e}")
        finally:
            spotify_jobs.task_done()

threading.Thread(
    target=spotify_worker,
    name="SpotifyPlaywright",
    daemon=True,
).start()

def focus_spotify():
    import ctypes
    import time

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    spotify_hwnd = None

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p
    )

    def callback(hwnd, lParam):
        nonlocal spotify_hwnd

        if not user32.IsWindowVisible(hwnd):
            return True

        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        try:
            process = psutil.Process(pid.value)
            if process.name().lower() == "spotify.exe":
                spotify_hwnd = hwnd
                return False
        except Exception:
            pass

        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)

    if not spotify_hwnd:
        return False

    try:
        if user32.IsIconic(spotify_hwnd):
            user32.ShowWindow(spotify_hwnd, 9)

        foreground_hwnd = user32.GetForegroundWindow()
        foreground_thread = user32.GetWindowThreadProcessId(
            foreground_hwnd, None
        )
        spotify_thread = user32.GetWindowThreadProcessId(
            spotify_hwnd, None
        )
        current_thread = kernel32.GetCurrentThreadId()

        attached_foreground = False
        attached_spotify = False

        try:
            if current_thread != foreground_thread:
                attached_foreground = bool(
                    user32.AttachThreadInput(
                        current_thread,
                        foreground_thread,
                        True
                    )
                )

            if current_thread != spotify_thread:
                attached_spotify = bool(
                    user32.AttachThreadInput(
                        current_thread,
                        spotify_thread,
                        True
                    )
                )

            user32.BringWindowToTop(spotify_hwnd)
            user32.SetActiveWindow(spotify_hwnd)
            user32.SetForegroundWindow(spotify_hwnd)
            user32.SetFocus(spotify_hwnd)

            time.sleep(0.4)

        finally:
            if attached_spotify:
                user32.AttachThreadInput(
                    current_thread,
                    spotify_thread,
                    False
                )

            if attached_foreground:
                user32.AttachThreadInput(
                    current_thread,
                    foreground_thread,
                    False
                )

        return user32.GetForegroundWindow() == spotify_hwnd

    except Exception as e:
        print(f"Spotify focus error: {e}")
        return False

def spotify_open_url(url):
    result_queue = queue.Queue(maxsize=1)
    spotify_jobs.put((url, result_queue))
    return result_queue.get()

def spotify_play_link(url):
    try:
        if not re.match(r"^https://open\.spotify\.com/", url, re.I):
            return "Invalid Spotify link."

        result = spotify_open_url(url)
        if not result:
            return "Failed to open Spotify link."

        time.sleep(1)
        pyautogui.press("enter")
        return "Spotify link opened and played."
    except Exception as e:
        return f"Spotify play error: {e}"

def spotify_play_playlist(name):
    name = name.strip().lower()
    if name not in PLAYLISTS:
        return f"Playlist '{name}' is not saved."
    result = spotify_open_url(PLAYLISTS[name])
    time.sleep(1)
    pyautogui.press("enter")
    return f"{result}\nPlaylist: {name}" if result.startswith("Spotify opened successfully") else result

def spotify_search(text):
    text = text.strip()
    if not text:
        return f"Usage: {PREFIX}spotify search <song or artist>"

    try:
        kill_spotify()
        encoded = urllib.parse.quote(text)
        os.system(f"start spotify:search:{encoded}")

        time.sleep(5)

        # Actually activate Spotify so its UI refreshes
        if not focus_spotify():
            print("Warning: Spotify could not be activated.")

        time.sleep(0.5)

        for _ in range(40):
            position = find_spotify_play_button()

            if position:
                x, y = position
                print(f"Spotify Play button detected at ({x}, {y})")

                pyautogui.moveTo(x, y, duration=0.3)
                time.sleep(0.2)
                pyautogui.click()

                return f"Playing first result for: {text}"

            time.sleep(0.25)

        return f"Spotify search opened, but Play button was not found for: {text}"

    except Exception as e:
        print(f"Spotify search error: {type(e).__name__}: {repr(e)}")
        return f"Spotify search error: {type(e).__name__}: {repr(e)}"
    
def spotify_add_playlist(name, context_url):
    try:
        name = name.strip().lower()
        if not name:
            return "Playlist name can't be empty."
        extract_context_info(context_url)
        PENDING_PLAYLISTS[name] = context_url.strip()
        return (
            f"Playlist '{name}' loaded.\n"
            "Now send any track link from that playlist/album."
        )
    except Exception as e:
        return f"Add playlist error: {e}"

def spotify_finish_add_playlist(track_url):
    if not PENDING_PLAYLISTS:
        return None
    try:
        name, context_url = next(iter(PENDING_PLAYLISTS.items()))
        final_url = build_spotify_url(track_url, context_url)
        PLAYLISTS[name] = final_url
        save_playlists(PLAYLISTS)
        del PENDING_PLAYLISTS[name]
        return f"Saved playlist '{name}'.\nURL: {final_url}"
    except ValueError:
        return None
    except Exception as e:
        return f"Add playlist error: {e}"

def spotify_list_playlists():
    if not PLAYLISTS:
        return "🎵 No Spotify playlists saved."
    return "🎵 Saved Spotify playlists:\n" + "\n".join(
        f"• {name}" for name in sorted(PLAYLISTS)
    )

def spotify_remove_playlist(name):
    name = name.strip().lower()
    if name not in PLAYLISTS:
        return f"Playlist '{name}' does not exist."
    del PLAYLISTS[name]
    save_playlists(PLAYLISTS)
    return f"Removed playlist '{name}'."

def spotify_help():
    return (
        "🎵 **Spotify commands**\n\n"
        f"`{PREFIX}spotify plink <link>`\n"
        f"`{PREFIX}spotify plist <name>`\n"
        f"`{PREFIX}spotify list`\n"
        f"`{PREFIX}spotify addlist <name> <playlist/album link>`\n"
        f"`{PREFIX}spotify rmlist <name>`\n"
        f"`{PREFIX}spotify search <text>`\n"
    )

# =========================
# Media
# =========================

def action_media_control(action, amount=10):
    try:
        act = action.lower().strip()

        if act in ["play", "pause", "playpause", "resume"]:
            pyautogui.press("playpause")
            return "Play/Pause toggled."

        if act in ["next", "skip"]:
            pyautogui.press("nexttrack")
            return "Skipped to next track."

        if act in ["prev", "previous", "back"]:
            pyautogui.press("prevtrack")
            return "Returned to previous track."

        if act in ["mute", "unmute"]:
            pyautogui.press("volumemute")
            return "Mute toggled."

        devices = AudioUtilities.GetSpeakers()
        volume = devices.EndpointVolume

        current = volume.GetMasterVolumeLevelScalar()

        if act in ["up", "volume_up", "louder"]:
            new_volume = min(1.0, current + amount / 100)
            volume.SetMasterVolumeLevelScalar(new_volume, None)
            return f"Volume increased by {amount}% → {round(new_volume * 100)}%."

        if act in ["down", "volume_down", "quieter"]:
            new_volume = max(0.0, current - amount / 100)
            volume.SetMasterVolumeLevelScalar(new_volume, None)
            return f"Volume decreased by {amount}% → {round(new_volume * 100)}%."

        return f"Unknown media command: {action}"

    except Exception as e:
        return f"Media control error: {e}"

# =========================
# Weather
# =========================

def action_weather():
    try:
        weather_url = (
            "https://api.open-meteo.com/v1/forecast?"
            "latitude=5.4164&longitude=100.3327"
            "&current=temperature_2m,relative_humidity_2m,"
            "apparent_temperature,weather_code,wind_speed_10m"
            "&hourly=precipitation_probability"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
            "sunrise,sunset,uv_index_max,precipitation_probability_max"
            "&timezone=Asia%2FKuala_Lumpur&forecast_days=1"
        )

        with urllib.request.urlopen(weather_url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        air_url = (
            "https://air-quality-api.open-meteo.com/v1/air-quality?"
            "latitude=5.4164&longitude=100.3327"
            "&current=pm10,pm2_5,us_aqi"
            "&timezone=Asia%2FKuala_Lumpur"
        )
        with urllib.request.urlopen(air_url, timeout=10) as response:
            air_data = json.loads(response.read().decode("utf-8"))

        current = data["current"]
        daily = data["daily"]
        hourly = data.get("hourly", {})
        air_current = air_data["current"]

        date_part = current["time"].split("T")[0]
        y, m, d = date_part.split("-")
        date_formatted = f"{d}/{m}/{y}"

        sunrise = daily["sunrise"][0].split("T")[-1]
        sunset = daily["sunset"][0].split("T")[-1]

        rain_peaks = []
        if hourly and "precipitation_probability" in hourly:
            times = hourly.get("time", [])
            probs = hourly.get("precipitation_probability", [])
            for t_str, p in zip(times, probs):
                if p >= 60:
                    rain_peaks.append(t_str.split("T")[-1])

        if rain_peaks:
            start_t = rain_peaks[0]
            end_t = rain_peaks[-1]
            if start_t == end_t:
                rain_window = f"Peak ~{start_t}"
            else:
                rain_window = f"Peak: {start_t} – {end_t}"
        else:
            max_prob = daily["precipitation_probability_max"][0]
            rain_window = "Scattered showers" if max_prob >= 40 else "Low risk"

        weather_codes = {
            0: "☀️ Clear sky",
            1: "🌤️ Mainly clear",
            2: "⛅ Partly cloudy",
            3: "☁️ Overcast",
            45: "🌫️ Fog",
            48: "🌫️ Depositing rime fog",
            51: "🌦️ Light drizzle",
            53: "🌦️ Moderate drizzle",
            55: "🌧️ Dense drizzle",
            61: "🌦️ Slight rain",
            63: "🌧️ Moderate rain",
            65: "🌧️ Heavy rain",
            71: "🌨️ Slight snow",
            73: "🌨️ Moderate snow",
            75: "🌨️ Heavy snow",
            80: "🌦️ Rain showers",
            81: "🌧️ Moderate rain showers",
            82: "⛈️ Violent rain showers",
            95: "⛈️ Thunderstorm",
            96: "⛈️ Thunderstorm with hail",
            99: "⛈️ Thunderstorm with heavy hail",
        }

        uv = daily["uv_index_max"][0]
        if uv <= 2:
            uv_level = f"{uv} (Low)"
        elif uv <= 5:
            uv_level = f"{uv} (Moderate)"
        elif uv <= 7:
            uv_level = f"{uv} (High)"
        elif uv <= 10:
            uv_level = f"{uv} (Very High)"
        else:
            uv_level = f"{uv} (Extreme)"

        aqi = air_current.get("us_aqi", 0)
        pm25 = air_current.get("pm2_5", 0)
        pm10 = air_current.get("pm10", 0)

        if aqi <= 50:
            aqi_status = f"{aqi} (Good 🟢)"
        elif aqi <= 100:
            aqi_status = f"{aqi} (Moderate 🟡)"
        elif aqi <= 150:
            aqi_status = f"{aqi} (Unhealthy for Sensitive Groups 🟠)"
        elif aqi <= 200:
            aqi_status = f"{aqi} (Unhealthy / Hazy 🔴)"
        elif aqi <= 300:
            aqi_status = f"{aqi} (Very Unhealthy 🟣)"
        else:
            aqi_status = f"{aqi} (Hazardous 🟤)"

        return (
            f"🌤️ **Pulau Pinang Weather Overview**\n"
            f"📅 `{date_formatted}` • {weather_codes.get(current['weather_code'], '🌡️ Unknown')}\n"
            f"────────────────────────\n"
            f"🌡️ **Temp:** {current['temperature_2m']}°C (Feels like {current['apparent_temperature']}°C)\n"
            f"💧 **Humidity:** {current['relative_humidity_2m']}%\n"
            f"💨 **Wind:** {current['wind_speed_10m']} km/h\n\n"
            f"📊 **Today's Forecast**\n"
            f"• 🌡️ **Range:** {daily['temperature_2m_min'][0]}°C — {daily['temperature_2m_max'][0]}°C\n"
            f"• 🌧️ **Precipitation:** {daily['precipitation_probability_max'][0]}% (`{rain_window}`)\n"
            f"• ☀️ **UV Index:** {uv_level}\n"
            f"• 🌅 **Sunrise:** {sunrise}  |  🌇 **Sunset:** {sunset}\n\n"
            f"😷 **Air Quality & Haze**\n"
            f"• 🫁 **AQI:** {aqi_status}\n"
            f"• 🌫️ **PM2.5:** {pm25} µg/m³\n"
            f"• 💨 **PM10:** {pm10} µg/m³\n"
        )
    except Exception as e:
        return f"Weather error: {e}"

# =========================
# System
# =========================

def action_capture_screen():
    try:
        screenshot = ImageGrab.grab()
        buf = io.BytesIO()
        screenshot.save(buf, format="JPEG", quality=80)
        buf.seek(0)
        return buf
    except Exception as e:
        return f"Screen capture error: {e}"
    
def action_capture_webcam():
    try:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            return None
        ret, frame = cap.read()
        cap.release()

        if ret:
            success, buffer = cv2.imencode(".jpg", frame)
            if success:
                return io.BytesIO(buffer.tobytes())
    except Exception as e:
        print(f"Webcam capture error: {e}")
    return None

def action_record_audio(duration=5, fs=44100):
    try:
        recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
        sd.wait()
        buf = io.BytesIO()
        write_wav(buf, fs, recording)
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Audio recording error: {e}")
        return None
    
def action_lock():
    try:
        subprocess.run(
            "rundll32.exe user32.dll,LockWorkStation",
            check=True,
        )
        return "Workstation locked."
    except Exception as e:
        return f"Lock error: {e}"

def action_telemetry():
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        drive = os.environ.get("SystemDrive", "C:") + "\\"
        disk = psutil.disk_usage(drive)
        batt = psutil.sensors_battery()
        batt_str = (
            f"{batt.percent}% "
            f"({'Charging' if batt.power_plugged else 'Battery'})"
            if batt else "Desktop / AC"
        )
        return (
            f"💻 CPU: {cpu}%\n"
            f"🧠 RAM: {mem.percent}% "
            f"({mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB)\n"
            f"💽 Drive C: {disk.percent}% "
            f"({disk.free // (1024**3)}GB free)\n"
            f"🔋 Power: {batt_str}"
        )
    except Exception as e:
        return f"Telemetry error: {e}"


def trigger_security_alarm(target_user_id):
    global IS_ARMED, ARM_LOCK
    if not IS_ARMED or ARM_LOCK:
        return

    ARM_LOCK = True

    webcam_io = action_capture_webcam()
    screen_io = action_capture_screen()
    action_lock()

    async def send_alarm_dm():
        global ARM_LOCK
        try:
            audio_io = await asyncio.to_thread(action_record_audio, 15)

            user = await client.fetch_user(target_user_id)
            files = []
            if webcam_io:
                files.append(discord.File(webcam_io, filename="intruder_cam.jpg"))
            if screen_io and not isinstance(screen_io, str):
                files.append(discord.File(screen_io, filename="intruder_screen.jpg"))
            if audio_io:
                files.append(discord.File(audio_io, filename="intruder_audio.wav"))

            await user.send(
                content="🚨 **Security Alert: Unauthorized physical interaction detected.**\nEvidence captured, 15s audio recorded, and workstation locked.",
                files=files
            )
        except Exception as e:
            print(f"Failed to send security alert DM: {e}")
        finally:
            await asyncio.sleep(30)
            ARM_LOCK = False

    asyncio.run_coroutine_threadsafe(send_alarm_dm(), client.loop)

def start_security_listeners(target_user_id):
    global SENTINEL_LISTENERS_STARTED
    if SENTINEL_LISTENERS_STARTED:
        return

    def on_move(x, y):
        if IS_ARMED and not ARM_LOCK:
            trigger_security_alarm(target_user_id)

    def on_click(x, y, button, pressed):
        if IS_ARMED and pressed and not ARM_LOCK:
            trigger_security_alarm(target_user_id)

    def on_press(key):
        if IS_ARMED and not ARM_LOCK:
            trigger_security_alarm(target_user_id)

    m_listener = mouse.Listener(on_move=on_move, on_click=on_click)
    k_listener = keyboard.Listener(on_press=on_press)
    m_listener.daemon = True
    k_listener.daemon = True
    m_listener.start()
    k_listener.start()
    SENTINEL_LISTENERS_STARTED = True

def action_screen_control(state):
    try:
        import ctypes

        user32 = ctypes.windll.user32

        if state.lower() == "off":
            user32.SendMessageW(
                0xFFFF,
                0x0112,
                0xF170,
                2
            )
            return "🖥️ Screen turned off."

        if state.lower() == "on":
            pyautogui.moveRel(1, 0, duration=0.05)
            pyautogui.moveRel(-1, 0, duration=0.05)
            return "🖥️ Screen turned on."

        return "Usage: .control screen <on/off>"

    except Exception as e:
        return f"Screen control error: {e}"

def action_cmd(command):
    try:
        command = command.strip()

        if not command:
            return "Usage: .cmd <command>"

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if output and error:
            result_text = f"{output}\n\n[stderr]\n{error}"
        elif output:
            result_text = output
        elif error:
            result_text = error
        else:
            result_text = f"Command completed with exit code {result.returncode}."

        if len(result_text) > 1900:
            result_text = result_text[:1900] + "\n...[truncated]"

        return f"```text\n{result_text}\n```"

    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."

    except Exception as e:
        return f"Command error: {e}"


async def action_upload(attachment):
    try:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filename = os.path.basename(attachment.filename)
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        await attachment.save(save_path)
        return save_path
    except Exception as e:
        return f"Upload error: {e}"
    
# =========================
# Applications
# =========================
def find_and_prep_file(query):
    query = query.strip().strip('"')
    target_path = None

    if os.path.exists(query):
        target_path = Path(query)
    else:
        script_dir = Path(__file__).resolve().parent
        user_home = Path.home()
        
        search_dirs = [
            script_dir,
            user_home / "Desktop",
            user_home / "OneDrive" / "Desktop",
            user_home / "OneDrive" / "桌面",
            user_home / "Downloads",
            user_home / "Documents",
            user_home / "OneDrive" / "文件",
        ]

        valid_dirs = []
        for d in search_dirs:
            if d.exists() and d not in valid_dirs:
                valid_dirs.append(d)

        matches = []
        query_lower = query.lower()

        for base_dir in valid_dirs:
            try:
                for root, dirs, files in os.walk(base_dir):
                    for f in files:
                        if query_lower in f.lower():
                            matches.append(Path(root) / f)
                    for d in dirs:
                        if query_lower in d.lower():
                            matches.append(Path(root) / d)
            except Exception:
                continue

        if matches:
            matches.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            target_path = matches[0]

    if not target_path or not target_path.exists():
        dirs_checked = "\n".join([f"• `{d}`" for d in valid_dirs])
        return None, None, f"File or folder not found: `{query}`\n\n**Searched locations:**\n{dirs_checked}"

    if target_path.is_dir():
        temp_dir = tempfile.gettempdir()
        zip_base_name = os.path.join(temp_dir, target_path.name)
        zip_path = Path(shutil.make_archive(zip_base_name, "zip", target_path))

        size_mb = zip_path.stat().st_size / (1024 * 1024)
        if size_mb > 24:
            if zip_path.exists():
                zip_path.unlink()
            return None, None, f"Folder too large ({size_mb:.1f}MB). Exceeds Discord 25MB limit."

        return zip_path, target_path, None

    size_mb = target_path.stat().st_size / (1024 * 1024)
    if size_mb > 24:
        return None, None, f"File too large ({size_mb:.1f}MB). Exceeds Discord 25MB limit."

    return target_path, target_path, None

def action_save_app(name, path):
    try:
        name = name.strip().lower()
        path = path.strip().strip('"')

        if not name:
            return "Application name can't be empty."
        if not path:
            return "Application path can't be empty."
        if not os.path.isfile(path):
            return f"File does not exist:\n{path}"

        APPS[name] = path
        save_apps(APPS)
        return f"Saved application '{name}'.\nPath: {path}"
    except Exception as e:
        return f"Save app error: {e}"

def action_list_apps():
    if not APPS:
        return "📦 No saved applications."
    return "📦 Saved applications:\n" + "\n".join(
        f"• {name}" for name in sorted(APPS)
    )

def action_remove_app(name):
    name = name.strip().lower()
    if name not in APPS:
        return f"Application '{name}' does not exist."
    del APPS[name]
    save_apps(APPS)
    return f"Removed application '{name}'."

def action_open(target):
    try:
        cleaned = target.strip()

        if cleaned.startswith(("http://", "https://", "www.")):
            if not cleaned.startswith("http"):
                cleaned = "https://" + cleaned
            webbrowser.open(cleaned)
            return f"Opened URL: {cleaned}"

        app_name = cleaned.lower()

        if app_name in APPS:
            path = APPS[app_name]
            if not os.path.isfile(path):
                return f"Saved application path no longer exists:\n{path}"
            subprocess.Popen([path], shell=False)
            return f"Launched saved application: {app_name}"

        app_map = {
            "spotify": "spotify:",
            "chrome": "chrome",
            "notepad": "notepad",
            "calculator": "calc",
            "calc": "calc",
            "task manager": "taskmgr",
            "taskmgr": "taskmgr",
            "explorer": "explorer",
            "paint": "mspaint",
            "cmd": "cmd",
            "powershell": "powershell",
        }

        subprocess.Popen(app_map.get(app_name, cleaned), shell=True)
        return f"Launched application: {cleaned}"
    except Exception as e:
        return f"Launch error: {e}"

def action_close(proc_name):
    try:
        name = proc_name.lower().strip()
        if not name.endswith(".exe"):
            name += ".exe"

        result = subprocess.run(
            f"taskkill /f /im {name}",
            shell=True,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return f"Could not close process: {proc_name}"

        return f"Closed process: {proc_name}."
    except Exception as e:
        return f"Process termination error: {e}"

# =========================
# Background
# =========================

async def background_sentinel():
    alerted = False

    while True:
        try:
            batt = psutil.sensors_battery()

            if batt and not batt.power_plugged and batt.percent <= 20 and not alerted:
                await send_authorized_message(
                    f"⚠️ Low Battery: {batt.percent}% remaining. Connect the charger!"
                )
                alerted = True
            elif batt and batt.power_plugged:
                alerted = False
        except Exception:
            pass

        await asyncio.sleep(30)

async def send_authorized_message(content):
    try:
        user = await client.fetch_user(AUTHORIZED_USER_ID)
        await user.send(content)
        print(f"DM sent to {user} ({AUTHORIZED_USER_ID})")
        return True
    except Exception as e:
        print(f"Failed to send DM: {e}")
        return False

def is_authorized(message):
    return message.author.id == AUTHORIZED_USER_ID

# =========================
# Discord
# =========================

@client.event
async def on_ready():
    print(f"Yuanx logged in as {client.user} (ID: {client.user.id})")

    if not getattr(client, "_sent_online_message", False):
        client._sent_online_message = True
        await send_authorized_message(random.choice(ONLINE_QUOTES))

    if not getattr(client, "_battery_task_started", False):
        client._battery_task_started = True
        asyncio.create_task(background_sentinel())

    start_security_listeners(AUTHORIZED_USER_ID)

@client.event
async def on_message(message):
    if message.author.bot or not is_authorized(message):
        return

    text = message.content.strip()
    if not text:
        return

    # =========================
    # Start
    # =========================

    if text == f"{PREFIX}start":
        await message.channel.send(
            "Yuanx is ready.\n\n"
            "🎵 **Spotify**\n"
            f"`{PREFIX}spotify plink <link>` — Play a Spotify track/playlist link\n"
            f"`{PREFIX}spotify plist <name>` — Play a saved playlist\n"
            f"`{PREFIX}spotify list` — Show saved playlists\n"
            f"`{PREFIX}spotify addlist <name> <playlist/album link>` — Save a playlist/album\n"
            f"`{PREFIX}spotify rmlist <name>` — Remove a saved playlist\n"
            f"`{PREFIX}spotify search <text>` — Search Spotify\n\n"

            "🌤️ **Weather**\n"
            f"`{PREFIX}weather` — Show current weather information\n\n"

            "📦 **Applications**\n"
            f"`{PREFIX}open <app/url>` — Open an application or URL\n"
            f"`{PREFIX}saveapp <name> <exe path>` — Save an application shortcut\n"
            f"`{PREFIX}showapps` — Show saved applications\n"
            f"`{PREFIX}removeapp <name>` — Remove a saved application\n\n"

            "🎧 **Media**\n"
            f"`{PREFIX}play` — Play/resume media\n"
            f"`{PREFIX}pause` — Pause media\n"
            f"`{PREFIX}next` — Skip to the next track\n"
            f"`{PREFIX}prev` — Go to the previous track\n"
            f"`{PREFIX}mute` — Toggle mute\n"
            f"`{PREFIX}volup [amount]` — Increase system volume\n"
            f"`{PREFIX}voldown [amount]` — Decrease system volume\n\n"

            "🖥️ **System**\n"
            f"`{PREFIX}screenshot` — Capture and send a screenshot\n"
            f"`{PREFIX}lock` — Lock the computer\n"
            f"`{PREFIX}status` — Show system status\n"
            f"`{PREFIX}close <process name>` — Close a running process\n"
            f"`{PREFIX}control screen <on/off>` — Turn the display on/off\n"
            f"`{PREFIX}cmd <command>` — Execute a system command\n"
            f"`{PREFIX}upload` — Save Discord attachments to the local uploads folder\n"
            f"`{PREFIX}get <filename/path>` — Retrieve a local file and send it to Discord\n"
            f"`{PREFIX}peek` — View stored/uploaded files\n"
            f"`{PREFIX}arm` — Arm the security sentinel\n"
            f"`{PREFIX}disarm` — Disarm the security sentinel\n"
        )
        return

    # Weather
    if text == f"{PREFIX}weather":
        await message.channel.send(action_weather())
        return

    if text == f"{PREFIX}upload":
        if not message.attachments:
            await message.channel.send(
                f"Usage: `{PREFIX}upload` with a file attached to the message."
            )
            return

        saved_files = []

        for attachment in message.attachments:
            result = await action_upload(attachment)

            if result.startswith("Upload error:"):
                await message.channel.send(result)
                continue

            saved_files.append(result)

        if saved_files:
            files_text = "\n".join(f"📁 `{path}`" for path in saved_files)
            await message.channel.send(
                f"✅ **{len(saved_files)} file(s) saved successfully.**\n{files_text}"
            )

        return
    # Spotify
    spotify_prefix = f"{PREFIX}spotify"

    if text.startswith(spotify_prefix):
        arg = text[len(spotify_prefix):].strip()

        if not arg:
            await message.channel.send(spotify_help())
            return

        parts = arg.split(maxsplit=1)
        command = parts[0].lower()
        value = parts[1].strip() if len(parts) > 1 else ""

        if command == "plink":
            if not value:
                await message.channel.send(
                    f"Usage: `{PREFIX}spotify plink <Spotify link>`"
                )
                return
            await message.channel.send(spotify_play_link(value))

        elif command == "plist":
            if not value:
                await message.channel.send(
                    f"Usage: `{PREFIX}spotify plist <name>`"
                )
                return
            await message.channel.send(spotify_play_playlist(value))

        elif command == "list":
            await message.channel.send(spotify_list_playlists())

        elif command == "addlist":
            playlist_parts = value.split(maxsplit=1)
            if len(playlist_parts) < 2:
                await message.channel.send(
                    f"Usage: `{PREFIX}spotify addlist <name> <playlist/album link>`"
                )
                return
            name, context_url = playlist_parts
            await message.channel.send(
                spotify_add_playlist(name, context_url)
            )

        elif command == "rmlist":
            if not value:
                await message.channel.send(
                    f"Usage: `{PREFIX}spotify rmlist <name>`"
                )
                return
            await message.channel.send(spotify_remove_playlist(value))

        elif command == "search":
            if not value:
                await message.channel.send(
                    f"Usage: `{PREFIX}spotify search <text>`"
                )
                return
            await message.channel.send(spotify_search(value))

        elif command == "help":
            await message.channel.send(spotify_help())

        else:
            await message.channel.send(spotify_help())

        return

    # Pending playlist
    if PENDING_PLAYLISTS:
        result = spotify_finish_add_playlist(text)
        if result is not None:
            await message.channel.send(result)
            return

    # Media
    if text in [
        f"{PREFIX}play",
        f"{PREFIX}pause",
    ]:
        await message.channel.send(action_media_control("play"))
        return

    if text == f"{PREFIX}next":
        await message.channel.send(action_media_control("next"))
        return

    if text == f"{PREFIX}prev":
        await message.channel.send(action_media_control("prev"))
        return

    if text == f"{PREFIX}mute":
        await message.channel.send(action_media_control("mute"))
        return

    if text.startswith(f"{PREFIX}volup"):
        arg = text[len(f"{PREFIX}volup"):].strip()

        if not arg:
            amount = 10
        else:
            try:
                amount = int(arg)
                if amount < 1:
                    raise ValueError
            except ValueError:
                await message.channel.send(
                    f"Usage: `{PREFIX}volup [amount]`\n"
                    f"Example: `{PREFIX}volup 5`\n"
                    "Default: 10"
                )
                return

        await message.channel.send(action_media_control("up", amount))
        return

    if text.startswith(f"{PREFIX}voldown"):
        arg = text[len(f"{PREFIX}voldown"):].strip()

        if not arg:
            amount = 10
        else:
            try:
                amount = int(arg)
                if amount < 1:
                    raise ValueError
            except ValueError:
                await message.channel.send(
                    f"Usage: `{PREFIX}voldown [amount]`\n"
                    f"Example: `{PREFIX}voldown 5`\n"
                    "Default: 10"
                )
                return

        await message.channel.send(action_media_control("down", amount))
        return

    # Screenshot
    if text == f"{PREFIX}screenshot":
        result = action_capture_screen()

        if isinstance(result, str):
            await message.channel.send(result)
        else:
            await message.channel.send(
                "🖥️ Screen Capture",
                file=discord.File(result, filename="screenshot.jpg"),
            )
        return

    # Peek
    if text.startswith(f"{PREFIX}peek"):
        arg = text[len(f"{PREFIX}peek"):].strip()
        duration = 5
        if arg:
            try:
                duration = int(arg)
                if duration < 1 or duration > 300:
                    raise ValueError
            except ValueError:
                await message.channel.send("Usage: `.peek [seconds (1-300)]`\nDefault is 5 seconds.")
                return

        await message.channel.send(f"📸 Capturing evidence and recording {duration}s audio...")

        webcam_io = action_capture_webcam()
        screen_io = action_capture_screen()
        audio_io = await asyncio.to_thread(action_record_audio, duration)

        files = []
        if webcam_io:
            files.append(discord.File(webcam_io, filename="webcam_peek.jpg"))
        if screen_io and not isinstance(screen_io, str):
            files.append(discord.File(screen_io, filename="screen_peek.jpg"))
        if audio_io:
            files.append(discord.File(audio_io, filename="audio_peek.wav"))

        if files:
            await message.channel.send(files=files)
        else:
            await message.channel.send("⚠️ Failed to capture peek data.")
        return

    # Remote File / Folder Retrieval
    if text.startswith(f"{PREFIX}get"):
        await message.channel.send("🔍 Searching for file/folder...")
        query = text[len(f"{PREFIX}get"):].strip()
        if not query:
            await message.channel.send(
                f"Usage: `{PREFIX}get <file/folder name or path>`\n"
                f"Example: `{PREFIX}get ProjectFolder`"
            )
            return

        file_to_send, original_target, err = find_and_prep_file(query)
        if err:
            await message.channel.send(err)
            return

        is_folder = original_target.is_dir()
        label = "📦 **Folder (Zipped):**" if is_folder else "📄 **File:**"

        try:
            await message.channel.send(
                f"{label} `{original_target.name}`\n"
                f"📍 **Path:** `{original_target}`\n"
                "Uploading...",
                file=discord.File(str(file_to_send))
            )
        finally:
            # Clean up temporary zip file if it was created
            if is_folder and file_to_send.exists():
                file_to_send.unlink()
        return

    # Arm
    if text == f"{PREFIX}arm":
        global IS_ARMED, ARM_LOCK
        if IS_ARMED:
            await message.channel.send("⚠️ Security sentinel is already armed.")
            return

        await message.channel.send("🛡️ Arming security sentinel... You have 10 seconds to leave.")
        await asyncio.sleep(10)
        ARM_LOCK = False
        IS_ARMED = True
        await message.channel.send("🔒 **Security sentinel armed.** Any physical interaction will trigger capture and lock.")
        return

    # Disarm
    if text == f"{PREFIX}disarm":
        IS_ARMED = False
        await message.channel.send("🔓 Security sentinel disarmed.")
        return

    # Lock
    if text == f"{PREFIX}lock":
        await message.channel.send(action_lock())
        return

    # Status
    if text == f"{PREFIX}status":
        await message.channel.send(action_telemetry())
        return

    # Open
    if text.startswith(f"{PREFIX}open"):
        arg = text[len(f"{PREFIX}open"):].strip()

        if not arg:
            await message.channel.send(
                f"Usage: `{PREFIX}open <app or url>`"
            )
            return

        await message.channel.send(action_open(arg))
        return

    # Save app
    if text.startswith(f"{PREFIX}saveapp"):
        arg = text[len(f"{PREFIX}saveapp"):].strip()
        parts = arg.split(maxsplit=1)

        if len(parts) < 2:
            await message.channel.send(
                f"Usage: `{PREFIX}saveapp <name> <exe path>`\n"
                "Example:\n"
                f"`{PREFIX}saveapp chrome "
                r"C:\Program Files\Google\Chrome\Application\chrome.exe`"
            )
            return

        name, path = parts
        await message.channel.send(action_save_app(name, path))
        return

    # Show apps
    if text == f"{PREFIX}showapps":
        await message.channel.send(action_list_apps())
        return

    # Remove app
    if text.startswith(f"{PREFIX}removeapp"):
        arg = text[len(f"{PREFIX}removeapp"):].strip()

        if not arg:
            await message.channel.send(
                f"Usage: `{PREFIX}removeapp <name>`"
            )
            return

        await message.channel.send(action_remove_app(arg))
        return

    if text.startswith(f"{PREFIX}control"):
        arg = text[len(f"{PREFIX}control"):].strip()
        parts = arg.split()

        if len(parts) != 2 or parts[0].lower() != "screen":
            await message.channel.send(
                f"Usage: `{PREFIX}control screen <on/off>`"
            )
            return

        await message.channel.send(
            action_screen_control(parts[1])
        )
        return
    # Close
    if text.startswith(f"{PREFIX}close"):
        arg = text[len(f"{PREFIX}close"):].strip()

        if not arg:
            await message.channel.send(
                f"Usage: `{PREFIX}close <process name>`"
            )
            return

        await message.channel.send(action_close(arg))
        return

    if text.startswith(f"{PREFIX}cmd"):
        command = text[len(f"{PREFIX}cmd"):].strip()
        if not command:
            await message.channel.send(f"Usage: `{PREFIX}cmd <command>`")
            return
        await message.channel.send(action_cmd(command))
        return
    # Unknown
    if text.startswith(PREFIX):
        await message.channel.send(
            f"Unrecognized command. Send `{PREFIX}start` to see available commands."
        )
        return

# =========================
# Start
# =========================

if __name__ == "__main__":
    print("Yuanx Discord bot is starting...")
    client.run(DISCORD_BOT_TOKEN)