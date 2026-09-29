import sys
import os
import re
import io
import wave
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
    raw_wav = buf.getvalue()

    # Calculate exact natural audio duration
    try:
        with wave.open(io.BytesIO(raw_wav), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            duration_secs = frames / float(rate)
    except Exception:
        duration_secs = max(1.0, len(raw_wav) / (22050 * 2))

    # Compress to MP3 (64kbps CBR) via FFmpeg for fast streaming, minimal size & native mobile playback
    mime_type = "audio/mpeg"
    b64_audio = ""
    if os.path.exists(FFMPEG_PATH):
        try:
            proc = subprocess.run(
                [FFMPEG_PATH, "-y", "-f", "wav", "-i", "pipe:0", "-c:a", "libmp3lame", "-b:a", "64k", "-f", "mp3", "pipe:1"],
                input=raw_wav,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=True
            )
            b64_audio = base64.b64encode(proc.stdout).decode("utf-8")
        except Exception as e:
            print(f"FFmpeg MP3 conversion failed, fallback to WAV: {e}", file=sys.stderr)

    if not b64_audio:
        mime_type = "audio/wav"
        b64_audio = base64.b64encode(raw_wav).decode("utf-8")

    voice_titles = {
        "dmytro": "Дмитро",
        "tetiana": "Тетяна",
        "lada": "Лада",
        "mykyta": "Микита",
        "oleksa": "Олекса",
    }
    voice_title = voice_titles.get(voice_name.lower(), "Дмитро")

    m = int(duration_secs // 60)
    s = int(duration_secs % 60)
    duration_str = f"{m}:{s:02d}"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}
    body {{
      background: transparent;
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      padding: 2px 0;
      user-select: none;
      -webkit-user-select: none;
    }}
    .player-card {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 14px;
      background: rgba(24, 24, 37, 0.95);
      border: 1px solid #313244;
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
      max-width: 480px;
      width: 100%;
      height: 44px;
    }}
    .play-btn {{
      width: 32px;
      height: 32px;
      min-width: 32px;
      border-radius: 50%;
      background: linear-gradient(135deg, #0057B7 0%, #0080FF 100%);
      border: none;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      box-shadow: 0 2px 6px rgba(0, 87, 183, 0.45);
      outline: none;
      flex-shrink: 0;
      transition: transform 0.1s ease, filter 0.15s ease;
    }}
    .play-btn:active {{
      transform: scale(0.92);
      filter: brightness(1.1);
    }}
    .play-btn svg {{
      width: 14px;
      height: 14px;
      fill: currentColor;
      display: block;
    }}
    .play-icon {{
      margin-left: 2px;
    }}
    .visualizer {{
      display: flex;
      align-items: center;
      gap: 2px;
      height: 16px;
      flex-shrink: 0;
    }}
    .waveform-bar {{
      display: block;
      width: 3px;
      border-radius: 2px;
      background: #0080FF;
      animation: wave 1s ease-in-out infinite;
    }}
    .waveform-bar:nth-child(1) {{ height: 6px; animation-delay: 0.0s; }}
    .waveform-bar:nth-child(2) {{ height: 14px; animation-delay: 0.2s; }}
    .waveform-bar:nth-child(3) {{ height: 10px; animation-delay: 0.4s; }}
    .waveform-bar:nth-child(4) {{ height: 16px; animation-delay: 0.1s; }}
    .waveform-bar:nth-child(5) {{ height: 8px; animation-delay: 0.3s; }}
    @keyframes wave {{
      0%, 100% {{ transform: scaleY(0.35); opacity: 0.5; }}
      50% {{ transform: scaleY(1.2); opacity: 1; }}
    }}
    .paused .waveform-bar {{
      animation: none !important;
      transform: scaleY(0.35) !important;
      opacity: 0.3 !important;
    }}
    .timeline-col {{
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 3px;
      flex: 1;
      min-width: 50px;
    }}
    .time-row {{
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      color: #a6adc8;
      line-height: 1;
    }}
    .track {{
      width: 100%;
      height: 5px;
      background: rgba(255, 255, 255, 0.15);
      border-radius: 999px;
      cursor: pointer;
      position: relative;
      touch-action: none;
    }}
    .fill {{
      height: 100%;
      width: 0%;
      border-radius: 999px;
      background: linear-gradient(90deg, #0057B7 0%, #0080FF 70%, #FFD700 100%);
      transition: width 0.05s linear;
      pointer-events: none;
    }}
    .badges {{
      display: flex;
      align-items: center;
      gap: 5px;
      flex-shrink: 0;
    }}
    .voice-badge {{
      display: inline-flex;
      align-items: center;
      gap: 2px;
      font-size: 11px;
      color: #cdd6f4;
      background: rgba(49, 50, 68, 0.65);
      border: 1px solid rgba(69, 71, 90, 0.45);
      border-radius: 6px;
      padding: 2px 5px;
      white-space: nowrap;
    }}
    .speed-btn {{
      font-size: 11px;
      font-weight: 600;
      color: #f9e2af;
      background: rgba(250, 179, 135, 0.12);
      border: 1px solid rgba(250, 179, 135, 0.35);
      border-radius: 6px;
      padding: 2px 6px;
      cursor: pointer;
      outline: none;
      white-space: nowrap;
      transition: all 0.15s ease;
    }}
    .speed-btn:active {{
      transform: scale(0.92);
      background: rgba(250, 179, 135, 0.25);
    }}
  </style>
</head>
<body>
  <audio id="audioPlayer" preload="auto" playsinline webkit-playsinline src="data:{mime_type};base64,{b64_audio}"></audio>
  <div class="player-card">
    <button id="playBtn" class="play-btn" aria-label="Play/Pause">
      <svg id="playIcon" class="play-icon" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
      <svg id="pauseIcon" style="display:none;" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
    </button>
    <div id="visualizer" class="visualizer paused">
      <span class="waveform-bar"></span>
      <span class="waveform-bar"></span>
      <span class="waveform-bar"></span>
      <span class="waveform-bar"></span>
      <span class="waveform-bar"></span>
    </div>
    <div class="timeline-col">
      <div class="time-row">
        <span id="currentTime">0:00</span>
        <span id="totalDuration">{duration_str}</span>
      </div>
      <div id="track" class="track">
        <div id="fill" class="fill"></div>
      </div>
    </div>
    <div class="badges">
      <span class="voice-badge">🎙️ {voice_title}</span>
      <button id="speedBtn" class="speed-btn">{speed}x</button>
    </div>
  </div>

  <script>
    const b64 = "{b64_audio}";
    const TOTAL_DURATION = {round(duration_secs, 2)};
    let currentSpeed = {speed};
    let isPlaying = false;

    const audio = document.getElementById('audioPlayer');
    const playBtn = document.getElementById('playBtn');
    const playIcon = document.getElementById('playIcon');
    const pauseIcon = document.getElementById('pauseIcon');
    const visualizer = document.getElementById('visualizer');
    const fill = document.getElementById('fill');
    const currentTimeEl = document.getElementById('currentTime');
    const totalDurationEl = document.getElementById('totalDuration');
    const speedBtn = document.getElementById('speedBtn');
    const track = document.getElementById('track');

    function formatTime(secs) {{
      if (!secs || isNaN(secs) || secs < 0) return "0:00";
      const m = Math.floor(secs / 60);
      const s = Math.floor(secs % 60);
      return m + ":" + (s < 10 ? "0" : "") + s;
    }}

    totalDurationEl.textContent = formatTime(TOTAL_DURATION);

    function updateUI(playing) {{
      isPlaying = playing;
      if (playing) {{
        playIcon.style.display = 'none';
        pauseIcon.style.display = 'block';
        visualizer.classList.remove('paused');
      }} else {{
        playIcon.style.display = 'block';
        pauseIcon.style.display = 'none';
        visualizer.classList.add('paused');
      }}
    }}

    // --- High-Performance Audio Engine (Web Audio Primary + HTML5 Fallback) ---
    let audioCtx = null;
    let audioBuffer = null;
    let webAudioSource = null;
    let webAudioStartTime = 0;
    let animId = null;
    let useWebAudio = false;
    let currentOffset = 0;

    function getAudioCtx() {{
      if (!audioCtx) {{
        const AC = window.AudioContext || window.webkitAudioContext;
        if (AC) audioCtx = new AC();
      }}
      return audioCtx;
    }}

    // Pre-decode audio data on load into memory
    try {{
      const ctx = getAudioCtx();
      if (ctx) {{
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        ctx.decodeAudioData(bytes.buffer.slice(0), (buf) => {{
          audioBuffer = buf;
          if (buf && buf.duration) {{
            totalDurationEl.textContent = formatTime(buf.duration);
          }}
        }}, () => {{}});
      }}
    }} catch(e) {{}}

    function trackWebAudio() {{
      if (!isPlaying || !useWebAudio || !audioCtx) return;
      const cur = (audioCtx.currentTime - webAudioStartTime) * currentSpeed;
      const dur = (audioBuffer && audioBuffer.duration) ? audioBuffer.duration : TOTAL_DURATION;
      if (cur >= dur) {{
        pauseAudio();
        currentOffset = 0;
        fill.style.width = '0%';
        currentTimeEl.textContent = "0:00";
        return;
      }}
      const pct = Math.min(100, Math.max(0, (cur / dur) * 100));
      fill.style.width = pct + '%';
      currentTimeEl.textContent = formatTime(cur);
      animId = requestAnimationFrame(trackWebAudio);
    }}

    function playWebAudio(offset) {{
      const ctx = getAudioCtx();
      if (!ctx || !audioBuffer) return false;
      if (ctx.state === 'suspended') ctx.resume();

      if (webAudioSource) {{
        try {{ webAudioSource.stop(); }} catch(e) {{}}
        webAudioSource = null;
      }}

      webAudioSource = ctx.createBufferSource();
      webAudioSource.buffer = audioBuffer;
      webAudioSource.playbackRate.value = currentSpeed;
      webAudioSource.connect(ctx.destination);
      webAudioStartTime = ctx.currentTime - (offset / currentSpeed);

      webAudioSource.onended = () => {{
        if (useWebAudio && isPlaying) {{
          const cur = (ctx.currentTime - webAudioStartTime) * currentSpeed;
          const dur = (audioBuffer && audioBuffer.duration) ? audioBuffer.duration : TOTAL_DURATION;
          if (cur >= dur - 0.1) {{
            pauseAudio();
            currentOffset = 0;
            fill.style.width = '0%';
            currentTimeEl.textContent = "0:00";
          }}
        }}
      }};

      webAudioSource.start(0, offset);
      useWebAudio = true;
      updateUI(true);
      if (animId) cancelAnimationFrame(animId);
      animId = requestAnimationFrame(trackWebAudio);
      return true;
    }}

    function playHtml5Audio(offset) {{
      audio.playbackRate = currentSpeed;
      if (offset !== undefined && Math.abs(audio.currentTime - offset) > 0.2) {{
        audio.currentTime = offset;
      }}
      const p = audio.play();
      if (p !== undefined) {{
        p.then(() => {{
          useWebAudio = false;
          updateUI(true);
        }}).catch((err) => {{
          console.warn("HTML5 audio blocked, trying WebAudio:", err);
          if (audioBuffer) playWebAudio(offset);
          else updateUI(false);
        }});
      }} else {{
        useWebAudio = false;
        updateUI(true);
      }}
    }}

    function playAudio(offset) {{
      const off = (offset !== undefined) ? offset : currentOffset;
      const ctx = getAudioCtx();
      if (ctx && ctx.state === 'suspended') ctx.resume();

      if (audioBuffer && ctx) {{
        playWebAudio(off);
      }} else {{
        playHtml5Audio(off);
      }}
    }}

    function pauseAudio() {{
      if (useWebAudio) {{
        if (audioCtx) {{
          currentOffset = (audioCtx.currentTime - webAudioStartTime) * currentSpeed;
        }}
        if (webAudioSource) {{
          try {{ webAudioSource.stop(); }} catch(e) {{}}
          webAudioSource = null;
        }}
        if (animId) {{
          cancelAnimationFrame(animId);
          animId = null;
        }}
      }} else {{
        audio.pause();
        currentOffset = audio.currentTime;
      }}
      updateUI(false);
    }}

    function togglePlay() {{
      if (isPlaying) {{
        pauseAudio();
      }} else {{
        playAudio(currentOffset);
      }}
    }}

    // Single click listener - rock-solid on both desktop & mobile touchscreens
    playBtn.addEventListener('click', (e) => {{
      e.stopPropagation();
      togglePlay();
    }});

    // --- HTML5 Audio Handlers (if active) ---
    audio.onloadedmetadata = () => {{
      if (!audioBuffer && audio.duration && !isNaN(audio.duration)) {{
        totalDurationEl.textContent = formatTime(audio.duration);
      }}
    }};

    audio.ontimeupdate = () => {{
      if (useWebAudio) return;
      const dur = audio.duration || TOTAL_DURATION;
      if (!dur) return;
      currentOffset = audio.currentTime;
      const pct = Math.min(100, Math.max(0, (audio.currentTime / dur) * 100));
      fill.style.width = pct + '%';
      currentTimeEl.textContent = formatTime(audio.currentTime);
    }};

    audio.onended = () => {{
      if (!useWebAudio) {{
        updateUI(false);
        currentOffset = 0;
        fill.style.width = '0%';
        currentTimeEl.textContent = "0:00";
      }}
    }};

    // --- Seeking ---
    function seekToPct(pct) {{
      const dur = (audioBuffer && audioBuffer.duration) ? audioBuffer.duration : ((audio.duration) ? audio.duration : TOTAL_DURATION);
      currentOffset = Math.max(0, Math.min(dur, pct * dur));
      fill.style.width = (pct * 100) + '%';
      currentTimeEl.textContent = formatTime(currentOffset);

      if (isPlaying) {{
        playAudio(currentOffset);
      }}
    }}

    function handleSeekEvent(e) {{
      const rect = track.getBoundingClientRect();
      const clientX = (e.touches && e.touches.length > 0) ? e.touches[0].clientX : e.clientX;
      const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      seekToPct(pct);
    }}

    track.addEventListener('click', (e) => {{
      e.stopPropagation();
      handleSeekEvent(e);
    }});
    track.addEventListener('touchstart', (e) => {{ handleSeekEvent(e); }}, {{ passive: true }});
    track.addEventListener('touchmove', (e) => {{ handleSeekEvent(e); }}, {{ passive: true }});

    // --- Speed Cycling ---
    const speeds = [1.0, 1.3, 1.5, 1.8];
    function cycleSpeed(e) {{
      if (e) e.stopPropagation();
      const idx = speeds.indexOf(currentSpeed);
      currentSpeed = speeds[(idx + 1) % speeds.length];
      speedBtn.textContent = currentSpeed + 'x';

      audio.playbackRate = currentSpeed;
      if (useWebAudio && isPlaying) {{
        playAudio(currentOffset);
      }}
    }}

    speedBtn.addEventListener('click', cycleSpeed);
  </script>
</body>
</html>
"""
    os.makedirs(os.path.dirname(output_html_path), exist_ok=True)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Automatically mirror between voice_button.html and voice_player.html
    out_dir = os.path.dirname(output_html_path)
    base_name = os.path.basename(output_html_path)
    if base_name == "voice_button.html":
        mirror_path = os.path.join(out_dir, "voice_player.html")
        try:
            with open(mirror_path, "w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception:
            pass
    elif base_name == "voice_player.html":
        mirror_path = os.path.join(out_dir, "voice_button.html")
        try:
            with open(mirror_path, "w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception:
            pass

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

    if "--help" in args or "-h" in args:
        print("Usage: speak_ukr.py [--widget <out.html>] [--file <path> | --text <text> | <text>] [--voice <dmytro|tetiana>] [--speed <float>]")
        sys.exit(0)

    if "--widget" in args:
        w_idx = args.index("--widget")
        out_html = args[w_idx + 1]
        args = args[:w_idx] + args[w_idx + 2:]
        
        if "--file" in args:
            f_idx = args.index("--file")
            with open(args[f_idx + 1], "r", encoding="utf-8") as f:
                content = f.read()
        elif "--text" in args:
            t_idx = args.index("--text")
            content = args[t_idx + 1]
        else:
            content = " ".join(args)
        
        generate_widget(content, out_html, voice_arg, speed_arg)
    else:
        if "--file" in args:
            f_idx = args.index("--file")
            with open(args[f_idx + 1], "r", encoding="utf-8") as f:
                content = f.read()
        elif "--text" in args:
            t_idx = args.index("--text")
            content = args[t_idx + 1]
        elif len(args) > 0:
            content = " ".join(args)
        else:
            if sys.stdin.isatty():
                print("No input text provided.")
                sys.exit(0)
            content = sys.stdin.read()
        
        stream_speak(content, voice_arg, speed_arg)
