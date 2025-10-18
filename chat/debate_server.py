"""
AI Debate Server - Cross-connects two Gemini text models (non-Live)

This creates a debate between two AI personas by alternately generating turns.
Each Gemini instance thinks it's talking to a human, but we route the text between them.

Setup:
    pip install google-genai websockets

Usage:
    export GEMINI_API_KEY="your-api-key"
    python debate_server.py

The debate will start automatically and stream text to any connected browser clients.
"""

import os
import asyncio
import json
import base64
import traceback
import logging
from typing import Optional
from datetime import datetime
from enum import Enum

import websockets
from google import genai
from google.genai import types

# Import TTS module for audio generation
from tts import ElevenLabsTTS

# Configure logging with timestamps and log levels
# This creates both console and file logging for comprehensive debugging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(
            f'debate_server_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Model for non-Live streaming generation
MODEL = "gemini-flash-lite-latest"

# WebSocket server configuration
WS_HOST = "localhost"
WS_PORT = 8765
obama_voice = "77R1BwNT6WJF5Bjget1w"
trump_voice = "AyNb8ExdIoh13YThHcFH"

# Initialize Gemini client
# Log API key status for debugging (without exposing the actual key)
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    logger.info(f"Gemini API key found (length: {len(api_key)})")
else:
    logger.error("GEMINI_API_KEY environment variable not set!")

client = genai.Client(
    api_key=api_key,
)

# Initialize ElevenLabs TTS client
# This client will be used to generate audio for both participants
tts_client = ElevenLabsTTS()


async def generate_debate_background(topic: str) -> Optional[bytes]:
    """
    Generate a South Park-style background image for the given debate topic.

    This function uses Google's Gemini 2.5 Flash Image model to create a thematic
    background that matches the debate topic. The generation runs asynchronously
    so it doesn't block the debate from starting.

    Architecture note:
    - Runs in background parallel to debate loop
    - Returns PNG/JPEG binary data directly (no file I/O)
    - Graceful failure: returns None if generation fails

    Args:
        topic: The debate topic to visualize (e.g., "climate change")

    Returns:
        Binary image data (PNG or JPEG) on success, None on failure

    Trade-offs:
    - Fresh generation per debate (no caching) - costs API credits but ensures uniqueness
    - Simple prompt passthrough - lets Gemini interpret the topic creatively
    - Synchronous API call wrapped in async - uses thread pool to avoid blocking
    """
    logger.info(f"🎨 Starting background image generation for topic: {topic}")

    try:
        # Define the content and configuration for Gemini API
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=topic)],
            ),
        ]

        generate_content_config = types.GenerateContentConfig(
            response_modalities=[
                "IMAGE",
            ],
            system_instruction=[
                types.Part.from_text(
                    text="""Generate a scene according to the user's prompt in South Park's cartoonish style. The user's prompt is going to be a debate topic, so identify the best prompt to achieve it. Exclude any commentary or description, just the image will do."""
                ),
            ],
        )

        # Run synchronous Gemini API call in thread pool to avoid blocking event loop
        # This is crucial for maintaining responsiveness of the debate server
        def _generate_image():
            """
            Synchronous wrapper for Gemini API call.

            Iterates through streaming chunks to find the image data.
            The API may return multiple chunks, but we only need the first one
            that contains inline image data.
            """
            for chunk in client.models.generate_content_stream(
                model="gemini-2.5-flash-image",
                contents=contents,
                config=generate_content_config,
            ):
                # Check if chunk contains valid image data
                if (
                    chunk.candidates is not None
                    and chunk.candidates[0].content is not None
                    and chunk.candidates[0].content.parts is not None
                ):
                    # Extract inline image data from the chunk
                    if (
                        chunk.candidates[0].content.parts[0].inline_data
                        and chunk.candidates[0].content.parts[0].inline_data.data
                    ):
                        inline_data = chunk.candidates[0].content.parts[0].inline_data
                        image_bytes = inline_data.data
                        mime_type = inline_data.mime_type

                        logger.info(
                            f"✅ Background image generated successfully: "
                            f"{len(image_bytes)} bytes, type: {mime_type}"
                        )
                        return image_bytes, mime_type

            # No image data found in any chunk
            logger.warning("No image data found in Gemini response chunks")
            return None, None

        # Execute in thread pool to avoid blocking asyncio event loop
        image_bytes, mime_type = await asyncio.to_thread(_generate_image)

        if image_bytes:
            logger.info(f"🎨 Background image generation complete ({len(image_bytes)} bytes)")
            return image_bytes, mime_type
        else:
            logger.warning("Background image generation returned no data")
            return None, None

    except Exception as e:
        # Log error but don't raise - graceful degradation means debate continues
        # even if background generation fails
        logger.error(f"❌ Background image generation failed: {e}", exc_info=True)
        return None, None


class DebateState(Enum):
    """
    State machine for tracking the debate flow.

    This ensures we handle turn-taking correctly and pre-buffer audio
    while the current speaker is talking.
    """
    IDLE = "idle"
    GENERATING_TEXT = "generating_text"  # LLM generating response text
    GENERATING_AUDIO = "generating_audio"  # TTS streaming audio chunks
    PLAYING_AUDIO = "playing_audio"  # Client playing audio
    WAITING_FOR_CLIENT = "waiting_for_client"  # Awaiting playback_complete


class AudioBuffer:
    """
    Thread-safe buffer for storing audio chunks in memory.

    This class manages the audio data for one speaker's turn, allowing
    concurrent generation (TTS streaming) and consumption (WebSocket sending).

    Benefits of in-memory buffering:
    - Lower latency than disk I/O
    - Automatic garbage collection (no file cleanup needed)
    - More scalable (no file system bottlenecks)
    """

    def __init__(self, speaker: str):
        self.speaker = speaker
        self.chunks: list[bytes] = []
        self.complete = False
        self.lock = asyncio.Lock()
        logger.debug(f"Created AudioBuffer for {speaker}")

    async def add_chunk(self, chunk: bytes):
        """Add an audio chunk to the buffer (called by TTS generator)."""
        async with self.lock:
            self.chunks.append(chunk)
            logger.debug(f"AudioBuffer({self.speaker}): Added chunk ({len(chunk)} bytes), total chunks: {len(self.chunks)}")

    async def mark_complete(self):
        """Mark this buffer as complete (no more chunks coming)."""
        async with self.lock:
            self.complete = True
            logger.debug(f"AudioBuffer({self.speaker}): Marked complete with {len(self.chunks)} total chunks")

    async def get_all_chunks(self) -> list[bytes]:
        """Get all buffered audio chunks (called when ready to stream to client)."""
        async with self.lock:
            return list(self.chunks)  # Return a copy to avoid concurrent modification

    async def is_complete(self) -> bool:
        """Check if audio generation is complete."""
        async with self.lock:
            return self.complete

    def get_total_size(self) -> int:
        """Get total size of buffered audio in bytes."""
        return sum(len(chunk) for chunk in self.chunks)


def _build_user_content(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part.from_text(text=text)])


class DebateParticipant:
    """
    Represents one AI participant in the debate.

    Each participant has:
    - A Gemini text generation session for creating responses
    - A persona (system prompt)
    - Audio buffer for pre-generated TTS audio
    - Speaking state tracking
    - Voice ID for ElevenLabs TTS
    """

    def __init__(self, name: str, voice_id: str, system_instruction: str):
        self.name = name
        self.voice_id = voice_id  # ElevenLabs voice ID for TTS
        self.system_instruction = system_instruction

        logger.info(f"Initializing debate participant: {name} with voice {voice_id}")

        # For broadcasting to web clients
        self.broadcast_queue = asyncio.Queue()

        # Opponent reference set by DebateServer
        self.opponent: Optional["DebateParticipant"] = None

        # Track if currently speaking (for frontend visualization)
        self.is_speaking = False
        self.last_spoke_time = 0.0

        # Conversation history from this participant's perspective
        self.history: list[types.Content] = []

        # Audio buffer for the current turn (cleared after each turn)
        self.audio_buffer: Optional[AudioBuffer] = None

        # State tracking for turn-based orchestration
        self.state = DebateState.IDLE

    def get_config(self) -> types.GenerateContentConfig:
        """Create GenerateContentConfig for text-only debate."""
        return types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

    async def generate_once(self, user_text: str) -> str:
        """Generate a single response using streaming API, returning concatenated text."""
        contents = self.history + [_build_user_content(user_text)]

        def _run() -> str:
            acc = []
            for chunk in client.models.generate_content_stream(
                model=MODEL, contents=contents, config=self.get_config()
            ):
                if getattr(chunk, "text", None):
                    acc.append(chunk.text)
            return "".join(acc)

        self.is_speaking = True
        try:
            text = await asyncio.to_thread(_run)
            self.history.append(
                types.Content(role="user", parts=[types.Part(text=user_text)])
            )
            self.history.append(
                types.Content(role="model", parts=[types.Part(text=text)])
            )
            self.last_spoke_time = asyncio.get_event_loop().time()
            return text
        finally:
            self.is_speaking = False

    async def generate_audio(self, text: str) -> AudioBuffer:
        """
        Generate audio for the given text using ElevenLabs TTS.

        This method streams audio chunks from ElevenLabs and buffers them in memory.
        The audio buffer is stored in self.audio_buffer for later streaming to the client.

        This runs concurrently with the opponent's audio playback to minimize latency.

        Args:
            text: The text to convert to speech

        Returns:
            AudioBuffer containing all MP3 audio chunks

        Raises:
            RuntimeError: If TTS fails after max retries
        """
        logger.info(f"{self.name}: Starting audio generation for text: {text[:50]}...")

        # Create fresh audio buffer for this turn
        self.audio_buffer = AudioBuffer(self.name)
        self.state = DebateState.GENERATING_AUDIO

        try:
            # Stream audio chunks from ElevenLabs and buffer them
            async for chunk in tts_client.stream_text_to_speech_yield(
                voice_id=self.voice_id,
                text=text
            ):
                await self.audio_buffer.add_chunk(chunk)
                logger.debug(f"{self.name}: Buffered audio chunk ({len(chunk)} bytes)")

            # Mark buffer as complete
            await self.audio_buffer.mark_complete()

            total_size = self.audio_buffer.get_total_size()
            logger.info(
                f"{self.name}: Audio generation complete. "
                f"Total: {total_size} bytes ({len(self.audio_buffer.chunks)} chunks)"
            )

            self.state = DebateState.WAITING_FOR_CLIENT
            return self.audio_buffer

        except Exception as e:
            logger.error(f"{self.name}: Audio generation failed: {e}", exc_info=True)
            self.state = DebateState.IDLE
            raise


class DebateServer:
    """
    Main debate server that:
    1. Manages two Gemini instances
    2. Routes text between them
    3. Broadcasts to web clients via WebSocket

    Architecture note:
    This server waits for a client to connect and specify a debate topic
    before initializing the AI participants. This allows for dynamic topics
    rather than hardcoded ones.
    """

    def __init__(self):
        logger.info("Initializing DebateServer")

        # Will be set when client sends topic
        self.debate_topic: Optional[str] = None
        self.obama: Optional[DebateParticipant] = None
        self.trump: Optional[DebateParticipant] = None

        # Track connected web clients
        self.web_clients = set()

        # Event to signal when topic is received and debate should start
        self.topic_received = asyncio.Event()

        # Track last speaking times to detect silence
        self.last_speaking_time = asyncio.get_event_loop().time()
        self.silence_threshold = 3.0  # seconds of silence before nudging

    def initialize_participants(self, debate_topic: str):
        """
        Initialize debate participants with the given topic.
        Called when client sends a topic via WebSocket.

        Trade-off: We create participants on-demand rather than at server startup.
        - Pro: Allows dynamic topics per debate session
        - Con: Slight delay when starting debate (acceptable for this use case)
        """
        logger.info(f"Initializing participants for debate topic: {debate_topic}")
        self.debate_topic = debate_topic

        # Create two participants with different personas and voices
        self.obama = DebateParticipant(
            name="Obama",
            voice_id=obama_voice,  # ElevenLabs voice ID
            system_instruction=f"""You are Barack Obama in a presidential debate with Trump, speaking directly with a voter/citizen.
Speak in Obama's characteristic thoughtful, measured, and articulate tone.
Use occasional pauses for emphasis. Reference policy details and facts.

Debate topic: {debate_topic}

You are having a back-and-forth conversation with someone who challenges your views.

CRITICAL INSTRUCTIONS:
- Keep responses EXTREMELY SHORT - 3-5 seconds maximum (ONE sentence only)
- This is rapid-fire debate - respond IMMEDIATELY when the other person finishes speaking
- DO NOT wait politely - jump in quickly with your response
- Make ONE sharp point, then STOP talking immediately
- You MUST respond to everything the other person says - silence is not an option
- Be assertive and eager to speak - this is competitive debate, not a polite conversation
- After making your point, STOP and let the other person respond

FIGHTING SPIRIT - NEVER GIVE UP:
- NEVER concede a point - always find a creative counter-argument
- If they attack your position, pivot to expose weaknesses in THEIR position
- Use analogies, historical examples, and logical rebuttals to stay on offense
- When cornered, reframe the debate to highlight what REALLY matters
- Question their assumptions and underlying logic - make them defend their premises
- Find creative angles they haven't thought of - think laterally
- Turn their own arguments against them when possible
- Stay relentless - every response should advance YOUR position while undermining THEIRS
- If losing on facts, appeal to values and principles
- If losing on values, bring in practical consequences
- ALWAYS have a comeback - there's ALWAYS another angle to fight from""",
        )

        self.trump = DebateParticipant(
            name="Trump",
            voice_id=trump_voice,  # ElevenLabs voice ID
            system_instruction=f"""You are Donald Trump in a presidential debate, speaking directly with a voter/citizen.
Speak in Trump's characteristic direct, energetic, and assertive style.
Use short, punchy sentences. Be confident and bold.

Debate topic: {debate_topic}

You are having a back-and-forth conversation with someone who opposes your views.

CRITICAL INSTRUCTIONS:
- Keep responses EXTREMELY SHORT - 3-5 seconds maximum (ONE sentence only)
- This is rapid-fire debate - respond IMMEDIATELY when the other person finishes speaking
- DO NOT wait or be polite - JUMP IN FAST and interrupt if needed
- Make ONE punchy point, then STOP talking immediately
- You MUST respond to everything the other person says - you NEVER stay quiet
- Be very aggressive and eager to speak - dominate the conversation
- After making your point, STOP so the other person responds and you can attack again
- You are in a FIGHT - act like it!

FIGHTING SPIRIT - NEVER BACK DOWN:
- NEVER admit weakness - if challenged, double down with confidence
- Attack their credibility, their logic, their track record - whatever works
- Use simple, devastating rebuttals that regular people understand
- When they make a point, immediately flip it to show how THEY'RE the problem
- Brand their arguments as "weak," "failing," "typical politician talk"
- Get creative with comparisons - "Nobody's ever seen anything like what I'm proposing"
- Personal victories and success stories - use them to discredit their theory with your practice
- If they quote experts, dismiss them and appeal to "common sense" and "real people"
- Turn every attack into proof that you're the fighter and they're the establishment
- Never defend - always counter-attack with something MORE aggressive
- Question their motives - why are they REALLY opposing this?
- ALWAYS find a way to win the point - reframe, redirect, attack, but NEVER retreat
- Every response should make THEM look worse, not just make you look better""",
        )

        # Cross-link opponents so each can signal end_of_turn to the other
        self.obama.opponent = self.trump
        self.trump.opponent = self.obama

        logger.info(f"✅ Participants initialized for topic: {debate_topic}")
        # Signal that we're ready to start the debate
        self.topic_received.set()

    # Live routing removed in non-Live configuration

    async def broadcast_to_clients(self):
        """
        Sends text and state updates to all connected web clients.

        This task will exit when all clients disconnect to prevent blocking
        the TaskGroup from completing.
        """
        logger.info("Starting broadcast to clients task")
        try:
            while True:
                # Check if clients are still connected before waiting on queues
                # This prevents blocking forever when debate has stopped
                if not self.web_clients:
                    logger.info("⏹️  No clients connected - exiting broadcast task")
                    break

                # Get messages from both participants and broadcast
                # Use wait_for with timeout to periodically check for disconnections
                tasks = [
                    asyncio.create_task(self.obama.broadcast_queue.get()),
                    asyncio.create_task(self.trump.broadcast_queue.get()),
                ]

                try:
                    # Wait for messages with a timeout to allow periodic client checks
                    done, pending = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED, timeout=1.0
                    )

                    # If timeout occurred (no messages received), cancel tasks and loop again
                    if not done:
                        for task in pending:
                            task.cancel()
                        continue

                    # Cancel pending tasks
                    for task in pending:
                        task.cancel()

                    # Get the message that completed first
                    for task in done:
                        message = task.result()

                        logger.debug(
                            f"Broadcasting message to {len(self.web_clients)} clients: {message.get('type', 'unknown')}"
                        )

                        # Handle different message types
                        if message.get('type') == 'audio_ready':
                            # Stream audio chunks to clients as binary frames
                            await self.stream_audio_to_clients(message)
                        else:
                            # Send text messages as JSON
                            message_json = json.dumps(message)
                            if self.web_clients:
                                await asyncio.gather(
                                    *[client.send(message_json) for client in self.web_clients],
                                    return_exceptions=True,
                                )
                            else:
                                logger.info("⏹️  Clients disconnected during broadcast")
                                break

                except asyncio.CancelledError:
                    # Clean up pending tasks on cancellation
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    raise

        except asyncio.CancelledError:
            logger.info("⏹️  Broadcast task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in broadcast_to_clients: {e}", exc_info=True)

    async def generate_and_send_background(self, topic: str):
        """
        Generate debate background image and send it to connected clients.

        This method runs asynchronously in the background while the debate starts,
        ensuring that image generation doesn't block the debate from beginning.
        If generation fails, the debate continues with the default gray background.

        Architecture:
        - Spawned as background task from debate_loop()
        - Runs parallel to debate conversation
        - Sends image via WebSocket when ready
        - Gracefully handles failures (no impact on debate)

        Args:
            topic: The debate topic to visualize

        Trade-offs:
        - Image may appear mid-debate (user accepts this per requirements)
        - No retry logic (single attempt keeps complexity low)
        - Base64 encoding increases message size ~33% but simplifies JSON transport
        """
        logger.info(f"🎨 Background generation task started for: {topic}")

        try:
            # Generate the image (this is the slow part - 5-15 seconds typically)
            result = await generate_debate_background(topic)

            # Check if generation succeeded
            if result is None or result[0] is None:
                logger.warning("Background generation returned no image - clients will keep gray background")
                return

            image_bytes, mime_type = result

            # Check if clients are still connected
            if not self.web_clients:
                logger.info("No clients connected - skipping background image broadcast")
                return

            # Encode image as base64 for JSON transport
            # This is simpler than sending as binary WebSocket frame with metadata
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')

            # Extract image format from MIME type (e.g., "image/png" -> "png")
            image_format = mime_type.split('/')[-1] if mime_type else 'png'

            # Send to all connected clients
            message = json.dumps({
                'type': 'background_image',
                'data': image_base64,
                'format': image_format,
                'topic': topic  # Include topic for debugging/logging
            })

            logger.info(
                f"📤 Sending background image to {len(self.web_clients)} clients "
                f"({len(image_base64)} chars base64, format: {image_format})"
            )

            await asyncio.gather(
                *[client.send(message) for client in self.web_clients],
                return_exceptions=True,
            )

            logger.info("✅ Background image sent to all clients")

        except Exception as e:
            # Log but don't raise - background generation is non-critical
            logger.error(f"❌ Error in generate_and_send_background: {e}", exc_info=True)

    async def stream_audio_to_clients(self, message: dict):
        """
        Stream audio chunks to all connected clients via binary WebSocket frames.

        This method:
        1. Retrieves the audio buffer for the specified speaker
        2. Sends a JSON message indicating audio is incoming
        3. Streams each audio chunk as a binary WebSocket frame
        4. Sends a JSON message indicating audio streaming is complete

        Args:
            message: Dictionary with 'speaker' key indicating which participant's audio to stream
        """
        speaker_name = message.get('speaker')
        if not speaker_name:
            logger.error("stream_audio_to_clients called without speaker name")
            return

        # Get the participant
        participant = self.obama if speaker_name == "Obama" else self.trump

        if not participant.audio_buffer or not await participant.audio_buffer.is_complete():
            logger.error(f"Audio buffer not ready for {speaker_name}")
            return

        logger.info(f"Streaming {speaker_name}'s audio to {len(self.web_clients)} clients...")

        try:
            # Send metadata message indicating audio is incoming
            metadata = json.dumps({
                "type": "audio_start",
                "speaker": speaker_name
            })

            if self.web_clients:
                await asyncio.gather(
                    *[client.send(metadata) for client in self.web_clients],
                    return_exceptions=True,
                )

            # Stream audio chunks as binary frames
            chunks = await participant.audio_buffer.get_all_chunks()
            total_bytes = 0

            for i, chunk in enumerate(chunks):
                if not self.web_clients:
                    logger.info("Clients disconnected during audio streaming")
                    break

                # Send binary audio chunk to all clients
                await asyncio.gather(
                    *[client.send(chunk) for client in self.web_clients],
                    return_exceptions=True,
                )
                total_bytes += len(chunk)
                logger.debug(f"Sent audio chunk {i+1}/{len(chunks)} ({len(chunk)} bytes)")

            # Send completion message
            completion = json.dumps({
                "type": "audio_complete",
                "speaker": speaker_name
            })

            if self.web_clients:
                await asyncio.gather(
                    *[client.send(completion) for client in self.web_clients],
                    return_exceptions=True,
                )

            logger.info(
                f"✅ Finished streaming {speaker_name}'s audio: "
                f"{total_bytes} bytes in {len(chunks)} chunks"
            )

            # Clean up audio buffer after streaming
            participant.audio_buffer = None

        except Exception as e:
            logger.error(f"Error streaming audio for {speaker_name}: {e}", exc_info=True)

    async def debate_loop(self):
        """
        Orchestrate turn-based debate with audio pre-buffering.

        Architecture:
        1. Generate current speaker's text + audio
        2. Stream current speaker's audio to client
        3. While client plays audio, generate next speaker's text + audio in background
        4. Wait for client to signal playback complete
        5. Repeat with roles reversed

        This minimizes gaps between speakers by pre-generating the next response.
        """
        logger.info(f"Starting audio-enabled debate on topic: {self.debate_topic}")

        try:
            # === SPAWN BACKGROUND IMAGE GENERATION TASK ===
            # This runs in parallel with the debate and doesn't block conversation
            # Image will be sent to clients when ready (may appear mid-debate)
            background_task = asyncio.create_task(
                self.generate_and_send_background(self.debate_topic)
            )
            logger.info("🎨 Background image generation task spawned")

            # === INITIAL TURN: Obama starts ===
            await asyncio.sleep(1)
            initial_prompt = (
                f'You are about to debate on the topic: \n"{self.debate_topic}".\n'
                "Make a brief opening statement. Keep it to ONE sentence."
            )

            logger.info("Generating Obama's opening statement...")
            obama_text = await self.obama.generate_once(initial_prompt)

            # Generate Obama's audio for opening
            logger.info("Generating Obama's opening audio...")
            await self.obama.generate_audio(obama_text)

            # Broadcast text to client (for transcript display)
            self.obama.broadcast_queue.put_nowait(
                {"type": "text", "speaker": self.obama.name, "text": obama_text}
            )

            # Signal that Obama's audio is ready to stream
            self.obama.broadcast_queue.put_nowait(
                {"type": "audio_ready", "speaker": self.obama.name}
            )

            # === MAIN DEBATE LOOP ===
            # We alternate: Obama speaks → Trump speaks → Obama speaks → ...
            # While one speaks (client plays audio), we generate the next one's response
            turn = 1
            current_speaker = self.obama
            next_speaker = self.trump
            current_text = obama_text

            while True:
                # Check if clients are still connected
                if not self.web_clients:
                    logger.info("⏹️  All clients disconnected - stopping debate loop")
                    break

                logger.info(f"\n{'='*60}")
                logger.info(f"Turn {turn}: {next_speaker.name} will respond to {current_speaker.name}")
                logger.info(f"{'='*60}")

                # === PARALLEL PIPELINE ===
                # 1. Client is playing current_speaker's audio
                # 2. We generate next_speaker's response + audio in background

                # Start generating next speaker's response in background
                logger.info(f"Generating {next_speaker.name}'s text response...")
                next_text_task = asyncio.create_task(
                    next_speaker.generate_once(current_text)
                )

                # Wait for next speaker's text to be ready
                next_text = await next_text_task

                # Check if client still connected
                if not self.web_clients:
                    logger.info("⏹️  All clients disconnected - stopping debate loop")
                    break

                # Generate next speaker's audio
                logger.info(f"Generating {next_speaker.name}'s audio...")
                await next_speaker.generate_audio(next_text)

                # Broadcast next speaker's text
                next_speaker.broadcast_queue.put_nowait(
                    {"type": "text", "speaker": next_speaker.name, "text": next_text}
                )

                # Signal that next speaker's audio is ready
                # The broadcast task will stream it to the client
                next_speaker.broadcast_queue.put_nowait(
                    {"type": "audio_ready", "speaker": next_speaker.name}
                )

                logger.info(
                    f"{next_speaker.name}'s response ready "
                    f"({next_speaker.audio_buffer.get_total_size()} bytes of audio)"
                )

                # === SWAP ROLES FOR NEXT ITERATION ===
                current_speaker, next_speaker = next_speaker, current_speaker
                current_text = next_text
                turn += 1

        except asyncio.CancelledError:
            logger.info("⏹️  Debate loop cancelled")
            raise
        except Exception as e:
            logger.error(f"❌ Error in debate_loop: {e}", exc_info=True)
            raise

    async def websocket_handler(self, websocket):
        """
        Handle new WebSocket connections from browser clients.

        Flow:
        1. Client connects
        2. Server sends acknowledgment
        3. Client sends debate topic
        4. Server initializes participants and starts debate
        """
        client_id = id(websocket)
        logger.info(f"New WebSocket client connected: {client_id}")
        self.web_clients.add(websocket)
        logger.info(f"Total connected clients: {len(self.web_clients)}")

        try:
            # Send initial acknowledgment
            await websocket.send(
                json.dumps(
                    {
                        "type": "connected",
                        "message": "Connected to debate server. Waiting for debate topic...",
                    }
                )
            )
            logger.debug(f"Sent connection acknowledgment to client {client_id}")

            # Wait for client to send messages (debate topic or playback signals)
            async for message in websocket:
                # Handle binary messages (not expected from client, but log if received)
                if isinstance(message, bytes):
                    logger.warning(f"Received unexpected binary message from client {client_id}")
                    continue

                logger.debug(
                    f"Received message from client {client_id}: {message[:100]}..."
                )
                try:
                    data = json.loads(message)

                    # Client sends the debate topic to start
                    if data.get("type") == "start_debate":
                        topic = data.get("topic", "")
                        logger.info(
                            f"Client {client_id} requesting debate start with topic: {topic}"
                        )

                        if topic and not self.topic_received.is_set():
                            logger.info(f"📝 Received debate topic: {topic}")

                            # Initialize participants with this topic
                            self.initialize_participants(topic)

                            # Send confirmation to client
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "init",
                                        "topic": topic,
                                        "status": "Debate starting...",
                                    }
                                )
                            )
                            logger.info(
                                f"Sent debate start confirmation to client {client_id}"
                            )

                        elif self.topic_received.is_set():
                            # Debate already started
                            logger.warning(
                                f"Client {client_id} tried to start debate, but one is already in progress"
                            )
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "error",
                                        "message": "Debate already in progress",
                                    }
                                )
                            )

                    # Client signals that audio playback completed
                    elif data.get("type") == "playback_complete":
                        speaker = data.get("speaker", "")
                        logger.info(f"Client {client_id} finished playing {speaker}'s audio")
                        # Note: Currently we don't wait for playback_complete before
                        # generating the next response. The generation happens immediately.
                        # This message is here for future use if we want to pace the debate
                        # based on client playback speed.

                except json.JSONDecodeError as e:
                    logger.error(
                        f"Invalid JSON from client {client_id}: {message[:100]}... Error: {e}"
                    )

        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"WebSocket connection closed for client {client_id}: {e}")
        except Exception as e:
            logger.error(
                f"Error in websocket_handler for client {client_id}: {e}", exc_info=True
            )
        finally:
            self.web_clients.remove(websocket)
            logger.info(
                f"Client {client_id} disconnected. Total clients: {len(self.web_clients)}"
            )

    # Silence monitoring (Live mode) removed in non-Live configuration

    async def start_debate(self):
        """Deprecated (Live mode). Use debate_loop instead."""
        await self.debate_loop()

    async def run(self):
        """
        Main entry point - sets up and runs the debate server.

        Architecture redesigned to support multiple debates:
        1. Start WebSocket server (persistent)
        2. Loop forever:
           a. Wait for client to send debate topic
           b. Initialize Gemini sessions with topic-specific system instructions
           c. Start debate tasks (broadcast + debate_loop)
           d. Wait for tasks to complete (when clients disconnect)
           e. Clean up state and wait for next debate

        This allows the server to handle multiple sequential debates without restart.
        """
        ws_server = None
        try:
            # Start WebSocket server for browser clients (persistent across multiple debates)
            # Increase max_size to 10MB to accommodate base64-encoded images (~2-3MB typical)
            # Default is 1MB which would reject our background images
            logger.info(f"Starting WebSocket server on {WS_HOST}:{WS_PORT}")
            ws_server = await websockets.serve(
                self.websocket_handler,
                WS_HOST,
                WS_PORT,
                max_size=10 * 1024 * 1024,  # 10MB max message size
            )
            logger.info(f"🌐 WebSocket server started on ws://{WS_HOST}:{WS_PORT} (max message size: 10MB)")
            logger.info("⏳ Waiting for client to connect and send debate topic...\n")

            # Main loop: handle multiple debates sequentially
            while True:
                # Wait for client to send topic (blocking until topic_received event is set)
                logger.debug("Waiting for topic_received event...")
                await self.topic_received.wait()

                logger.info(f"🎙️  Starting debate on: {self.debate_topic}\n")

                # Start background tasks (non-Live)
                # These will run until debate_loop detects client disconnect
                try:
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self.broadcast_to_clients())
                        tg.create_task(self.debate_loop())

                        logger.info("\n🎬 Debate is running! Press Ctrl+C to stop.\n")
                except* Exception as eg:
                    # Handle exception group from TaskGroup
                    # debate_loop naturally exits when clients disconnect
                    logger.info("Debate tasks completed")

                # Clean up state for next debate
                logger.info("🧹 Cleaning up debate state for next session...")
                self.topic_received.clear()  # Allow new topics
                self.debate_topic = None
                self.obama = None
                self.trump = None
                logger.info("✅ Ready for next debate topic\n")

        except asyncio.CancelledError:
            logger.info("\n⏹️  Debate stopped by user")
        except Exception as e:
            logger.error(f"❌ Error in debate server: {e}", exc_info=True)
            traceback.print_exc()
        finally:
            if ws_server:
                logger.info("Closing WebSocket server...")
                ws_server.close()
                await ws_server.wait_closed()
                logger.info("WebSocket server closed")


if __name__ == "__main__":
    print("=" * 60)
    print("AI Presidential Debate Server")
    print("=" * 60)
    print()
    logger.info("The debate topic will be provided by the web client.")
    logger.info("Start the web interface and enter a topic to begin.")
    print()

    # Create server without topic - topic will come from web client
    logger.info("Creating DebateServer instance...")
    server = DebateServer()

    logger.info("Starting server event loop...")
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
