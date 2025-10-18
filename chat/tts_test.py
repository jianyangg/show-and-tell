"""
Example usage of the ElevenLabs TTS module.

This demonstrates various ways to use the refactored tts.py module.
"""

import asyncio
from tts import ElevenLabsTTS, AudioPlayer, VoiceSettings


# Example 1: Basic usage with direct playback
async def example_basic_playback():
    """Simple example: convert text to speech and play it"""
    tts = ElevenLabsTTS()  # Reads API key from ELEVENLABS_API_KEY env var
    voice_id = "77R1BwNT6WJF5Bjget1w"

    # AudioPlayer context manager handles PyAudio initialization and cleanup
    with AudioPlayer() as player:
        await tts.stream_text_to_speech(
            voice_id=voice_id,
            text="Hello from the refactored module!",
            audio_callback=player.write
        )


# Example 2: Custom voice settings
async def example_custom_voice():
    """Example with custom voice stability and similarity settings"""
    tts = ElevenLabsTTS()
    voice_id = "77R1BwNT6WJF5Bjget1w"

    # Configure voice generation parameters
    # Higher stability = more consistent output
    # Higher similarity_boost = closer to original voice training
    custom_settings = VoiceSettings(
        stability=0.7,
        similarity_boost=0.9
    )

    with AudioPlayer() as player:
        await tts.stream_text_to_speech(
            voice_id=voice_id,
            text="This uses custom voice settings for a different sound.",
            voice_settings=custom_settings,
            audio_callback=player.write
        )


# Example 3: Save audio to file instead of playing
async def example_save_to_file():
    """Example showing how to save audio to a file instead of playing"""
    tts = ElevenLabsTTS()
    voice_id = "77R1BwNT6WJF5Bjget1w"

    # Collect audio chunks in a list
    audio_chunks = []

    def save_chunk(audio_data: bytes):
        """Callback that saves audio data instead of playing it"""
        audio_chunks.append(audio_data)

    await tts.stream_text_to_speech(
        voice_id=voice_id,
        text="This audio will be saved to a file.",
        audio_callback=save_chunk
    )

    # Write all chunks to a PCM file
    # This is raw 24kHz 16-bit mono PCM audio
    with open("output.pcm", "wb") as f:
        for chunk in audio_chunks:
            f.write(chunk)

    print(f"Saved {len(audio_chunks)} audio chunks to output.pcm")


# Example 4: Use in another async function (e.g., in a web server)
async def example_in_async_context():
    """Example showing usage within an async application context"""
    tts = ElevenLabsTTS()

    # In a real application, you might create the TTS instance once
    # and reuse it for multiple requests
    async def speak(text: str):
        """Helper function that can be called from anywhere in your app"""
        with AudioPlayer() as player:
            await tts.stream_text_to_speech(
                voice_id="77R1BwNT6WJF5Bjget1w",
                text=text,
                audio_callback=player.write
            )

    # Now you can call this from anywhere
    await speak("First message")
    await speak("Second message")


# Example 5: Process audio data in real-time
async def example_realtime_processing():
    """Example showing real-time audio processing"""
    tts = ElevenLabsTTS()
    voice_id = "77R1BwNT6WJF5Bjget1w"

    total_bytes = 0

    def process_audio(audio_data: bytes):
        """Custom callback for real-time processing"""
        nonlocal total_bytes
        total_bytes += len(audio_data)
        # You could: send over network, apply effects, analyze, etc.
        print(f"Received chunk: {len(audio_data)} bytes (total: {total_bytes})")

    await tts.stream_text_to_speech(
        voice_id=voice_id,
        text="This demonstrates real-time audio processing as chunks arrive.",
        audio_callback=process_audio
    )


if __name__ == "__main__":
    # Run one of the examples
    print("Running basic playback example...")
    asyncio.run(example_basic_playback())

    # Uncomment to run other examples:
    # asyncio.run(example_custom_voice())
    # asyncio.run(example_save_to_file())
    # asyncio.run(example_in_async_context())
    # asyncio.run(example_realtime_processing())
