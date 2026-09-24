import sys
import os
import re
import winsound
import scipy.signal
from scipy.signal.windows import kaiser
scipy.signal.kaiser = kaiser

from ukrainian_tts.tts import TTS, Voices, Stress

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

def speak(text: str, voice_name: str = "dmytro"):
    text = clean_text_for_speech(text)
    if not text:
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
    out_wav = os.path.join(os.environ.get("TEMP", "C:/Windows/Temp"), "antigravity_voice_output.wav")
    
    with open(out_wav, "wb") as f:
        tts.tts(text, voice, Stress.Dictionary.value, f)
    
    winsound.PlaySound(out_wav, winsound.SND_FILENAME)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--file" and len(sys.argv) > 2:
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = " ".join(sys.argv[1:])
    else:
        content = sys.stdin.read()
    
    speak(content)
