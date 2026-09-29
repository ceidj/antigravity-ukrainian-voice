# Ukrainian Voice & Player

## Audio Player (Strict Single-Embed)
- Embed ONCE at the end of every substantive FINAL response to user:
  `<agent-embed src="file:///<conversation_artifact_dir>/voice_button.html"></agent-embed>`
- Run TTS silently: `python "C:\Users\Human\speak_ukr.py" --text "<clean_summary>" --widget "<conversation_artifact_dir>\voice_button.html"`
- NEVER embed in intermediate progress ("waiting...") or daemon/cron pings.

## Voice Commands (/s, /sound, "озвуч")
- Voice response via: `python "C:\Users\Human\speak_ukr.py" --text "<clean_summary>"`

## Proactive Habit
- Conclude deliverables with backlog summary + "Що робимо далі?" with a recommended option.
