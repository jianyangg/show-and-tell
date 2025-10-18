"""
ElevenLabs Text-to-Speech WebSocket Streaming Module

This module provides a reusable interface for streaming text-to-speech audio
from the ElevenLabs API using WebSocket connections. It supports both direct
audio playback and custom audio handling via callbacks.

Key Features:
- Async WebSocket streaming for low-latency audio generation
- Configurable voice settings (stability, similarity_boost)
- Callback-based audio handling for flexibility
- Proper SSL certificate verification on macOS
- Context manager support for resource cleanup
"""

import pyaudio
import websockets
import json
import base64
import os
import ssl
import certifi
import asyncio
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class VoiceSettings:
    """Configuration for ElevenLabs voice generation parameters"""
    stability: float = 0.5  # Higher = more consistent, Lower = more variable
    similarity_boost: float = 0.8  # Higher = closer to original voice


class ElevenLabsTTS:
    """
    Manages text-to-speech streaming from ElevenLabs API.

    This class handles WebSocket connections, SSL configuration, and audio streaming.
    Audio data can be processed via callback or played directly using PyAudio.

    Example usage:
        tts = ElevenLabsTTS(api_key="your_api_key")
        await tts.stream_text_to_speech(
            voice_id="voice_id_here",
            text="Hello world",
            audio_callback=lambda data: print(f"Received {len(data)} bytes")
        )
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the TTS client.

        Args:
            api_key: ElevenLabs API key. If None, reads from ELEVENLABS_API_KEY env var
        """
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("API key must be provided or set in ELEVENLABS_API_KEY environment variable")

        # Create SSL context once to avoid repeated initialization
        # Uses certifi's CA bundle to ensure proper certificate verification on macOS
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())

    async def stream_text_to_speech(
        self,
        voice_id: str,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_callback: Optional[Callable[[bytes], None]] = None,
        output_format: str = "mp3_44100_128"
    ) -> None:
        """
        Stream text-to-speech audio from ElevenLabs API.

        This async function establishes a WebSocket connection, sends the text,
        and processes incoming audio chunks via the provided callback.

        Args:
            voice_id: ElevenLabs voice ID (e.g., "77R1BwNT6WJF5Bjget1w")
            text: Text to convert to speech
            voice_settings: Optional voice configuration (uses defaults if None)
            audio_callback: Function to call with each audio chunk (bytes).
                          If None, audio data is silently discarded.
            output_format: Audio format (default: "mp3_44100_128" for 44.1kHz MP3 at 128kbps)

        Raises:
            websockets.exceptions.WebSocketException: If connection fails
            json.JSONDecodeError: If API returns invalid JSON
            RuntimeError: If audio streaming fails after max retries
        """
        max_retries = 2
        retry_count = 0
        base_delay = 1.0  # Start with 1 second delay

        while retry_count <= max_retries:
            try:
                await self._stream_text_to_speech_internal(
                    voice_id, text, voice_settings, audio_callback, output_format
                )
                # Success - exit retry loop
                return

            except Exception as e:
                retry_count += 1
                if retry_count > max_retries:
                    raise RuntimeError(
                        f"TTS failed after {max_retries} retries: {e}"
                    ) from e

                # Exponential backoff: wait longer between each retry
                delay = base_delay * (2 ** (retry_count - 1))
                print(f"TTS attempt {retry_count} failed: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)

    async def _stream_text_to_speech_internal(
        self,
        voice_id: str,
        text: str,
        voice_settings: Optional[VoiceSettings],
        audio_callback: Optional[Callable[[bytes], None]],
        output_format: str
    ) -> None:
        """
        Internal implementation of TTS streaming (called by retry wrapper).

        This method handles the actual WebSocket communication with ElevenLabs.
        Separated from the public method to enable clean retry logic.
        """
        settings = voice_settings or VoiceSettings()
        uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?output_format={output_format}"

        async with websockets.connect(
            uri,
            additional_headers={"xi-api-key": self.api_key},
            ssl=self.ssl_context
        ) as websocket:
            # Initialize connection with voice settings
            # The API requires an initial message with voice configuration
            await websocket.send(
                json.dumps({
                    "text": " ",  # Empty initial text
                    "voice_settings": {
                        "stability": settings.stability,
                        "similarity_boost": settings.similarity_boost
                    }
                })
            )

            # Send the actual text to convert
            await websocket.send(json.dumps({"text": text}))

            # Signal end of text stream
            # This tells the API we're done sending text
            await websocket.send(json.dumps({"text": ""}))

            # Process incoming audio chunks
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)

                    # Audio data is base64-encoded in the response
                    if data.get("audio"):
                        audio_data = base64.b64decode(data["audio"])
                        if audio_callback:
                            audio_callback(audio_data)

                    # Check if this is the final chunk
                    if data.get("isFinal"):
                        break

                except Exception as e:
                    # Re-raise with context for better debugging
                    raise RuntimeError(f"Error during audio streaming: {e}") from e

    async def stream_text_to_speech_yield(
        self,
        voice_id: str,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        output_format: str = "mp3_44100_128"
    ):
        """
        Stream text-to-speech audio from ElevenLabs API, yielding chunks.

        This is a generator function that yields MP3 audio chunks as they arrive
        from the ElevenLabs API. Useful for server-side streaming to clients.

        Args:
            voice_id: ElevenLabs voice ID (e.g., "77R1BwNT6WJF5Bjget1w")
            text: Text to convert to speech
            voice_settings: Optional voice configuration (uses defaults if None)
            output_format: Audio format (default: "mp3_44100_128" for 44.1kHz MP3 at 128kbps)

        Yields:
            bytes: MP3 audio chunks as they arrive from the API

        Raises:
            RuntimeError: If audio streaming fails after max retries
        """
        max_retries = 2
        retry_count = 0
        base_delay = 1.0

        while retry_count <= max_retries:
            try:
                # Yield audio chunks from the internal streaming implementation
                async for chunk in self._stream_text_to_speech_yield_internal(
                    voice_id, text, voice_settings, output_format
                ):
                    yield chunk
                # Success - exit retry loop
                return

            except Exception as e:
                retry_count += 1
                if retry_count > max_retries:
                    raise RuntimeError(
                        f"TTS streaming failed after {max_retries} retries: {e}"
                    ) from e

                delay = base_delay * (2 ** (retry_count - 1))
                print(f"TTS stream attempt {retry_count} failed: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)

    async def _stream_text_to_speech_yield_internal(
        self,
        voice_id: str,
        text: str,
        voice_settings: Optional[VoiceSettings],
        output_format: str
    ):
        """
        Internal generator for TTS streaming (called by retry wrapper).

        Yields MP3 audio chunks as they arrive from ElevenLabs WebSocket.
        """
        settings = voice_settings or VoiceSettings()
        uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?output_format={output_format}"

        async with websockets.connect(
            uri,
            additional_headers={"xi-api-key": self.api_key},
            ssl=self.ssl_context
        ) as websocket:
            # Initialize connection with voice settings
            await websocket.send(
                json.dumps({
                    "text": " ",
                    "voice_settings": {
                        "stability": settings.stability,
                        "similarity_boost": settings.similarity_boost
                    }
                })
            )

            # Send the actual text to convert
            await websocket.send(json.dumps({"text": text}))

            # Signal end of text stream
            await websocket.send(json.dumps({"text": ""}))

            # Yield incoming audio chunks
            while True:
                message = await websocket.recv()
                data = json.loads(message)

                # Yield audio chunk if present
                if data.get("audio"):
                    audio_data = base64.b64decode(data["audio"])
                    yield audio_data

                # Stop when final chunk is received
                if data.get("isFinal"):
                    break


class AudioPlayer:
    """
    Context manager for PyAudio playback.

    Handles initialization and cleanup of PyAudio resources, ensuring
    proper resource management even if errors occur during playback.

    Example usage:
        with AudioPlayer() as player:
            # player.write() is now available
            await tts.stream_text_to_speech(..., audio_callback=player.write)
    """

    def __init__(self, sample_rate: int = 24000, channels: int = 1, format: int = pyaudio.paInt16):
        """
        Initialize audio player configuration.

        Args:
            sample_rate: Audio sample rate in Hz (default: 24000 for ElevenLabs PCM)
            channels: Number of audio channels (default: 1 for mono)
            format: PyAudio format constant (default: paInt16 for 16-bit)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.format = format
        self.p = None
        self.stream = None

    def __enter__(self):
        """Initialize PyAudio and open output stream"""
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=self.format,
            channels=self.channels,
            rate=self.sample_rate,
            output=True
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup PyAudio resources"""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.p:
            self.p.terminate()

    def write(self, audio_data: bytes) -> None:
        """Write audio data to the output stream"""
        if self.stream:
            self.stream.write(audio_data)


if __name__ == "__main__":
    import asyncio

    # Example usage showing how to use the module
    voice_id = "77R1BwNT6WJF5Bjget1w"
    text = "Hello! This is a test of the refactored ElevenLabs TTS module."

    # Create TTS client (uses ELEVENLABS_API_KEY from environment)
    tts = ElevenLabsTTS()

    # Use AudioPlayer context manager for automatic resource cleanup
    # This ensures PyAudio resources are properly released even if errors occur
    with AudioPlayer() as player:
        asyncio.run(
            tts.stream_text_to_speech(
                voice_id=voice_id,
                text=text,
                audio_callback=player.write  # Pass player.write as callback
            )
        )
