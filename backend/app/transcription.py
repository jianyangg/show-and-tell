"""
ElevenLabs Speech-to-Text integration for transcribing teach session audio.

This module provides a service for transcribing audio recordings using the ElevenLabs
Scribe v1 model. It handles:
- Sending audio to the ElevenLabs STT API using the official SDK
- Parsing word-level timestamps from the response
- Aligning transcript with recording timeline
- Grouping words into time-windowed chunks for better context
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ElevenLabs API configuration
DEFAULT_CHUNK_WINDOW = float(os.environ.get("TRANSCRIPTION_CHUNK_WINDOW", "5.0"))
ENABLE_TRANSCRIPTION = os.environ.get("ENABLE_TRANSCRIPTION", "1") == "1"
TRANSCRIPTION_LANGUAGE = os.environ.get("TRANSCRIPTION_LANGUAGE", "eng")  # Use 'eng' format for SDK


@dataclass
class TranscriptWord:
    """Represents a single transcribed word with timing information."""
    text: str
    start: float  # Start time in seconds
    end: float    # End time in seconds
    speaker_id: Optional[str] = None


@dataclass
class TranscriptChunk:
    """Represents a time-windowed chunk of transcript aligned with recording timeline."""
    start_time: float
    end_time: float
    text: str
    words: List[TranscriptWord]


@dataclass
class TranscriptionResult:
    """Complete transcription result with word-level and chunked data."""
    full_text: str
    language_code: str
    words: List[TranscriptWord]
    chunks: List[TranscriptChunk]
    raw_response: Dict[str, Any]


class TranscriptionService:
    """
    Service for transcribing audio using ElevenLabs Speech-to-Text API.

    The service converts base64-encoded WAV audio into timestamped transcripts,
    aligning the spoken words with the recording timeline for better context
    during plan synthesis.
    """

    def __init__(self, *, api_key: Optional[str] = None, chunk_window: Optional[float] = None) -> None:
        """
        Initialize the transcription service.

        Args:
            api_key: ElevenLabs API key. Defaults to ELEVENLABS_API_KEY environment variable.
            chunk_window: Time window in seconds for grouping words. Defaults to 5.0s.
        """
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        self.chunk_window = chunk_window or DEFAULT_CHUNK_WINDOW
        self.enabled = ENABLE_TRANSCRIPTION and bool(self.api_key)
        self.client = None

        if not self.enabled:
            if not self.api_key:
                logger.info("Transcription service disabled: missing ELEVENLABS_API_KEY")
            else:
                logger.info("Transcription service disabled: ENABLE_TRANSCRIPTION != 1")
        else:
            # Initialize ElevenLabs client
            try:
                from elevenlabs.client import ElevenLabs
                self.client = ElevenLabs(api_key=self.api_key)
                logger.info("ElevenLabs client initialized successfully")
            except ImportError:
                logger.error("elevenlabs package not installed. Run: pip install elevenlabs")
                self.enabled = False
            except Exception as exc:
                logger.error("Failed to initialize ElevenLabs client: %s", exc)
                self.enabled = False

    async def transcribe(
        self,
        audio_wav_base64: str,
        *,
        language: Optional[str] = None,
    ) -> Optional[TranscriptionResult]:
        """
        Transcribe base64-encoded WAV audio using ElevenLabs STT API.

        Args:
            audio_wav_base64: Base64-encoded WAV audio data
            language: Language code (e.g., 'en', 'es'). Defaults to TRANSCRIPTION_LANGUAGE env var.

        Returns:
            TranscriptionResult with word-level timestamps and time-windowed chunks,
            or None if transcription fails or is disabled.

        Example:
            ```python
            service = TranscriptionService()
            result = await service.transcribe(audio_base64)
            if result:
                print(result.full_text)
                for chunk in result.chunks:
                    print(f"[{chunk.start_time:.1f}-{chunk.end_time:.1f}s] {chunk.text}")
            ```
        """
        if not self.enabled:
            logger.debug("Transcription skipped: service disabled")
            return None

        if not audio_wav_base64 or not audio_wav_base64.strip():
            logger.warning("Transcription skipped: empty audio data")
            return None

        try:
            # Decode base64 audio to bytes
            audio_bytes = base64.b64decode(audio_wav_base64)

            # Create BytesIO object for SDK
            audio_file = BytesIO(audio_bytes)
            audio_file.name = "recording.wav"  # SDK needs a filename

            # Call ElevenLabs API using SDK
            response_data = await self._call_elevenlabs_sdk(
                audio_file,
                language=language or TRANSCRIPTION_LANGUAGE
            )

            # Parse response into structured format
            result = self._parse_response(response_data)

            logger.info(
                "Transcription successful: %d words, %d chunks, language=%s",
                len(result.words),
                len(result.chunks),
                result.language_code
            )
            logger.info("Full transcript text: %s", result.full_text)

            return result

        except Exception as exc:
            # Graceful degradation: log error but don't raise
            logger.error("Transcription failed: %s", exc, exc_info=True)
            return None

    async def _call_elevenlabs_sdk(
        self,
        audio_file: BytesIO,
        *,
        language: str,
    ) -> Dict[str, Any]:
        """
        Call ElevenLabs Speech-to-Text API using the official SDK.

        Args:
            audio_file: BytesIO object containing WAV audio bytes
            language: Target language code (e.g., 'eng', 'spa')

        Returns:
            Transcription response as dict

        Raises:
            Exception: If API request fails
        """
        if not self.client:
            raise RuntimeError("ElevenLabs client not initialized")

        # Call SDK in thread to avoid blocking async loop
        response = await asyncio.to_thread(
            self.client.speech_to_text.convert,
            file=audio_file,
            model_id="scribe_v1",  # Only model available currently
            tag_audio_events=True,  # Tag events like laughter, applause
            language_code=language,  # Language of the audio
            diarize=True,  # Annotate who is speaking
        )

        # Convert response to dict format that our parser expects
        # The SDK returns a SpeechToTextResponse object
        if hasattr(response, 'model_dump'):
            return response.model_dump()
        elif hasattr(response, 'dict'):
            return response.dict()
        else:
            # Fallback: try to convert to dict
            return dict(response)

    def _parse_response(self, response_data: Dict[str, Any]) -> TranscriptionResult:
        """
        Parse ElevenLabs API response into structured TranscriptionResult.

        The response contains:
        - full transcript text
        - language code and probability
        - word-level entries with timestamps and types (word/spacing/audio_event)

        Args:
            response_data: JSON response from ElevenLabs API

        Returns:
            Structured TranscriptionResult with words and time-windowed chunks
        """
        full_text = response_data.get("text", "")
        language_code = response_data.get("language_code", "unknown")
        raw_words = response_data.get("words", [])

        # Extract only actual words (filter out spacing and audio events)
        words: List[TranscriptWord] = []
        for item in raw_words:
            item_type = item.get("type", "word")
            if item_type == "word":
                words.append(TranscriptWord(
                    text=item.get("text", ""),
                    start=float(item.get("start", 0.0)),
                    end=float(item.get("end", 0.0)),
                    speaker_id=item.get("speaker_id"),
                ))

        # Group words into time-windowed chunks for better context
        chunks = self._create_chunks(words)

        return TranscriptionResult(
            full_text=full_text,
            language_code=language_code,
            words=words,
            chunks=chunks,
            raw_response=response_data,
        )

    def _create_chunks(self, words: List[TranscriptWord]) -> List[TranscriptChunk]:
        """
        Group words into time-windowed chunks for alignment with recording events.

        This creates semantic chunks (e.g., 5-second windows) that can be easily
        correlated with user actions in the recording timeline.

        Args:
            words: List of transcribed words with timestamps

        Returns:
            List of TranscriptChunk objects with grouped words

        Example:
            Input: ["Hello" (0.0-0.5s), "world" (0.6-1.0s), "this" (5.5-6.0s)]
            Output: [
                TranscriptChunk(0.0-5.0s, "Hello world"),
                TranscriptChunk(5.0-10.0s, "this")
            ]
        """
        if not words:
            return []

        chunks: List[TranscriptChunk] = []
        current_chunk_words: List[TranscriptWord] = []
        chunk_start = 0.0

        for word in words:
            word_start = word.start

            # Check if word belongs in current chunk window
            if word_start >= chunk_start + self.chunk_window:
                # Finalize current chunk if it has words
                if current_chunk_words:
                    chunks.append(self._finalize_chunk(chunk_start, current_chunk_words))

                # Start new chunk
                # Align chunk_start to window boundaries (0, 5, 10, 15, ...)
                chunk_start = (word_start // self.chunk_window) * self.chunk_window
                current_chunk_words = [word]
            else:
                current_chunk_words.append(word)

        # Finalize last chunk
        if current_chunk_words:
            chunks.append(self._finalize_chunk(chunk_start, current_chunk_words))

        return chunks

    def _finalize_chunk(
        self,
        start_time: float,
        words: List[TranscriptWord]
    ) -> TranscriptChunk:
        """
        Create a TranscriptChunk from a list of words.

        Args:
            start_time: Start of the time window
            words: Words in this chunk

        Returns:
            TranscriptChunk with concatenated text and timing info
        """
        if not words:
            return TranscriptChunk(
                start_time=start_time,
                end_time=start_time + self.chunk_window,
                text="",
                words=[]
            )

        # Concatenate word texts with spaces
        text = " ".join(word.text for word in words).strip()

        # Use actual word boundaries for chunk timing (more accurate than window)
        actual_start = words[0].start
        actual_end = words[-1].end

        return TranscriptChunk(
            start_time=actual_start,
            end_time=actual_end,
            text=text,
            words=words
        )

    def format_for_prompt(self, result: TranscriptionResult) -> str:
        """
        Format transcription result for inclusion in plan synthesis prompt.

        Creates a human-readable format showing time-windowed chunks
        aligned with the recording timeline.

        Args:
            result: TranscriptionResult from transcribe()

        Returns:
            Formatted string for inclusion in synthesis prompt

        Example:
            ```
            [0.0-5.0s] "Now I'm going to click the search button"
            [5.1-10.3s] "And enter the username as admin"
            [10.4-15.0s] "Then submit the form"
            ```
        """
        if not result or not result.chunks:
            return ""

        lines = []
        for chunk in result.chunks:
            if chunk.text.strip():
                time_label = f"[{chunk.start_time:.1f}-{chunk.end_time:.1f}s]"
                lines.append(f'{time_label} "{chunk.text}"')

        return "\n".join(lines)


# Module-level singleton instance
_transcription_service: Optional[TranscriptionService] = None


def get_transcription_service() -> TranscriptionService:
    """
    Get or create the singleton TranscriptionService instance.

    Returns:
        Shared TranscriptionService instance
    """
    global _transcription_service
    if _transcription_service is None:
        _transcription_service = TranscriptionService()
    return _transcription_service
