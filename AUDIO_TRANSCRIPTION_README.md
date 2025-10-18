# Audio Recording & Transcription Feature

## Overview

This feature adds audio recording capability to teach sessions, allowing users to narrate their actions. The audio is then transcribed using ElevenLabs Speech-to-Text API and included in plan synthesis to help the AI better understand user intent.

## Architecture

### Flow

1. **Teach Session Start**
   - User starts a teach session
   - Frontend requests microphone permission
   - Audio recording begins (browser-based via WebRTC)
   - User demonstrates actions while narrating

2. **Teach Session Stop**
   - User stops the teach session
   - Audio recording stops and converts to WAV format
   - Audio sent to backend as base64-encoded WAV
   - Stored in `RecordingBundle.audio_wav_base64`

3. **Plan Synthesis**
   - User clicks "Synthesize Plan"
   - Backend checks if `audio_wav_base64` exists
   - If yes, sends to ElevenLabs STT API
   - Transcript aligned with recording timeline
   - Formatted as time-windowed chunks
   - Included in synthesis prompt
   - AI uses transcript to understand intent

4. **Optional Cleanup**
   - After successful transcription, audio can be deleted to save space
   - Transcript is preserved for future use

## Files Modified/Created

### Backend

**New Files:**
- `backend/app/transcription.py` - ElevenLabs SDK integration and transcript formatting

**Modified Files:**
- `backend/app/synthesis.py` - Calls transcription service, enhances prompt with transcript
- `backend/app/api.py` - Accepts audio in `/teach/stop`, adds `/recordings/{id}/audio` cleanup endpoint
- `backend/requirements.txt` - Added `elevenlabs` SDK dependency

### Frontend

**New Files:**
- `frontend/app/src/utils/audioRecorder.ts` - Browser-based audio recording utility

**Modified Files:**
- `frontend/app/src/hooks/useTeachSession.ts` - Integrates audio recording into teach session lifecycle

## Configuration

### Environment Variables

Add to your `.env` file or environment:

```bash
# Required for transcription
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# Optional configuration
ENABLE_TRANSCRIPTION=1                 # Enable/disable transcription (default: 1)
TRANSCRIPTION_LANGUAGE=en              # Language code (default: en)
TRANSCRIPTION_CHUNK_WINDOW=5.0         # Time window for grouping words (default: 5.0 seconds)

# Optional: Plan synthesis settings (already exist)
PLAN_SYNTH_ENABLED=1
GEMINI_API_KEY=your_gemini_api_key_here
```

## Testing Guide

### 1. Prerequisites

```bash
# Ensure you have your ElevenLabs API key
export ELEVENLABS_API_KEY=your_key_here

# Install backend dependencies (includes elevenlabs SDK)
cd backend
pip install -r requirements.txt

# Start the backend
cd backend
python -m uvicorn app.api:app --reload

# Start the frontend (in another terminal)
cd frontend
yarn dev
```

### 2. Test Audio Recording

1. **Open the application** in your browser (Chrome, Firefox, or Safari)
2. **Start a teach session**
   - Click "Start Teaching"
   - Grant microphone permission when prompted
   - Check console for: `Audio: Microphone recording started`
3. **Perform actions while narrating:**
   - Example: "Now I'm going to click the search button"
   - Example: "I'll enter the username as admin"
   - Example: "Then I'll submit the form"
4. **Stop the teach session**
   - Click "Stop Teaching"
   - Check console for: `Audio: Recording saved (X KB)`
   - Check response: `Recording {id} saved with audio`

### 3. Test Transcription

1. **After stopping the teach session**, click **"Synthesize Plan"**
2. **Check backend logs** for transcription progress:
   ```
   INFO: Starting audio transcription...
   INFO: Transcription completed: 42 words in 3 chunks
   ```
3. **Check the generated plan:**
   - Plan name should reflect user's stated intent
   - Step descriptions should reference words from narration
   - Variables should match names mentioned verbally

### 4. Test Error Handling

**No microphone:**
- Deny microphone permission
- Should show: `Audio: Recording disabled: ...`
- Teach session should continue without audio ✅

**No audio data:**
- Start and immediately stop teach session
- Should show: `Audio: No audio data captured`
- Plan synthesis should work without transcript ✅

**Transcription failure:**
- Invalid or missing API key
- Backend should log error
- Plan synthesis should continue without transcript ✅

### 5. Test Audio Cleanup

```bash
# After successful transcription, optionally delete audio to save space
curl -X DELETE http://localhost:8000/recordings/{recording_id}/audio

# Response:
{
  "ok": true,
  "message": "Audio data deleted successfully",
  "transcript_preserved": true
}
```

## Example Workflow

### Scenario: Recording a Login Flow

1. **Start teach session**
   - Console: `Audio: Microphone recording started`

2. **User narrates while performing actions:**
   ```
   [0-5s] "First, I'll open the login page and locate the username field"
   [5-10s] "Now I'll enter my username. Let's call this variable {username}"
   [10-15s] "Next, I need to enter the password. This will be {password}"
   [15-20s] "Finally, I'll click the login button to submit"
   ```

3. **Stop teach session**
   - Console: `Audio: Recording saved (127 KB)`
   - Response: `Recording abc123 saved with audio`

4. **Synthesize plan**
   - Backend transcribes audio
   - Transcript included in prompt:
     ```
     USER NARRATION:
     [0.0-5.0s] "First, I'll open the login page and locate the username field"
     [5.1-10.3s] "Now I'll enter my username. Let's call this variable username"
     [10.4-15.0s] "Next, I need to enter the password. This will be password"
     [15.1-20.0s] "Finally, I'll click the login button to submit"
     ```

5. **Generated plan benefits:**
   - **Name**: "Login to application" (inferred from narration)
   - **Variables**: `{username}`, `{password}` (mentioned by user)
   - **Step 1 title**: "Enter login credentials"
   - **Step 1 instructions**: "Locate the username field and enter {username}, then locate the password field and enter {password}"
   - **Step 2 title**: "Submit login form"
   - **Step 2 instructions**: "Click the login button to submit the credentials"

## API Reference

### POST /teach/stop

**Request:**
```json
{
  "audioWavBase64": "UklGRiQAAA..." // Optional base64-encoded WAV
}
```

**Response:**
```json
{
  "recordingId": "abc123",
  "frames": [...],
  "markers": [...],
  "events": [...],
  "hasAudio": true
}
```

### DELETE /recordings/{recording_id}/audio

Deletes audio data while preserving transcript.

**Response:**
```json
{
  "ok": true,
  "message": "Audio data deleted successfully",
  "transcript_preserved": true
}
```

## Troubleshooting

### Audio not recording

**Issue:** Console shows "Audio recording not supported"
- **Solution:** Use Chrome, Firefox, or Safari (latest versions)
- **Note:** Some older browsers don't support MediaRecorder API

**Issue:** Microphone permission denied
- **Solution:** Check browser settings, allow microphone access
- **Note:** Teach session will continue without audio (graceful degradation)

### Transcription failing

**Issue:** Backend logs show "Transcription service disabled"
- **Solution:** Check `ELEVENLABS_API_KEY` is set correctly
- **Solution:** Verify `ENABLE_TRANSCRIPTION=1` in environment

**Issue:** Backend logs show "Transcription failed: 401 Unauthorized"
- **Solution:** Verify ElevenLabs API key is valid
- **Solution:** Check your ElevenLabs account has available credits

**Issue:** Backend logs show "Transcription failed: 400 Bad Request"
- **Solution:** Audio format may be invalid
- **Solution:** Check browser's WAV encoding compatibility

### Large audio files

**Issue:** Request payload too large
- **Solution:** Keep teach sessions under 10 minutes
- **Solution:** Consider compressing audio or using lower sample rate
- **Note:** ElevenLabs supports up to 3GB files, but HTTP may have limits

## Best Practices

### For Users

1. **Speak clearly** - Helps transcription accuracy
2. **Mention variable names** - Say "{username}" when you want a variable
3. **Explain intent** - Say "I'm searching for products" not just "clicking button"
4. **Keep sessions short** - < 5 minutes for faster uploads

### For Developers

1. **Monitor transcription costs** - ElevenLabs charges per hour transcribed
2. **Clean up audio files** - Delete after transcription to save storage
3. **Handle errors gracefully** - Always allow plan synthesis even without transcript
4. **Log failures** - Console logging helps debugging

## Cost Considerations

### ElevenLabs Pricing (as of 2024)

| Tier     | Hours Included | Price/Additional Hour |
|----------|----------------|----------------------|
| Free     | Unavailable    | Unavailable          |
| Starter  | 12.5 hours     | N/A                  |
| Creator  | 62.8 hours     | $0.48                |
| Pro      | 300 hours      | $0.40                |
| Scale    | 1,100 hours    | $0.33                |
| Business | 6,000 hours    | $0.22                |

**Example:**
- 100 teach sessions × 2 minutes average = 200 minutes = 3.3 hours
- Cost on Pro tier: ~$1.32

### Optimization

- Only transcribe when user clicks "Synthesize Plan" (not on every recording)
- Delete audio after transcription to save storage costs
- Use `ENABLE_TRANSCRIPTION=0` to disable feature if not needed

## Future Enhancements

### Potential Improvements

1. **Real-time transcription** - Show transcript while recording
2. **Speaker diarization** - Support multiple speakers in demonstrations
3. **Transcript editing** - Allow users to correct transcription before synthesis
4. **Audio compression** - Reduce file sizes for faster uploads
5. **Multilingual support** - Detect and transcribe multiple languages
6. **WebSocket streaming** - Stream audio chunks during recording
7. **Visual waveform** - Show audio levels while recording

## Security & Privacy

- **Microphone access** - Requested only when needed, user must grant permission
- **Audio storage** - Stored temporarily, can be deleted after transcription
- **Transcript privacy** - Stored permanently with recording, contains user speech
- **API keys** - ElevenLabs API key must be kept secure on backend
- **HTTPS recommended** - Use HTTPS in production for secure transmission

## Conclusion

This feature significantly improves plan synthesis quality by capturing user intent through voice narration. The implementation is designed for:
- **Ease of use** - Automatic recording during teach sessions
- **Reliability** - Graceful degradation if audio/transcription fails
- **Flexibility** - Optional feature that doesn't break existing workflows
- **Performance** - Transcription only happens on-demand during synthesis

For questions or issues, check the backend logs and browser console for detailed error messages.
