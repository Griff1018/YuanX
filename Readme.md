# 🟢 YuanX Personal System Assistant (Discord Edition)

**YuanX** is a lightweight, remote system control and security sentinel bot powered by Python and Discord. It allows authorized users to remotely control, monitor, inspect, and secure their Windows machines via standard Discord commands. It is also specialized in Spotify controll.

## 🌟 Key Features

* **🛡️ Security Sentinel:** Arm/disarm physical peripheral monitors. Any unauthorized mouse movement, click, or keystroke triggers an automated response—capturing webcam images, screen state, and a 15-second ambient audio recording before immediately locking the workstation and DMing the evidence to you.

* **🎵 Advanced Spotify Integration:** Seamlessly search, play specific tracks, or launch saved playlists using automated UI interactions (via Playwright and PyAutoGUI).

* **💻 System Telemetry & Control:** Monitor CPU, RAM, disk space, and battery levels in real-time. Lock workstation, turn displays on/off, or kill specific processes remotely.

* **📂 File Management & Remote Search:** Search for files or folders across common paths (Desktop, Documents, Downloads, etc.), automatically zip folders under 25MB, and upload/download files directly via Discord.

* **📸 Live Inspection (`.peek`):** Remotely request an on-demand webcam snapshot, screenshot, and brief audio clip without locking the computer.

* **🌤️ Local Weather & Air Quality:** Query real-time weather forecasts, rain peak windows, UV index, and AQI/haze metrics (defaulted to Pulau Pinang via Open-Meteo).

* **🖥️ Remote Shell Execution:** Run shell commands directly via Discord and receive stdout/stderr output formatted inline.

* **🎧 Media & Volume Controls:** Adjust master system volume, mute, skip tracks, and control playback remotely.

## 📋 Prerequisites

* **Operating System:** Windows 10 / 11 (uses Windows API `ctypes`, `user32.dll`, and `rundll32.exe`).

* **Python:** Version 3.9 or higher.

* **Discord Bot Token & User ID:** You will need a registered Discord Bot and your personal Discord User ID.

* **Peripherals:** A working webcam and microphone (for security and inspection features).

## 📥 Installation

1. **Clone the Repository:**

   ```
   git clone https://github.com/your-username/yuanx-system-assistant.git
   cd yuanx-system-assistant
   
   ```

2. **Set Up a Virtual Environment (Optional):**

   ```
   python -m venv venv
   venv\Scripts\activate
   
   ```

3. **Install Dependencies:**

   ```
   .\installation.bat
   
   ```
   OR
   ```
   py -m pip install discord.py pyautogui opencv-python numpy psutil pillow pycaw comtypes sounddevice scipy pynput playwright
   py -m playwright install chromium
   ```



## ⚙️ Configuration

1. **Credentials Setup:**
   Create a file named `credentials.py` in the root directory:

   ```
   # credentials.py
   
   def fetch_discord_bot_token():
       return "YOUR_DISCORD_BOT_TOKEN_HERE"
   
   def fetch_authorized_user_id():
       return 123456789012345678  # Replace with your numeric Discord User ID
   
   ```

2. **Discord Bot Configuration:**

   * Go to the [Discord Developer Portal](https://discord.com/developers/applications).

   * Ensure **Message Content Intent** is enabled under the **Bot** tab.

   * Invite the bot to a private server and send commands directly via Direct Message.

## 🚀 Usage

1. Edit 
Run the assistant script:

```
python YuanX_modified.py

```

Upon successful connection, the bot will log into Discord and send a ready message directly to your authorized Discord account.

## 🎮 Command Reference

Send `.start` in Discord to view the complete interactive menu.

### 🛡️ Security & Monitoring

| 

| **Command** | **Description** | 
| `.arm` | Arms the security sentinel after a 10-second countdown. | 
| `.disarm` | Disarms the security sentinel. | 
| `.peek [seconds]` | Captures an immediate webcam image, screenshot, and audio recording (1-300 seconds). | 
| `.lock` | Immediately locks the Windows workstation. | 
| `.status` | Returns system telemetry (CPU, RAM, Disk C, Battery status). | 

### 📁 File Management & Remote Access

| **Command** | **Description** | 
| `.get <name or path>` | Searches common directories for a file or folder, zips folders, and sends them via Discord (<25MB). | 
| `.upload` | Saves any file attached to the Discord message into the local `uploads/` folder. | 
| `.cmd <command>` | Executes a command prompt command remotely and returns the terminal output. | 

### 🎵 Spotify & Media Control

| **Command** | **Description** | 
| `.spotify plink <link>` | Opens and plays a direct Spotify track/playlist link. | 
| `.spotify search <query>` | Searches Spotify for a track/artist and automatically clicks play. | 
| `.spotify addlist <name> <link>` | Saves a Spotify playlist or album shortcut under a name. | 
| `.spotify plist <name>` | Opens and plays a saved playlist. | 
| `.spotify list` | Lists all saved Spotify playlists. | 
| `.spotify rmlist <name>` | Deletes a saved playlist shortcut. | 
| `.play` / `.pause` | Toggles media play/pause. | 
| `.next` / `.prev` | Skips to the next or previous media track. | 
| `.volup [amount]` | Increases master system volume (default: 10%). | 
| `.voldown [amount]` | Decreases master system volume (default: 10%). | 
| `.mute` | Toggles master system mute. | 

### 📦 Applications & System Control

| **Command** | **Description** | 
| `.open <app/url>` | Launches an app or opens a URL in the default browser. | 
| `.saveapp <name> <path>` | Saves an application executable path under a custom shortcut name. | 
| `.showapps` | Lists saved app shortcuts. | 
| `.removeapp <name>` | Deletes a saved app shortcut. | 
| `.close <process.exe>` | Forcefully terminates a running process by name. | 
| `.control screen <on/off>` | Powers off or wakes up connected displays. | 
| `.screenshot` | Takes a screenshot of the main screen and sends it as an image. | 
| `.weather` | Displays weather forecast, UV index, rain windows, and AQI metrics. | 

## 🔒 Security Notice

* **Authorized Access Only:** The bot checks `message.author.id` against `AUTHORIZED_USER_ID`. Commands issued by any other user account will be ignored.

* **Command Shell Caution:** The `.cmd` command runs commands with the privileges of the script host process. Keep your Discord bot token private and secure.

## Possible Issues
There might have some issues and bugs during usage. here is what you can do
1. **Spotify Command**
   You can adjust `time.sleep()` period if your PC takes too long time for Spotify.exe startup during `.spotify search` causing openCv button search timeout. 



## 📄 License

This project is open-source and available under the [MIT License](https://opensource.org/licenses/MIT).