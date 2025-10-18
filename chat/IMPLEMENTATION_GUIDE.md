# AI Presidential Debate - Developer Implementation Guide

## Overview

This system creates a live debate between two AI personas (Obama and Trump) using Google's Gemini Live API. The audio from both participants plays through your browser speakers while animated sprites provide visual feedback.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (Frontend)                       │
│  ┌──────────────┐              ┌──────────────┐            │
│  │    Obama     │              │    Trump     │            │
│  │   Sprite     │              │   Sprite     │            │
│  │  🔊 Audio    │              │  🔊 Audio    │            │
│  └──────────────┘              └──────────────┘            │
│         ▲                              ▲                    │
│         └──────── WebSocket ───────────┘                    │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Python Backend (debate_server.py)               │
│  ┌────────────────────────┐  ┌────────────────────────┐    │
│  │  Gemini Instance 1     │  │  Gemini Instance 2     │    │
│  │  (Obama Persona)       │  │  (Trump Persona)       │    │
│  │                        │  │                        │    │
│  │  Audio IN ◄────────────┼──┼─ Audio OUT             │    │
│  │  Audio OUT ────────────┼─►│  Audio IN              │    │
│  └────────────────────────┘  └────────────────────────┘    │
│                                                              │
│         Audio Router (cross-connects the streams)           │
└─────────────────────────────────────────────────────────────┘
```

## How It Works

1. **Backend creates two Gemini Live sessions** - one for Obama, one for Trump
2. **Audio routing**: Obama's speech output → Trump's speech input (and vice versa)
3. **Each AI thinks it's debating a human** - Gemini's built-in VAD handles turn-taking
4. **Backend broadcasts to browser** via WebSocket (audio + text transcripts)
5. **Frontend plays audio** using Web Audio API and animates sprites

---

## Part 1: Backend Setup

### Prerequisites

- Python 3.9+
- Gemini API key with Live API access
- PyAudio dependencies (PortAudio)

### Step 1.1: Install System Dependencies

**macOS:**
```bash
brew install portaudio
```

**Ubuntu/Debian:**
```bash
sudo apt-get install portaudio19-dev
```

**Windows:**
```bash
# PyAudio installer handles this
```

### Step 1.2: Create Python Environment

```bash
cd /path/to/hiyori_free_en
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### Step 1.3: Install Python Dependencies

Create `requirements.txt`:
```txt
google-genai>=0.8.0
websockets>=13.0
pyaudio>=0.2.14
```

Install:
```bash
pip install -r requirements.txt
```

### Step 1.4: Set Gemini API Key

```bash
export GEMINI_API_KEY="your-api-key-here"
```

Or add to your `.bashrc`/`.zshrc`:
```bash
echo 'export GEMINI_API_KEY="your-key"' >> ~/.zshrc
```

### Step 1.5: Understand debate_server.py

**Key Components:**

#### `DebateParticipant` Class
Represents one AI debater (Obama or Trump).

```python
class DebateParticipant:
    - name: "Obama" or "Trump"
    - voice: Gemini voice preset (Puck, Kore, etc.)
    - system_instruction: Persona prompt
    - audio_in_queue: Receives audio from opponent
    - audio_out_queue: Sends audio to opponent
    - broadcast_queue: Sends to web clients
```

#### `DebateServer` Class
Orchestrates the entire debate.

```python
class DebateServer:
    - obama: DebateParticipant instance
    - trump: DebateParticipant instance
    - web_clients: Set of connected WebSocket clients

    Methods:
    - route_audio(): Cross-connects audio streams
    - broadcast_to_clients(): Sends to browser
    - websocket_handler(): Handles browser connections
    - start_debate(): Sends initial prompt to kick off debate
```

#### Audio Flow

```
Obama Gemini → audio_out_queue → route_audio() → Trump audio_in_queue
                     ↓
              broadcast_queue → WebSocket → Browser
```

---

## Part 2: Frontend Setup

### Step 2.1: WebSocket Client

Add to `main.js` (after the existing code):

```javascript
// ========================================
// DEBATE SYSTEM - WEBSOCKET CLIENT
// ========================================

class DebateClient {
    constructor() {
        this.ws = null;
        this.audioContext = null;
        this.audioQueues = {
            'Obama': [],
            'Trump': []
        };
        this.isPlaying = {
            'Obama': false,
            'Trump': false
        };
    }

    async connect() {
        // Initialize Web Audio API
        // Must be done after user interaction (browser security requirement)
        this.audioContext = new AudioContext();

        // Connect to Python WebSocket server
        this.ws = new WebSocket('ws://localhost:8765');

        this.ws.onopen = () => {
            console.log('Connected to debate server');
        };

        this.ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            this.handleMessage(msg);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.ws.onclose = () => {
            console.log('Disconnected from debate server');
        };
    }

    handleMessage(msg) {
        switch(msg.type) {
            case 'init':
                console.log('Debate topic:', msg.topic);
                break;

            case 'audio':
                this.handleAudio(msg.speaker, msg.data);
                break;

            case 'text':
                this.handleTranscript(msg.speaker, msg.text);
                break;

            case 'speaking':
                this.handleSpeakingState(msg.speaker, msg.is_speaking);
                break;
        }
    }

    handleAudio(speaker, hexData) {
        // Convert hex string to Uint8Array
        const bytes = new Uint8Array(
            hexData.match(/.{1,2}/g).map(byte => parseInt(byte, 16))
        );

        // Queue audio for playback
        this.audioQueues[speaker].push(bytes);

        // Start playback if not already playing
        if (!this.isPlaying[speaker]) {
            this.playAudioQueue(speaker);
        }
    }

    async playAudioQueue(speaker) {
        this.isPlaying[speaker] = true;

        while (this.audioQueues[speaker].length > 0) {
            const audioData = this.audioQueues[speaker].shift();

            // Convert PCM data to AudioBuffer
            const audioBuffer = await this.pcmToAudioBuffer(audioData);

            // Play the audio
            await this.playAudioBuffer(audioBuffer);
        }

        this.isPlaying[speaker] = false;
    }

    async pcmToAudioBuffer(pcmData) {
        // Gemini sends 16-bit PCM at 24kHz mono
        const sampleRate = 24000;
        const numChannels = 1;

        // Convert Uint8Array to Int16Array (16-bit samples)
        const int16Data = new Int16Array(pcmData.buffer);

        // Create AudioBuffer
        const audioBuffer = this.audioContext.createBuffer(
            numChannels,
            int16Data.length,
            sampleRate
        );

        // Convert Int16 to Float32 (Web Audio API format)
        const channelData = audioBuffer.getChannelData(0);
        for (let i = 0; i < int16Data.length; i++) {
            // Normalize 16-bit PCM to -1.0 to 1.0 range
            channelData[i] = int16Data[i] / 32768.0;
        }

        return audioBuffer;
    }

    playAudioBuffer(audioBuffer) {
        return new Promise((resolve) => {
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);
            source.onended = resolve;
            source.start();
        });
    }

    handleTranscript(speaker, text) {
        console.log(`[${speaker}] ${text}`);
        // TODO: Display in UI
        this.updateTranscriptUI(speaker, text);
    }

    handleSpeakingState(speaker, isSpeaking) {
        // TODO: Update sprite animation
        this.updateSpeakerVisuals(speaker, isSpeaking);
    }

    updateTranscriptUI(speaker, text) {
        // Add transcript to UI element
        const transcriptDiv = document.getElementById('transcript');
        if (transcriptDiv) {
            const entry = document.createElement('div');
            entry.className = `transcript-entry ${speaker.toLowerCase()}`;
            entry.innerHTML = `<strong>${speaker}:</strong> ${text}`;
            transcriptDiv.appendChild(entry);
            transcriptDiv.scrollTop = transcriptDiv.scrollHeight;
        }
    }

    updateSpeakerVisuals(speaker, isSpeaking) {
        // Visual feedback: pulse sprite when speaking
        const sprites = speaker === 'Obama' ? obamaSprites : trumpSprites;

        sprites.forEach(sprite => {
            if (isSpeaking) {
                // Add pulsing/glowing effect
                sprite.alpha = 1.0;
                // Could add filter, scale, or other effects
            } else {
                sprite.alpha = 0.8;
            }
        });
    }
}

// Initialize debate client
const debateClient = new DebateClient();
```

### Step 2.2: Add UI Controls

Modify `index.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AI Presidential Debate</title>
    <style>
        body {
            margin: 0;
            background-color: #333;
            font-family: Arial, sans-serif;
        }
        canvas {
            display: block;
        }

        /* Debate controls overlay */
        #controls {
            position: absolute;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 100;
        }

        #controls button {
            background: #4CAF50;
            color: white;
            border: none;
            padding: 15px 30px;
            font-size: 16px;
            cursor: pointer;
            border-radius: 5px;
            margin: 0 10px;
        }

        #controls button:hover {
            background: #45a049;
        }

        #controls button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }

        /* Transcript display */
        #transcript {
            position: absolute;
            bottom: 20px;
            left: 20px;
            right: 20px;
            max-height: 200px;
            background: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 15px;
            border-radius: 10px;
            overflow-y: auto;
            z-index: 100;
        }

        .transcript-entry {
            margin: 5px 0;
            padding: 5px;
        }

        .transcript-entry.obama {
            border-left: 4px solid #4A90E2;
        }

        .transcript-entry.trump {
            border-left: 4px solid #E24A4A;
        }

        .transcript-entry strong {
            display: inline-block;
            min-width: 80px;
        }
    </style>
</head>
<body>
    <!-- Controls -->
    <div id="controls">
        <button id="startBtn">Start Debate</button>
        <button id="stopBtn" disabled>Stop Debate</button>
    </div>

    <!-- Transcript -->
    <div id="transcript"></div>

    <!-- PIXI canvas will be inserted here -->

    <!-- Load libraries -->
    <script src="https://cdn.jsdelivr.net/npm/pixi.js@7/dist/pixi.min.js"></script>
    <script src="main.js"></script>
</body>
</html>
```

### Step 2.3: Add Control Logic

Add to end of `main.js`:

```javascript
// ========================================
// DEBATE CONTROLS
// ========================================

document.getElementById('startBtn').addEventListener('click', async () => {
    // Browser requires user interaction before playing audio
    await debateClient.connect();

    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').disabled = false;
});

document.getElementById('stopBtn').addEventListener('click', () => {
    if (debateClient.ws) {
        debateClient.ws.close();
    }

    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
});
```

---

## Part 3: Running the System

### Terminal 1: Start Backend

```bash
cd /path/to/hiyori_free_en
source venv/bin/activate
export GEMINI_API_KEY="your-key"
python debate_server.py
```

Expected output:
```
============================================================
AI Presidential Debate
============================================================
Topic: Should artificial intelligence be heavily regulated by the government?

WebSocket server started on ws://localhost:8765
Connected to Gemini Live API for both participants

Debate is running! Press Ctrl+C to stop.

Debate started! Obama is making the opening statement...
```

### Terminal 2: Serve Frontend

```bash
cd /path/to/hiyori_free_en
python -m http.server 8000
```

### Browser

1. Open `http://localhost:8000/index.html`
2. Click "Start Debate" button
3. **You'll hear both Obama and Trump speaking!**
4. See live transcripts at the bottom
5. Watch sprites animate when speaking

---

## Part 4: Audio Technical Details

### Audio Format from Gemini

- **Encoding**: PCM (raw, uncompressed)
- **Sample Rate**: 24,000 Hz
- **Bit Depth**: 16-bit signed integer
- **Channels**: Mono (1 channel)
- **Byte Order**: Little-endian

### Transmission Format

**Backend → Frontend:**
```json
{
    "type": "audio",
    "speaker": "Obama",
    "data": "0a1b2c3d..."  // Hex-encoded PCM bytes
}
```

### Decoding Process

1. **Hex to Bytes**: `"0a1b" → [10, 27]`
2. **Bytes to Int16**: `[10, 27] → 6922` (16-bit sample)
3. **Int16 to Float32**: `6922 / 32768 = 0.211` (Web Audio format)
4. **Create AudioBuffer**: Load Float32 samples into buffer
5. **Play**: Create BufferSourceNode and play

### Playback Strategy

**Queue-based playback** prevents audio gaps:

```javascript
// Queue chunks as they arrive
audioQueue.push(chunk);

// Play sequentially
while (audioQueue.length > 0) {
    const chunk = audioQueue.shift();
    await playChunk(chunk);  // Wait for completion
}
```

This ensures **gapless audio** even with network jitter.

---

## Part 5: Visual Feedback

### Speaking Indicators

When a character is speaking, you can:

1. **Alpha/Opacity**: Increase opacity to 1.0
2. **Scale pulse**: Slightly enlarge sprite
3. **Glow effect**: Add PIXI filter
4. **Gesture speed**: Cycle gestures faster
5. **Border/highlight**: Add colored outline

Example implementation:

```javascript
updateSpeakerVisuals(speaker, isSpeaking) {
    const sprites = speaker === 'Obama' ? obamaSprites : trumpSprites;

    if (isSpeaking) {
        // Make brighter
        sprites.forEach(sprite => {
            sprite.tint = 0xFFFFFF;  // Full brightness
            sprite.alpha = 1.0;
        });

        // Speed up gesture cycling
        const interval = speaker === 'Obama' ? OBAMA_GESTURE_INTERVAL : TRUMP_GESTURE_INTERVAL;
        // Reduce interval by 50%

    } else {
        // Dim slightly when not speaking
        sprites.forEach(sprite => {
            sprite.tint = 0xCCCCCC;  // Slightly dimmed
            sprite.alpha = 0.8;
        });
    }
}
```

---

## Part 6: Troubleshooting

### Backend Issues

**Problem**: `ModuleNotFoundError: No module named 'google.genai'`
```bash
pip install --upgrade google-genai
```

**Problem**: `PyAudio not found`
```bash
# macOS
brew install portaudio
pip install pyaudio

# Linux
sudo apt-get install portaudio19-dev python3-pyaudio
pip install pyaudio
```

**Problem**: `GEMINI_API_KEY not set`
```bash
export GEMINI_API_KEY="your-key"
python debate_server.py
```

### Frontend Issues

**Problem**: No audio playback

Check:
1. Browser console for errors
2. Web Audio API requires user interaction - click "Start Debate"
3. WebSocket connected? Check `ws.readyState === 1`
4. Audio context resumed? `audioContext.state === 'running'`

**Fix**:
```javascript
// Resume audio context on user interaction
document.getElementById('startBtn').addEventListener('click', async () => {
    if (audioContext.state === 'suspended') {
        await audioContext.resume();
    }
    await debateClient.connect();
});
```

**Problem**: WebSocket connection refused

Check:
1. Backend running? `python debate_server.py`
2. Port 8765 available? `lsof -i :8765`
3. Firewall blocking?

**Problem**: Choppy/stuttering audio

Solutions:
1. Increase audio queue buffer size
2. Check network latency
3. Reduce debate response length in prompts
4. Use faster model (though Gemini 2.0 Flash is already fast)

### Gemini API Issues

**Problem**: Rate limit exceeded

The Live API has limits. Solutions:
1. Add exponential backoff
2. Reduce concurrent sessions (test with one AI first)
3. Upgrade API quota

**Problem**: Model not available

```python
# Try different model
MODEL = "models/gemini-2.0-flash-exp"  # Current
MODEL = "models/gemini-1.5-flash"      # Fallback
```

---

## Part 7: Customization

### Change Debate Topic

Edit `debate_server.py`:

```python
if __name__ == "__main__":
    DEBATE_TOPIC = "Your custom topic here"
    server = DebateServer(debate_topic=DEBATE_TOPIC)
    asyncio.run(server.run())
```

### Change Voices

Available Gemini voices:
- `Puck` - Calm, measured
- `Charon` - Deep, authoritative
- `Kore` - Energetic, direct
- `Fenrir` - Intense
- `Aoede` - Smooth

Edit in `debate_server.py`:

```python
self.obama = DebateParticipant(
    name="Obama",
    voice="Puck",  # Change this
    ...
)
```

### Adjust Response Length

In persona prompts:

```python
system_instruction=f"""...
Keep your responses to 10-15 seconds.  # Change this
..."""
```

### Add Moderator

Create third `DebateParticipant`:

```python
self.moderator = DebateParticipant(
    name="Moderator",
    voice="Aoede",
    system_instruction="You are a debate moderator. Ask follow-up questions..."
)
```

Route moderator audio to both debaters.

---

## Part 8: Advanced Features

### Recording Debates

Save audio to WAV file:

```python
import wave

class DebateRecorder:
    def __init__(self, filename):
        self.wav = wave.open(filename, 'wb')
        self.wav.setnchannels(1)
        self.wav.setsampwidth(2)  # 16-bit
        self.wav.setframerate(24000)

    def write(self, audio_data):
        self.wav.writeframes(audio_data)

    def close(self):
        self.wav.close()
```

### Topic Selection UI

Add input field in HTML:

```html
<input type="text" id="topicInput" placeholder="Enter debate topic">
<button onclick="startWithTopic()">Start Debate</button>
```

Send to backend via WebSocket:

```javascript
function startWithTopic() {
    const topic = document.getElementById('topicInput').value;
    ws.send(JSON.stringify({
        type: 'set_topic',
        topic: topic
    }));
}
```

### Fact-Checking

Integrate web search in persona prompts:

```python
system_instruction=f"""...
If you're unsure about a fact, acknowledge it.
Cite sources when making claims.
..."""
```

Or add separate fact-checker AI that monitors transcript.

---

## Summary

**You now have:**

✅ Backend server routing audio between two Gemini AIs
✅ WebSocket communication to browser
✅ Audio playback through Web Audio API
✅ Visual feedback on sprites
✅ Live transcript display
✅ Start/stop controls

**The debate will sound natural** because Gemini's VAD handles interruptions and turn-taking automatically!

**Next steps:**
1. Test with simple topic
2. Tune persona prompts for better debates
3. Add recording, topic selection, or other features
4. Have fun watching AIs debate!

---

## Architecture Diagram (Detailed)

```
┌─────────────────────── Browser ────────────────────────┐
│                                                          │
│  User clicks "Start Debate"                             │
│         │                                                │
│         ▼                                                │
│  ┌──────────────────────────────────────────────┐       │
│  │         DebateClient (main.js)               │       │
│  │                                              │       │
│  │  - WebSocket connection                      │       │
│  │  - AudioContext (Web Audio API)             │       │
│  │  - Audio queues for Obama/Trump             │       │
│  │  - PCM→AudioBuffer conversion               │       │
│  │  - Playback scheduling                       │       │
│  └──────────────────────────────────────────────┘       │
│         │                          ▲                     │
│         │ WS Message               │ Audio Data          │
│         ▼                          │                     │
│  ┌─────────────┐          ┌─────────────┐               │
│  │   Obama     │          │   Trump     │               │
│  │   Sprite    │          │   Sprite    │               │
│  │  🔊 Speaker │          │  🔊 Speaker │               │
│  └─────────────┘          └─────────────┘               │
│                                                          │
└──────────────────────────────────────────────────────────┘
                          │
                WebSocket (JSON)
                          │
                          ▼
┌─────────────────── Python Backend ─────────────────────┐
│                                                          │
│  ┌────────��───────────────────────────────────┐        │
│  │      DebateServer (debate_server.py)       │        │
│  │                                            │        │
│  │  - WebSocket server (port 8765)           │        │
│  │  - Manages two Gemini sessions            │        │
│  │  - Routes audio between AIs               │        │
│  │  - Broadcasts to web clients              │        │
│  └────────────────────────────────────────────┘        │
│         │                          │                    │
│         ▼                          ▼                    │
│  ┌─────────────────┐      ┌─────────────────┐         │
│  │ DebateParticipant│      │ DebateParticipant│         │
│  │    (Obama)      │      │    (Trump)      │         │
│  │                 │      │                 │         │
│  │ audio_in_queue ◄┼──────┼─ audio_out_queue│         │
│  │ audio_out_queue┼───────┼► audio_in_queue │         │
│  │ broadcast_queue│      │ broadcast_queue│         │
│  └─────────────────┘      └─────────────────┘         │
│         │                          │                    │
│         ▼                          ▼                    │
│  ┌─────────────────┐      ┌─────────────────┐         │
│  │ Gemini Session 1│      │ Gemini Session 2│         │
│  │   (Live API)    │      │   (Live API)    │         │
│  │                 │      │                 │         │
│  │ Voice: Puck     │      │ Voice: Kore     │         │
│  │ Persona: Obama  │      │ Persona: Trump  │         │
│  └─────────────────┘      └─────────────────┘         │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## File Structure

```
hiyori_free_en/
├── index.html                  # HTML with controls + transcript UI
├── main.js                     # PIXI sprite logic + DebateClient
├── debate_server.py            # Python backend (Gemini + WebSocket)
├── requirements.txt            # Python dependencies
├── obama.png                   # Obama sprite images
├── obama_gesture1.png
├── obama_gesture2.png
├── trump.png                   # Trump sprite images
├── trump_gesture1.png
├── trump_gesture2.png
└── IMPLEMENTATION_GUIDE.md     # This file
```

## Getting Help

If you encounter issues:

1. Check browser console for JavaScript errors
2. Check Python terminal for backend errors
3. Verify WebSocket connection: `ws.readyState`
4. Test audio context: `audioContext.state`
5. Check Gemini API quota/limits

Good luck building your AI debate system! 🎤🤖
