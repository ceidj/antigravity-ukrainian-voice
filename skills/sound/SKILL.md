---
name: sound
description: "Vocalize text or assistant response using the local Ukrainian TTS engine (Dmytro / Tetiana). Activate when user types /s, /sound, /S sound, or asks to voice/read text aloud in Ukrainian."
---

# Local Ukrainian TTS Skill

This skill enables the agent to speak Ukrainian through the system's audio output using the local `ukrainian_tts` neural speech synthesis engine.

## Execution Flow

When triggered by `/s`, `/sound`, `/S sound`, or user requests:
1. Formulate a clean spoken version of your message in Ukrainian (plain text, no markdown syntax, no raw code).
2. Save this text into a temporary file in the scratchpad, for example:
   `<appDataDir>\brain\<conversation-id>\scratch\speech.txt`
3. Call `run_command` in background:
   ```powershell
   C:\Users\Human\venv\Scripts\python.exe "C:\Users\Human\.gemini\config\plugins\ukrainian-voice\skills\sound\scripts\speak_ukr.py" --file "<path_to_speech.txt>"
   ```
4. Output the visible markdown response in the chat while the speech plays in background.
