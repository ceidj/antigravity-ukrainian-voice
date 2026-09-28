import sys
import os
import re
import io
import json
import queue
import threading
import subprocess
import base64
import struct
import winsound
import scipy.signal
from scipy.signal.windows import kaiser
scipy.signal.kaiser = kaiser

from ukrainian_tts.tts import TTS, Voices, Stress

_SENTENCE_RE = re.compile(r'[^.!?;\n]+[.!?;\n]*')
CONFIG_PATH = os.path.expanduser("~/.gemini/config/plugins/ukrainian-voice/voice_config.json")
FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"
DEFAULT_SPEED = 1.3

def get_models_dir() -> str:
    env_dir = os.environ.get("UKR_TTS_CACHE")
    if env_dir and os.path.exists(os.path.join(env_dir, "model.pth")):
        return env_dir
    repo_models = r"D:\___ new dev\antigravity-ukrainian-voice\models"
    if os.path.exists(os.path.join(repo_models, "model.pth")):
        return repo_models
    plugin_models = os.path.expanduser("~/.gemini/config/plugins/ukrainian-voice/models")
    if os.path.exists(os.path.join(plugin_models, "model.pth")):
        return plugin_models
    os.makedirs(plugin_models, exist_ok=True)
    return plugin_models

_TTS_INSTANCE = None

def get_tts():
    global _TTS_INSTANCE
    if _TTS_INSTANCE is None:
        models_dir = get_models_dir()
        old_cwd = os.getcwd()
        try:
            os.chdir(models_dir)
            _TTS_INSTANCE = TTS(cache_folder=models_dir)
        finally:
            os.chdir(old_cwd)
    return _TTS_INSTANCE

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"voice": "dmytro", "speed": DEFAULT_SPEED}

def save_config(config: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

def get_configured_voice() -> str:
    cfg = load_config()
    return cfg.get("voice", os.environ.get("UKR_VOICE", "dmytro"))

def get_configured_speed() -> float:
    cfg = load_config()
    return float(cfg.get("speed", DEFAULT_SPEED))

def set_configured_voice(voice_name: str):
    cfg = load_config()
    cfg["voice"] = voice_name.lower()
    save_config(cfg)
    print(f"Голос за замовчуванням змінено на: {voice_name}")

def set_configured_speed(speed: float):
    cfg = load_config()
    cfg["speed"] = speed
    save_config(cfg)
    print(f"Швидкість мови змінено на: {speed}x")

def apply_speed(wav_bytes: bytes, speed: float) -> bytes:
    """Applies pitch-preserved time-stretching using ffmpeg atempo filter."""
    if abs(speed - 1.0) < 0.05 or not os.path.exists(FFMPEG_PATH):
        return wav_bytes
    try:
        proc = subprocess.run(
            [FFMPEG_PATH, "-f", "wav", "-i", "pipe:0", "-filter:a", f"atempo={speed}", "-f", "wav", "pipe:1"],
            input=wav_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True
        )
        out = bytearray(proc.stdout)
        if len(out) > 44:
            struct.pack_into('<I', out, 4, len(out) - 8)
            data_idx = out.find(b'data')
            if data_idx != -1:
                struct.pack_into('<I', out, data_idx + 4, len(out) - (data_idx + 8))
        return bytes(out)
    except Exception:
        return wav_bytes

def split_sentences(text: str, max_len: int = 180):
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return []
    chunks = []
    for match in _SENTENCE_RE.finditer(text):
        piece = match.group().strip()
        if not piece:
            continue
        while len(piece) > max_len:
            cut = piece.rfind(',', 0, max_len)
            if cut == -1:
                cut = piece.rfind(' ', 0, max_len)
            if cut == -1:
                cut = max_len
            chunks.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        if piece:
            chunks.append(piece)
    return chunks

def clean_text_for_speech(text: str) -> str:
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'^[#>\-\*\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[*_~]', '', text)
    text = re.sub(r'[^\w\s\.,!\?\'"\-:;()«»—–]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_voice(voice_name: str = None):
    if not voice_name:
        voice_name = get_configured_voice()
    voice_map = {
        "dmytro": Voices.Dmytro.value,
        "tetiana": Voices.Tetiana.value,
        "lada": Voices.Lada.value,
        "mykyta": Voices.Mykyta.value,
        "oleksa": Voices.Oleksa.value,
    }
    return voice_map.get(voice_name.lower(), Voices.Dmytro.value)

def stream_speak(text: str, voice_name: str = None, speed: float = None):
    text = clean_text_for_speech(text)
    sentences = split_sentences(text)
    if not sentences:
        return

    if speed is None:
        speed = get_configured_speed()
    voice = get_voice(voice_name)
    tts = get_tts()
    audio_queue = queue.Queue(maxsize=10)

    def synthesizer():
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue
            try:
                buf = io.BytesIO()
                tts.tts(sentence, voice, Stress.Dictionary.value, buf)
                raw_wav = buf.getvalue()
                fast_wav = apply_speed(raw_wav, speed)
                audio_queue.put(fast_wav)
            except Exception as e:
                print(f"Помилка синтезу речення {i}: {e}", file=sys.stderr)
        audio_queue.put(None)

    worker = threading.Thread(target=synthesizer, daemon=True)
    worker.start()

    while True:
        wav_bytes = audio_queue.get()
        if wav_bytes is None:
            break
        winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
        audio_queue.task_done()

    worker.join()

def generate_widget(text: str, output_html_path: str, voice_name: str = None, speed: float = None):
    text = clean_text_for_speech(text)
    if not text:
        return

    if speed is None:
        speed = get_configured_speed()
    if not voice_name:
        voice_name = get_configured_voice()

    voice = get_voice(voice_name)
    tts = get_tts()
    buf = io.BytesIO()
    tts.tts(text, voice, Stress.Dictionary.value, buf)
    b64_audio = base64.b64encode(buf.getvalue()).decode("utf-8")

    voice_titles = {
        "dmytro": "Дмитро",
        "tetiana": "Тетяна",
        "lada": "Лада",
        "mykyta": "Микита",
        "oleksa": "Олекса",
    }
    voice_title = voice_titles.get(voice_name.lower(), "Дмитро")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    body {{ margin: 0; padding: 0; background: transparent; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    .waveform-bar {{
      display: inline-block;
      width: 3px;
      border-radius: 2px;
      background: #0057B7;
      animation: wave 1s ease-in-out infinite;
    }}
    .waveform-bar:nth-child(1) {{ height: 8px; animation-delay: 0.0s; }}
    .waveform-bar:nth-child(2) {{ height: 16px; animation-delay: 0.2s; }}
    .waveform-bar:nth-child(3) {{ height: 12px; animation-delay: 0.4s; }}
    .waveform-bar:nth-child(4) {{ height: 18px; animation-delay: 0.1s; }}
    .waveform-bar:nth-child(5) {{ height: 10px; animation-delay: 0.3s; }}
    @keyframes wave {{
      0%, 100% {{ transform: scaleY(0.4); opacity: 0.5; }}
      50% {{ transform: scaleY(1.2); opacity: 1; }}
    }}
    .paused .waveform-bar {{
      animation: none !important;
      transform: scaleY(0.4) !important;
      opacity: 0.3 !important;
    }}
    .progress-track {{
      background: rgba(255, 255, 255, 0.12);
      border-radius: 9999px;
      cursor: pointer;
      position: relative;
      height: 6px;
      transition: height 0.15s ease;
    }}
    .progress-track:hover {{
      height: 8px;
    }}
    .progress-fill {{
      background: linear-gradient(90deg, #0057B7 0%, #0080FF 70%, #FFD700 100%);
      border-radius: 9999px;
      height: 100%;
      width: 0%;
      position: relative;
      transition: width 0.08s linear;
    }}
  </style>
</head>
<body class="bg-transparent antialiased py-1">
  <div class="inline-flex items-center gap-3 px-3 py-2 rounded-2xl bg-[#181825]/90 border border-[#313244] shadow-lg backdrop-blur-md max-w-lg select-none">
    <!-- Play/Pause Button -->
    <button id="playBtn" onclick="togglePlay()" class="w-9 h-9 shrink-0 rounded-full bg-gradient-to-tr from-[#0057B7] to-[#0070ea] hover:scale-105 active:scale-95 text-white flex items-center justify-center shadow-md transition-all cursor-pointer">
      <svg id="playIcon" class="w-4 h-4 translate-x-0.5 fill-current" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
      <svg id="pauseIcon" class="w-4 h-4 fill-current hidden" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
    </button>

    <!-- Waveform Visualizer -->
    <div id="visualizer" class="flex items-center gap-0.5 h-5 shrink-0 paused">
      <span class="waveform-bar"></span>
      <span class="waveform-bar"></span>
      <span class="waveform-bar"></span>
      <span class="waveform-bar"></span>
      <span class="waveform-bar"></span>
    </div>

    <!-- Center: Timeline & Time -->
    <div class="flex flex-col gap-1 w-44 sm:w-56 shrink-0">
      <div class="flex items-center justify-between text-[10px] text-[#a6adc8] font-mono leading-none">
        <span id="currentTime">0:00</span>
        <span class="text-[#6c7086]">/</span>
        <span id="totalDuration">0:00</span>
      </div>
      <div id="progressTrack" class="progress-track w-full" onclick="seekAudio(event)">
        <div id="progressFill" class="progress-fill"></div>
      </div>
    </div>

    <!-- Right: Badges -->
    <div class="flex items-center gap-1.5 shrink-0 ml-1">
      <!-- Voice badge -->
      <span class="inline-flex items-center gap-1 text-[11px] font-medium text-[#cdd6f4] px-2 py-0.5 rounded-lg bg-[#313244]/60 border border-[#45475a]/40">
        <span>🎙️</span>
        <span id="voiceName">{voice_title}</span>
      </span>

      <!-- Speed toggle badge -->
      <button onclick="cycleSpeed()" title="Клікніть щоб змінити швидкість" class="text-[11px] font-semibold text-[#f9e2af] px-2 py-0.5 rounded-lg bg-[#fab387]/10 hover:bg-[#fab387]/20 border border-[#fab387]/30 transition-all cursor-pointer active:scale-95">
        <span id="speedLabel">{speed}x</span>
      </button>
    </div>
  </div>

  <script>
    const audio = new Audio("data:audio/wav;base64,{b64_audio}");
    let currentSpeed = {speed};
    audio.playbackRate = currentSpeed;
    let isPlaying = false;

    const playIcon = document.getElementById('playIcon');
    const pauseIcon = document.getElementById('pauseIcon');
    const visualizer = document.getElementById('visualizer');
    const progressFill = document.getElementById('progressFill');
    const currentTimeEl = document.getElementById('currentTime');
    const totalDurationEl = document.getElementById('totalDuration');
    const speedLabel = document.getElementById('speedLabel');

    function formatTime(secs) {{
      if (isNaN(secs) || secs < 0) return "0:00";
      const m = Math.floor(secs / 60);
      const s = Math.floor(secs % 60);
      return m + ":" + (s < 10 ? "0" : "") + s;
    }}

    audio.onloadedmetadata = () => {{
      totalDurationEl.textContent = formatTime(audio.duration / currentSpeed);
    }};

    audio.ontimeupdate = () => {{
      if (!audio.duration) return;
      const progress = (audio.currentTime / audio.duration) * 100;
      progressFill.style.width = progress + '%';
      currentTimeEl.textContent = formatTime(audio.currentTime / currentSpeed);
      if (totalDurationEl.textContent === "0:00") {{
        totalDurationEl.textContent = formatTime(audio.duration / currentSpeed);
      }}
    }};

    audio.onended = () => {{
      resetUI();
    }};

    function togglePlay() {{
      if (!isPlaying) {{
        audio.playbackRate = currentSpeed;
        audio.play().then(() => {{
          isPlaying = true;
          playIcon.classList.add('hidden');
          pauseIcon.classList.remove('hidden');
          visualizer.classList.remove('paused');
        }}).catch(err => console.error(err));
      }} else {{
        audio.pause();
        isPlaying = false;
        playIcon.classList.remove('hidden');
        pauseIcon.classList.add('hidden');
        visualizer.classList.add('paused');
      }}
    }}

    function resetUI() {{
      isPlaying = false;
      playIcon.classList.remove('hidden');
      pauseIcon.classList.add('hidden');
      visualizer.classList.add('paused');
      progressFill.style.width = '0%';
      currentTimeEl.textContent = "0:00";
    }}

    function seekAudio(e) {{
      const track = document.getElementById('progressTrack');
      const rect = track.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const pct = Math.max(0, Math.min(1, clickX / rect.width));
      if (audio.duration) {{
        audio.currentTime = pct * audio.duration;
        progressFill.style.width = (pct * 100) + '%';
      }}
    }}

    const speeds = [1.0, 1.3, 1.5, 1.8];
    function cycleSpeed() {{
      const idx = speeds.indexOf(currentSpeed);
      currentSpeed = speeds[(idx + 1) % speeds.length];
      audio.playbackRate = currentSpeed;
      speedLabel.textContent = currentSpeed + 'x';
      if (audio.duration) {{
        totalDurationEl.textContent = formatTime(audio.duration / currentSpeed);
        currentTimeEl.textContent = formatTime(audio.currentTime / currentSpeed);
      }}
    }}
  </script>
</body>
</html>
"""
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

if __name__ == "__main__":
    args = sys.argv[1:]
    
    if "--set-voice" in args:
        v_idx = args.index("--set-voice")
        set_configured_voice(args[v_idx + 1])
        sys.exit(0)

    if "--set-speed" in args:
        s_idx = args.index("--set-speed")
        set_configured_speed(float(args[s_idx + 1]))
        sys.exit(0)

    voice_arg = None
    if "--voice" in args:
        v_idx = args.index("--voice")
        voice_arg = args[v_idx + 1]
        args = args[:v_idx] + args[v_idx + 2:]

    speed_arg = None
    if "--speed" in args:
        s_idx = args.index("--speed")
        speed_arg = float(args[s_idx + 1])
        args = args[:s_idx] + args[s_idx + 2:]

    if "--widget" in args:
        w_idx = args.index("--widget")
        out_html = args[w_idx + 1]
        args = args[:w_idx] + args[w_idx + 2:]
        
        if "--file" in args:
            f_idx = args.index("--file")
            with open(args[f_idx + 1], "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = " ".join(args)
        
        generate_widget(content, out_html, voice_arg, speed_arg)
    else:
        if len(args) > 0 and args[0] == "--file" and len(args) > 1:
            with open(args[1], "r", encoding="utf-8") as f:
                content = f.read()
        elif len(args) > 0:
            content = " ".join(args)
        else:
            content = sys.stdin.read()
        
        stream_speak(content, voice_arg, speed_arg)
