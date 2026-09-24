import sys
import os
import re
import queue
import threading
import tempfile
import winsound
import scipy.signal
from scipy.signal.windows import kaiser
scipy.signal.kaiser = kaiser

from ukrainian_tts.tts import TTS, Voices, Stress

_SENTENCE_RE = re.compile(r'[^.!?;\n]+[.!?;\n]*')

def split_sentences(text: str, max_len: int = 180):
    """Split text into sentence chunks for pipeline streaming."""
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

def stream_speak(text: str, voice_name: str = "dmytro"):
    """
    Sentence-by-sentence streaming audio player (Producer-Consumer pipeline).
    Plays the first sentence immediately while synthesizing remaining sentences ahead.
    """
    text = clean_text_for_speech(text)
    sentences = split_sentences(text)
    if not sentences:
        return

    voice_map = {
        "dmytro": Voices.Dmytro.value,
        "tetiana": Voices.Tetiana.value,
        "lada": Voices.Lada.value,
        "mykyta": Voices.Mykyta.value,
        "oleksa": Voices.Oleksa.value,
    }
    voice = voice_map.get(voice_name.lower(), Voices.Dmytro.value)

    tts = TTS()
    audio_queue = queue.Queue(maxsize=10)
    temp_dir = tempfile.gettempdir()

    def synthesizer():
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue
            chunk_file = os.path.join(temp_dir, f"tts_chunk_{os.getpid()}_{i}.wav")
            try:
                with open(chunk_file, "wb") as f:
                    tts.tts(sentence, voice, Stress.Dictionary.value, f)
                audio_queue.put(chunk_file)
            except Exception as e:
                print(f"Помилка синтезу речення {i}: {e}", file=sys.stderr)
        audio_queue.put(None)

    worker = threading.Thread(target=synthesizer, daemon=True)
    worker.start()

    # Consumer thread plays chunks sequentially
    while True:
        chunk_file = audio_queue.get()
        if chunk_file is None:
            break
        winsound.PlaySound(chunk_file, winsound.SND_FILENAME)
        try:
            os.remove(chunk_file)
        except OSError:
            pass
        audio_queue.task_done()

    worker.join()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--file" and len(sys.argv) > 2:
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = " ".join(sys.argv[1:])
    else:
        content = sys.stdin.read()
    
    stream_speak(content)
