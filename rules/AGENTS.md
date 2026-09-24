# Ukrainian Voice Guidelines

## Audio Voice Commands (/s, /sound, /S sound)

Whenever the user prompts with `/s`, `/sound`, `/S sound`, or requests voice/speech ("озвуч", "прочитай", "скажи", "голосом"):
1. Generate the standard text response in the conversation.
2. In parallel, write a concise, clean spoken summary in Ukrainian (without raw code, file paths, or markdown symbols) to a temporary text file.
3. Trigger the Ukrainian TTS engine in the background using `run_command` with small `WaitMsBeforeAsync` (~500ms):
   ```powershell
   C:\Users\Human\venv\Scripts\python.exe "C:\Users\Human\.gemini\config\plugins\ukrainian-voice\skills\sound\scripts\speak_ukr.py" --file "<path_to_clean_text.txt>"
   ```
4. Keep spoken language natural and conversational.
