import sys
import os
import re
import io
import queue
import threading
import base64
import winsound
import scipy.signal
from scipy.signal.windows import kaiser
scipy.signal.kaiser = kaiser

from ukrainian_tts.tts import TTS, Voices, Stress

_SENTENCE_RE = re.compile(r'[^.!?;\n]+[.!?;\n]*')

def split_sentences(text: str, max_len: int = 180):
    """Split text into sentence chunks for streaming."""
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
    """Strip markdown, URLs, code blocks, and symbols for clean TTS reading."""
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'^[#>\-\*\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[*_~]', '', text)
    text = re.sub(r'[^\w\s\.,!\?\'"\-:;()«»—–]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_voice(voice_name: str = "dmytro"):
    voice_map = {
        "dmytro": Voices.Dmytro.value,
        "tetiana": Voices.Tetiana.value,
        "lada": Voices.Lada.value,
        "mykyta": Voices.Mykyta.value,
        "oleksa": Voices.Oleksa.value,
    }
    return voice_map.get(voice_name.lower(), Voices.Dmytro.value)

def stream_speak(text: str, voice_name: str = "dmytro"):
    """Plays audio sentence-by-sentence purely in RAM (SND_MEMORY)."""
    text = clean_text_for_speech(text)
    sentences = split_sentences(text)
    if not sentences:
        return

    voice = get_voice(voice_name)
    tts = TTS()
    audio_queue = queue.Queue(maxsize=10)

    def synthesizer():
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue
            try:
                buf = io.BytesIO()
                tts.tts(sentence, voice, Stress.Dictionary.value, buf)
                audio_queue.put(buf.getvalue())
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

def generate_widget(text: str, output_html_path: str, voice_name: str = "dmytro"):
    """
    Synthesizes text and embeds the WAV audio as Base64 directly into a
    self-contained, interactive HTML button widget (for <agent-embed> in Antigravity).
    """
    text = clean_text_for_speech(text)
    if not text:
        return

    voice = get_voice(voice_name)
    tts = TTS()
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
    </button>
  </div>

  <script>
    const audio = new Audio("data:audio/wav;base64,{b64_audio}");
    let isPlaying = false;

    audio.onended = () => {{
      resetUI();
    }};

    function togglePlay() {{
      const icon = document.getElementById('icon');
      const label = document.getElementById('label');
      if (!isPlaying) {{
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
    print(f"Widget successfully written to {output_html_path}")

if __name__ == "__main__":
    args = sys.argv[1:]
    
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
        
        generate_widget(content, out_html)
    else:
        if len(args) > 0 and args[0] == "--file" and len(args) > 1:
            with open(args[1], "r", encoding="utf-8") as f:
                content = f.read()
        elif len(args) > 0:
            content = " ".join(args)
        else:
            content = sys.stdin.read()
        
        stream_speak(content)
