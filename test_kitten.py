from kittenml import KittenTTS

print("Loading KittenTTS 2...")

tts = KittenTTS(
    "KittenML/kitten-tts-2",
    backend="mlx"
)

print("Generating speech...")

tts.generate_to_file(
    "Hello! This is my first locally generated speech.",
    "hello.wav",
    voice="Bruno"
)

print("Done! Audio saved as hello.wav")