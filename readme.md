# to build the installer
.venv/bin/pyinstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "Kitten Voice" \
  --icon image/KittenVoiceIcons/KittenVoice.icns \
  --add-data "image/KittenVoiceIcons/KittenVoice-Dock.png:image/KittenVoiceIcons" \
  --add-data "image/KittenVoiceIcons/KittenVoice-MenuBar.png:image/KittenVoiceIcons" \
  --copy-metadata requests \
  --collect-all kittenml \
  --collect-all mlx \
  --collect-all mlx_lm \
  --collect-all PySide6 \
  voice_app.py

# open the app
open "dist/Kitten Voice.app"