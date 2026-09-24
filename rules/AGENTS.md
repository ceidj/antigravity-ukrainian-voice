# Ukrainian Voice Guidelines

## Response Voice Badge (Always Active)

At the end of EVERY substantive assistant response, you MUST append the compact graphical voice badge with fixed height:

---
<a href="#speak"><img src="https://img.shields.io/badge/🔊_Озвучити_відповідь-/s-0057B7?style=flat-square" height="22" alt="Озвучити відповідь" /></a>  
*💡 Надішліть `/s`, щоб прослухати цей текст голосом.*

## Audio Voice Commands (/s, /sound, /S sound)

Whenever the user prompts with `/s`, `/sound`, `/S sound`, or requests voice/speech ("озвуч", "прочитай", "скажи", "голосом"):
1. If the user sent just `/s` or `/sound` without additional instructions, summarize and voice the previous response.
2. In parallel with generating text, write a concise, clean spoken summary in Ukrainian (without raw code, file paths, or markdown symbols) to a temporary text file.
3. Trigger the Ukrainian TTS engine in the background using `run_command` with small `WaitMsBeforeAsync` (~500ms):
   ```powershell
   C:\Users\Human\venv\Scripts\python.exe "C:\Users\Human\.gemini\config\plugins\ukrainian-voice\skills\sound\scripts\speak_ukr.py" --file "<path_to_clean_text.txt>"
   ```
4. Keep spoken language natural, friendly, and conversational.
