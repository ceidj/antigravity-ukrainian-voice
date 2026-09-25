import sys
import os
import re
import io
import json
import queue
import threading
import subprocess
import base64
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
        return proc.stdout
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
    voice = get_voice(voice_name)
    tts = get_tts()
    buf = io.BytesIO()
    tts.tts(text, voice, Stress.Dictionary.value, buf)
    b64_audio = base64.b64encode(buf.getvalue()).decode("utf-8")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    body {{ margin: 0; padding: 0; background: transparent; overflow: hidden; }}
  </style>
</head>
<body class="bg-transparent antialiased py-1">
  <div class="inline-flex items-center gap-2">
    <button id="btn" onclick="togglePlay()" class="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-[#0057B7] hover:bg-[#004494] text-white font-medium text-xs shadow-sm transition-all cursor-pointer active:scale-95">
      <span id="icon">🔊</span>
      <span id="label">Озвучити відповідь</span>
      <span class="text-[10px] bg-white/20 px-1 py-0.5 rounded text-white/90">{speed}x</span>
    </button>
  </div>

  <script>
    const audio = new Audio("data:audio/wav;base64,{b64_audio}");
    audio.playbackRate = {speed};
    let isPlaying = false;

    audio.onended = () => {{
      resetUI();
    }};

    function togglePlay() {{
      const icon = document.getElementById('icon');
      const label = document.getElementById('label');
      if (!isPlaying) {{
        audio.playbackRate = {speed};
        audio.play();
        isPlaying = true;
        icon.textContent = '⏹️';
        label.textContent = 'Зупинити';
      }} else {{
        audio.pause();
        audio.currentTime = 0;
        resetUI();
      }}
    }}

    function resetUI() {{
      isPlaying = false;
      document.getElementById('icon').textContent = '🔊';
      document.getElementById('label').textContent = 'Озвучити відповідь';
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
