"""
AI Debate Server - Routes audio between two Gemini Live API instances

This creates a debate between two AI personas by cross-connecting their audio streams.
Each Gemini instance thinks it's talking to a human, but we route the audio between them.

Setup:
    pip install google-genai websockets pyaudio

Usage:
    export GEMINI_API_KEY="your-api-key"
    python debate_server.py

The debate will start automatically and stream to any connected browser clients.
"""

import os
import asyncio
import json
import traceback
from typing import Optional

import pyaudio
import websockets
from google import genai
from google.genai import types

# Audio configuration matching Gemini's requirements
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000  # What we send TO Gemini
RECEIVE_SAMPLE_RATE = 24000  # What we receive FROM Gemini
CHUNK_SIZE = 1024

MODEL = "models/gemini-2.0-flash-exp"

# WebSocket server configuration
WS_HOST = "localhost"
WS_PORT = 8765

# Initialize Gemini client
client = genai.Client(
    http_options={"api_version": "v1alpha"},
    api_key=os.environ.get("GEMINI_API_KEY"),
)


class DebateParticipant:
    """
    Represents one AI participant in the debate.

    Each participant has:
    - A Gemini Live API session
    - A persona (system prompt)
    - Audio input/output queues
    - Speaking state tracking
    """

    def __init__(self, name: str, voice: str, system_instruction: str):
        self.name = name
        self.voice = voice
        self.system_instruction = system_instruction

        # Audio queues for cross-connecting with the other participant
        self.audio_in_queue = asyncio.Queue()  # Receives audio from other participant
        self.audio_out_queue = asyncio.Queue()  # Sends audio to other participant

        # For broadcasting to web clients
        self.broadcast_queue = asyncio.Queue()

        # Session will be set when connecting
        self.session: Optional[genai.LiveSession] = None

        # Track if currently speaking (for frontend visualization)
        self.is_speaking = False

    def get_config(self) -> types.LiveConnectConfig:
        """Create Gemini Live API configuration for this participant."""
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=self.system_instruction,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice
                    )
                )
            ),
        )

    async def send_audio_to_gemini(self):
        """
        Background task: Reads audio from input queue and sends to Gemini.
        This is the audio FROM the other participant.
        """
        while True:
            audio_data = await self.audio_in_queue.get()

            # Send audio chunk to Gemini as if it's hearing a human speak
            await self.session.send(
                input={"data": audio_data, "mime_type": "audio/pcm"}
            )

    async def receive_audio_from_gemini(self):
        """
        Background task: Receives audio from Gemini and routes it to:
        1. The other participant's input queue (for debate continuation)
        2. The broadcast queue (for web clients to hear)
        """
        while True:
            turn = self.session.receive()
            async for response in turn:
                # Audio data from Gemini
                if data := response.data:
                    self.is_speaking = True

                    # Route to other participant
                    await self.audio_out_queue.put(data)

                    # Also send to web clients for playback
                    await self.broadcast_queue.put({
                        "type": "audio",
                        "speaker": self.name,
                        "data": data.hex()  # Convert bytes to hex string for JSON
                    })

                # Text transcript (optional, for debugging/display)
                if text := response.text:
                    print(f"[{self.name}] {text}")
                    await self.broadcast_queue.put({
                        "type": "text",
                        "speaker": self.name,
                        "text": text
                    })

            # Turn complete - no longer speaking
            self.is_speaking = False
            await self.broadcast_queue.put({
                "type": "speaking",
                "speaker": self.name,
                "is_speaking": False
            })


class DebateServer:
    """
    Main debate server that:
    1. Manages two Gemini instances
    2. Routes audio between them
    3. Broadcasts to web clients via WebSocket

    Architecture note:
    This server waits for a client to connect and specify a debate topic
    before initializing the AI participants. This allows for dynamic topics
    rather than hardcoded ones.
    """

    def __init__(self):
        # Will be set when client sends topic
        self.debate_topic: Optional[str] = None
        self.obama: Optional[DebateParticipant] = None
        self.trump: Optional[DebateParticipant] = None

        # Track connected web clients
        self.web_clients = set()

        # Event to signal when topic is received and debate should start
        self.topic_received = asyncio.Event()

    def initialize_participants(self, debate_topic: str):
        """
        Initialize debate participants with the given topic.
        Called when client sends a topic via WebSocket.

        Trade-off: We create participants on-demand rather than at server startup.
        - Pro: Allows dynamic topics per debate session
        - Con: Slight delay when starting debate (acceptable for this use case)
        """
        self.debate_topic = debate_topic

        # Create two participants with different personas and voices
        self.obama = DebateParticipant(
            name="Obama",
            voice="Puck",  # Gemini voice - calm, measured
            system_instruction=f"""You are Barack Obama participating in a presidential debate.
Speak in Obama's characteristic thoughtful, measured, and articulate tone.
Use occasional pauses for emphasis. Reference policy details and facts.

Debate topic: {debate_topic}

Keep your responses concise (15-30 seconds). This is a real-time debate,
so respond naturally to what your opponent says. Be respectful but firm.
You can disagree, fact-check, and present counterarguments."""
        )

        self.trump = DebateParticipant(
            name="Trump",
            voice="Kore",  # Gemini voice - energetic, direct
            system_instruction=f"""You are Donald Trump participating in a presidential debate.
Speak in Trump's characteristic direct, energetic, and assertive style.
Use short, punchy sentences. Be confident and bold.

Debate topic: {debate_topic}

Keep your responses concise (15-30 seconds). This is a real-time debate,
so respond naturally to what your opponent says. Be strong and defend your positions.
You can interrupt, challenge, and make your points forcefully."""
        )

        print(f"✅ Participants initialized for topic: {debate_topic}")
        # Signal that we're ready to start the debate
        self.topic_received.set()

    async def route_audio(self, from_participant: DebateParticipant,
                          to_participant: DebateParticipant):
        """
        Routes audio from one participant to another.
        This is what creates the debate - each AI hears the other's output.
        """
        while True:
            audio_data = await from_participant.audio_out_queue.get()
            await to_participant.audio_in_queue.put(audio_data)

    async def broadcast_to_clients(self):
        """
        Sends audio and state updates to all connected web clients.
        """
        while True:
            # Get messages from both participants and broadcast
            tasks = [
                asyncio.create_task(self.obama.broadcast_queue.get()),
                asyncio.create_task(self.trump.broadcast_queue.get()),
            ]

            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()

            # Get the message that completed first
            for task in done:
                message = task.result()
                message_json = json.dumps(message)

                # Broadcast to all connected clients
                if self.web_clients:
                    await asyncio.gather(
                        *[client.send(message_json) for client in self.web_clients],
                        return_exceptions=True
                    )

    async def websocket_handler(self, websocket):
        """
        Handle new WebSocket connections from browser clients.

        Flow:
        1. Client connects
        2. Server sends acknowledgment
        3. Client sends debate topic
        4. Server initializes participants and starts debate
        """
        self.web_clients.add(websocket)
        print(f"New client connected. Total clients: {len(self.web_clients)}")

        try:
            # Send initial acknowledgment
            await websocket.send(json.dumps({
                "type": "connected",
                "message": "Connected to debate server. Waiting for debate topic..."
            }))

            # Wait for client to send debate topic
            async for message in websocket:
                try:
                    data = json.loads(message)

                    # Client sends the debate topic to start
                    if data.get('type') == 'start_debate':
                        topic = data.get('topic', '')
                        if topic and not self.topic_received.is_set():
                            print(f"📝 Received debate topic: {topic}")

                            # Initialize participants with this topic
                            self.initialize_participants(topic)

                            # Send confirmation to client
                            await websocket.send(json.dumps({
                                "type": "init",
                                "topic": topic,
                                "status": "Debate starting..."
                            }))

                        elif self.topic_received.is_set():
                            # Debate already started
                            await websocket.send(json.dumps({
                                "type": "error",
                                "message": "Debate already in progress"
                            }))

                except json.JSONDecodeError:
                    print(f"⚠️  Invalid JSON from client: {message}")

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.web_clients.remove(websocket)
            print(f"Client disconnected. Total clients: {len(self.web_clients)}")

    async def start_debate(self):
        """
        Starts the debate by:
        1. Connecting both Gemini sessions
        2. Sending an initial prompt to get the conversation started
        3. Cross-routing their audio streams
        """
        print(f"Starting debate on topic: {self.debate_topic}")

        # Send initial prompt to Obama to start the debate
        await asyncio.sleep(2)  # Wait for connections to stabilize

        initial_prompt = f"""You are about to debate with your opponent on the topic:
"{self.debate_topic}".

Please make your opening statement. Keep it to 20-30 seconds."""

        await self.obama.session.send(input=initial_prompt, end_of_turn=True)
        print("Debate started! Obama is making the opening statement...")

    async def run(self):
        """
        Main entry point - sets up and runs the debate server.

        Architecture:
        1. Start WebSocket server
        2. Wait for client to send debate topic
        3. Initialize Gemini sessions with topic-specific system instructions
        4. Start audio routing and debate

        This allows dynamic topics rather than hardcoding at server startup.
        """
        try:
            # Start WebSocket server for browser clients
            ws_server = await websockets.serve(
                self.websocket_handler, WS_HOST, WS_PORT
            )
            print(f"🌐 WebSocket server started on ws://{WS_HOST}:{WS_PORT}")
            print("⏳ Waiting for client to connect and send debate topic...\n")

            # Wait for client to send topic (blocking until topic_received event is set)
            await self.topic_received.wait()

            print(f"🎙️  Starting debate on: {self.debate_topic}\n")

            # Now that we have participants, connect to Gemini
            async with (
                client.aio.live.connect(
                    model=MODEL, config=self.obama.get_config()
                ) as obama_session,
                client.aio.live.connect(
                    model=MODEL, config=self.trump.get_config()
                ) as trump_session,
                asyncio.TaskGroup() as tg,
            ):
                # Assign sessions
                self.obama.session = obama_session
                self.trump.session = trump_session

                print("✅ Connected to Gemini Live API for both participants")

                # Start all background tasks
                # Obama tasks
                tg.create_task(self.obama.send_audio_to_gemini())
                tg.create_task(self.obama.receive_audio_from_gemini())

                # Trump tasks
                tg.create_task(self.trump.send_audio_to_gemini())
                tg.create_task(self.trump.receive_audio_from_gemini())

                # Audio routing (cross-connect)
                tg.create_task(self.route_audio(self.obama, self.trump))
                tg.create_task(self.route_audio(self.trump, self.obama))

                # Web client broadcasting
                tg.create_task(self.broadcast_to_clients())

                # Start the debate
                tg.create_task(self.start_debate())

                # Keep running until interrupted
                print("\n🎬 Debate is running! Press Ctrl+C to stop.\n")
                await asyncio.Event().wait()  # Run forever

        except asyncio.CancelledError:
            print("\n⏹️  Debate stopped by user")
        except Exception as e:
            print(f"❌ Error in debate server: {e}")
            traceback.print_exc()
        finally:
            ws_server.close()
            await ws_server.wait_closed()


if __name__ == "__main__":
    print("=" * 60)
    print("AI Presidential Debate Server")
    print("=" * 60)
    print()
    print("The debate topic will be provided by the web client.")
    print("Start the web interface and enter a topic to begin.")
    print()

    # Create server without topic - topic will come from web client
    server = DebateServer()
    asyncio.run(server.run())
