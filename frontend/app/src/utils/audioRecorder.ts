/**
 * Audio recording utility for capturing user narration during teach sessions.
 *
 * This module provides a simple interface for recording audio from the user's microphone
 * and converting it to WAV format for submission with the teach session recording.
 *
 * Features:
 * - Browser-based recording using WebRTC MediaRecorder API
 * - Automatic WAV conversion for compatibility with ElevenLabs STT API
 * - Base64 encoding for easy transmission via HTTP/WebSocket
 */

/**
 * Convert an AudioBuffer to WAV format bytes.
 *
 * This implements a simple WAV file format encoder that creates a standard
 * PCM WAV file from raw audio samples.
 *
 * @param audioBuffer - The AudioBuffer containing audio samples
 * @returns ArrayBuffer containing WAV file bytes
 */
function audioBufferToWav(audioBuffer: AudioBuffer): ArrayBuffer {
  const numChannels = audioBuffer.numberOfChannels;
  const sampleRate = audioBuffer.sampleRate;
  const format = 1; // PCM
  const bitsPerSample = 16;

  // Get audio data from all channels
  const channelData: Float32Array[] = [];
  for (let channel = 0; channel < numChannels; channel++) {
    channelData.push(audioBuffer.getChannelData(channel));
  }

  const length = audioBuffer.length;
  const interleaved = new Int16Array(length * numChannels);

  // Interleave channels and convert float32 to int16
  for (let i = 0; i < length; i++) {
    for (let channel = 0; channel < numChannels; channel++) {
      const sample = Math.max(-1, Math.min(1, channelData[channel][i]));
      interleaved[i * numChannels + channel] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
  }

  const wavBytes = new ArrayBuffer(44 + interleaved.length * 2);
  const view = new DataView(wavBytes);

  // WAV file header
  const writeString = (offset: number, string: string) => {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  };

  writeString(0, 'RIFF'); // ChunkID
  view.setUint32(4, 36 + interleaved.length * 2, true); // ChunkSize
  writeString(8, 'WAVE'); // Format
  writeString(12, 'fmt '); // Subchunk1ID
  view.setUint32(16, 16, true); // Subchunk1Size (PCM)
  view.setUint16(20, format, true); // AudioFormat
  view.setUint16(22, numChannels, true); // NumChannels
  view.setUint32(24, sampleRate, true); // SampleRate
  view.setUint32(28, sampleRate * numChannels * bitsPerSample / 8, true); // ByteRate
  view.setUint16(32, numChannels * bitsPerSample / 8, true); // BlockAlign
  view.setUint16(34, bitsPerSample, true); // BitsPerSample
  writeString(36, 'data'); // Subchunk2ID
  view.setUint32(40, interleaved.length * 2, true); // Subchunk2Size

  // Write PCM samples
  const offset = 44;
  for (let i = 0; i < interleaved.length; i++) {
    view.setInt16(offset + i * 2, interleaved[i], true);
  }

  return wavBytes;
}

/**
 * Convert ArrayBuffer to base64 string.
 *
 * @param buffer - ArrayBuffer to encode
 * @returns Base64-encoded string
 */
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Audio recorder for teach sessions.
 *
 * Manages microphone access, recording, and conversion to WAV format.
 *
 * @example
 * ```typescript
 * const recorder = new AudioRecorder();
 *
 * // Request mic permission and start recording
 * await recorder.start();
 *
 * // Stop recording and get WAV as base64
 * const audioBase64 = await recorder.stop();
 *
 * // Send to backend
 * fetch('/api/recording', {
 *   method: 'POST',
 *   body: JSON.stringify({ audio: audioBase64 })
 * });
 * ```
 */
export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;

  /**
   * Check if audio recording is supported in this browser.
   *
   * @returns True if MediaRecorder and getUserMedia are available
   */
  static isSupported(): boolean {
    return !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  }

  /**
   * Start recording audio from the user's microphone.
   *
   * This will request microphone permission if not already granted.
   *
   * @throws Error if microphone access is denied or not supported
   */
  async start(): Promise<void> {
    if (!AudioRecorder.isSupported()) {
      throw new Error('Audio recording is not supported in this browser');
    }

    try {
      // Request microphone access
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 44100,
        },
      });

      // Create MediaRecorder
      // Try to use WAV if supported, otherwise use WebM/Opus (we'll convert later)
      const mimeType = MediaRecorder.isTypeSupported('audio/wav')
        ? 'audio/wav'
        : MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';

      this.mediaRecorder = new MediaRecorder(this.stream, { mimeType });
      this.audioChunks = [];

      // Collect audio data chunks
      this.mediaRecorder.addEventListener('dataavailable', (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      });

      // Start recording (collect data every second)
      this.mediaRecorder.start(1000);

      console.log('Audio recording started');
    } catch (error) {
      this.cleanup();
      throw new Error(
        `Failed to start audio recording: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  /**
   * Stop recording and convert audio to WAV format.
   *
   * @returns Base64-encoded WAV audio, or null if no audio was recorded
   */
  async stop(): Promise<string | null> {
    if (!this.mediaRecorder) {
      console.warn('No active recording to stop');
      return null;
    }

    return new Promise<string | null>((resolve, reject) => {
      if (!this.mediaRecorder) {
        resolve(null);
        return;
      }

      // Set up one-time stop handler
      this.mediaRecorder.addEventListener('stop', async () => {
        try {
          if (this.audioChunks.length === 0) {
            console.warn('No audio data recorded');
            this.cleanup();
            resolve(null);
            return;
          }

          // Combine chunks into single blob
          const audioBlob = new Blob(this.audioChunks, {
            type: this.mediaRecorder?.mimeType || 'audio/webm',
          });

          // Convert to WAV format
          const wavBase64 = await this.convertToWav(audioBlob);

          this.cleanup();
          console.log('Audio recording stopped and converted to WAV');
          resolve(wavBase64);
        } catch (error) {
          this.cleanup();
          reject(error);
        }
      });

      // Stop the recorder
      this.mediaRecorder.stop();
    });
  }

  /**
   * Convert audio blob to WAV format and encode as base64.
   *
   * @param blob - Audio blob from MediaRecorder
   * @returns Base64-encoded WAV audio
   */
  private async convertToWav(blob: Blob): Promise<string> {
    // Create audio context if needed
    if (!this.audioContext) {
      this.audioContext = new AudioContext();
    }

    // Read blob as array buffer
    const arrayBuffer = await blob.arrayBuffer();

    // Decode audio data
    const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);

    // Convert to WAV format
    const wavArrayBuffer = audioBufferToWav(audioBuffer);

    // Encode as base64
    const base64 = arrayBufferToBase64(wavArrayBuffer);

    return base64;
  }

  /**
   * Check if currently recording.
   *
   * @returns True if recording is active
   */
  isRecording(): boolean {
    return this.mediaRecorder?.state === 'recording';
  }

  /**
   * Clean up resources (stop tracks, release microphone).
   */
  private cleanup(): void {
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }

    this.mediaRecorder = null;
    this.audioChunks = [];

    // Note: We keep audioContext alive for potential reuse
    // It will be garbage collected when the recorder instance is destroyed
  }

  /**
   * Abort recording and clean up without returning audio.
   */
  abort(): void {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
    this.cleanup();
    console.log('Audio recording aborted');
  }
}
