import { Component, OnDestroy, input, output, signal } from '@angular/core';

export interface RecordedAudio {
  blob: Blob;
  durationMs: number;
}

// T-046 v2: ~1 s de silencio después de hablar (antes 1,8 s: se sentía lento).
// Una pausa normal entre palabras es más corta, así que no corta a mitad de la frase.
const AUTO_STOP_SILENCE_MS = 1000;
const MIN_VOICE_MS = 180;
const MIN_VOICE_RMS = 0.018;
const MAX_NOISE_SAMPLE_RMS = 0.03;
const NOISE_MULTIPLIER = 2.2;

@Component({
  selector: 'app-audio-recorder',
  template: `
    <div class="recorder stack">
      @if (error()) {
        <p class="small error">{{ error() }}</p>
      }

      @if (!recordedUrl()) {
        <div class="row">
          @if (recording()) {
            <button class="btn btn-sm btn-danger" type="button" (click)="stop()">
              <span class="stop-icon" aria-hidden="true"></span>
              Detener
            </button>
            <strong class="small recording">Grabando… {{ elapsedSeconds() }} s</strong>
            @if (autoStopAvailable()) {
              <span class="muted small">Se detiene solo al terminar de hablar.</span>
            }
          } @else if (confirmed()) {
            <span class="confirmed small"><strong>✓ Respuesta grabada</strong></span>
            <button class="btn btn-sm" type="button" (click)="start()" [disabled]="busy()">
              Volver a grabar
            </button>
          } @else {
            <button class="record-btn" type="button" (click)="start()" [disabled]="busy()">
              <span class="record-icon" aria-hidden="true"></span>
              <span>Grabar respuesta</span>
            </button>
            <span class="muted small">
              @if (autoStopAvailable()) {
                Se detiene sola cuando terminás de hablar · máximo {{ maxSeconds() }} segundos.
              } @else {
                Máximo {{ maxSeconds() }} segundos.
              }
            </span>
          }
        </div>
      } @else {
        <audio [src]="recordedUrl()" controls></audio>
        <div class="row">
          @if (confirmed()) {
            <span class="confirmed small"><strong>✓ Respuesta grabada</strong></span>
          } @else if (busy()) {
            <span class="small muted"><span class="spinner"></span> Guardando…</span>
          } @else {
            <!-- Solo si falló el guardado automático. -->
            <span class="pending small">No se pudo guardar la grabación.</span>
            <button class="btn btn-sm" type="button" (click)="accept()">Reintentar</button>
          }
          <button class="btn btn-sm" type="button" (click)="start()" [disabled]="busy()">
            Volver a grabar
          </button>
          <span class="muted small">{{ elapsedSeconds() }} s</span>
        </div>
      }
    </div>
  `,
  styles: `
    .pending { color: var(--bad); }
    .recorder { gap: 0.55rem; padding: 0.7rem; border: 1px solid var(--border); border-radius: 0.6rem; background: var(--bg); }
    audio { width: min(100%, 32rem); height: 2.4rem; }
    .record-btn {
      display: inline-flex; align-items: center; gap: 0.65rem;
      padding: 0.65rem 1rem; border: 1px solid #d23b3b; border-radius: 999px;
      background: #fff; color: #a51f1f; font: inherit; font-weight: 700; cursor: pointer;
    }
    .record-btn:hover:not(:disabled) { background: #fff3f3; }
    .record-btn:disabled { opacity: 0.55; cursor: not-allowed; }
    .record-icon {
      width: 1rem; height: 1rem; border-radius: 50%; background: #d93025;
      box-shadow: 0 0 0 4px rgb(217 48 37 / 0.12);
    }
    .stop-icon { width: 0.75rem; height: 0.75rem; background: currentColor; display: inline-block; }
    .confirmed { color: var(--ok); }
    .recording { color: var(--bad); }
    .error { color: var(--bad); margin: 0; }
  `
})
export class AudioRecorderComponent implements OnDestroy {
  readonly busy = input(false);
  readonly confirmed = input(false);
  readonly maxSeconds = input(60);
  readonly accepted = output<RecordedAudio>();
  readonly recordingStarted = output<void>();
  /** true: hay una grabación hecha que todavía no se guardó (no cuenta como respuesta). */
  readonly pendingChange = output<boolean>();

  readonly recording = signal(false);
  readonly recordedUrl = signal<string | null>(null);
  readonly elapsedSeconds = signal(0);
  readonly error = signal<string | null>(null);
  readonly autoStopAvailable = signal(
    typeof window !== 'undefined' && typeof window.AudioContext !== 'undefined'
  );

  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: BlobPart[] = [];
  private blob: Blob | null = null;
  private startedAt = 0;
  private durationMs = 0;
  private timerId: number | null = null;

  private audioContext: AudioContext | null = null;
  private audioSource: MediaStreamAudioSourceNode | null = null;
  private analyser: AnalyserNode | null = null;
  private analyserData: Uint8Array<ArrayBuffer> | null = null;
  private voiceFrameId: number | null = null;
  private speechDetected = false;
  private voiceCandidateSince: number | null = null;
  private lastVoiceAt: number | null = null;
  private noiseFloorRms = 0.008;

  async start(): Promise<void> {
    this.error.set(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      this.error.set('Este navegador no permite grabar audio.');
      return;
    }
    try {
      this.cleanupRecording();
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = this.preferredMimeType();
      this.recorder = new MediaRecorder(
        this.stream,
        mimeType ? { mimeType } : undefined
      );
      this.chunks = [];
      this.recorder.ondataavailable = (event) => {
        if (event.data.size) {
          this.chunks.push(event.data);
        }
      };
      this.recorder.onstop = () => this.finish();
      this.startedAt = Date.now();
      this.elapsedSeconds.set(0);
      this.recording.set(true);
      this.recorder.start(250);
      this.startVoiceDetection();
      this.recordingStarted.emit();
      this.pendingChange.emit(false);
      this.timerId = window.setInterval(() => {
        const elapsed = Date.now() - this.startedAt;
        this.elapsedSeconds.set(Math.min(this.maxSeconds(), Math.ceil(elapsed / 1000)));
        if (elapsed >= this.maxSeconds() * 1000) {
          this.stop();
        }
      }, 250);
    } catch {
      this.stopVoiceDetection();
      this.stopTracks();
      this.error.set(
        'No se pudo acceder al micrófono. Permití el acceso y usá HTTPS o localhost.'
      );
    }
  }

  stop(): void {
    if (this.recorder?.state === 'recording') {
      this.recorder.stop();
    }
  }

  accept(): void {
    if (this.blob && this.durationMs > 0) {
      this.accepted.emit({ blob: this.blob, durationMs: this.durationMs });
    }
  }

  reset(): void {
    this.cleanupRecording();
    this.elapsedSeconds.set(0);
    this.error.set(null);
  }

  ngOnDestroy(): void {
    this.cleanupRecording();
  }

  private finish(): void {
    this.clearTimer();
    this.stopVoiceDetection();
    this.durationMs = Math.min(
      this.maxSeconds() * 1000,
      Math.max(1, Date.now() - this.startedAt)
    );
    this.elapsedSeconds.set(Math.max(1, Math.ceil(this.durationMs / 1000)));
    const type = this.recorder?.mimeType || 'audio/webm';
    this.blob = new Blob(this.chunks, { type });
    const oldUrl = this.recordedUrl();
    if (oldUrl) {
      URL.revokeObjectURL(oldUrl);
    }
    this.recordedUrl.set(URL.createObjectURL(this.blob));
    this.recording.set(false);
    this.stopTracks();
    this.pendingChange.emit(true);
    // T-046 v2: lo grabado ES la respuesta (se transcribe y corrige al enviar la clase):
    // se guarda solo, sin "Confirmar respuesta".
    this.accept();
  }

  private startVoiceDetection(): void {
    this.stopVoiceDetection();
    this.speechDetected = false;
    this.voiceCandidateSince = null;
    this.lastVoiceAt = null;
    this.noiseFloorRms = 0.008;

    if (!this.stream || typeof window.AudioContext === 'undefined') {
      this.autoStopAvailable.set(false);
      return;
    }

    try {
      this.audioContext = new AudioContext();
      this.audioSource = this.audioContext.createMediaStreamSource(this.stream);
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 1024;
      this.analyser.smoothingTimeConstant = 0.2;
      this.audioSource.connect(this.analyser);
      this.analyserData = new Uint8Array(this.analyser.fftSize);
      this.autoStopAvailable.set(true);
      this.monitorVoice();
    } catch {
      this.autoStopAvailable.set(false);
      this.stopVoiceDetection();
    }
  }

  private monitorVoice(): void {
    const analyser = this.analyser;
    const data = this.analyserData;
    if (!analyser || !data || this.recorder?.state !== 'recording') {
      return;
    }

    analyser.getByteTimeDomainData(data);
    let energy = 0;
    for (const sample of data) {
      const normalized = (sample - 128) / 128;
      energy += normalized * normalized;
    }
    const rms = Math.sqrt(energy / data.length);
    const now = performance.now();
    const threshold = Math.max(MIN_VOICE_RMS, this.noiseFloorRms * NOISE_MULTIPLIER);

    if (rms >= threshold) {
      if (this.speechDetected) {
        this.lastVoiceAt = now;
      } else {
        this.voiceCandidateSince ??= now;
        if (now - this.voiceCandidateSince >= MIN_VOICE_MS) {
          this.speechDetected = true;
          this.lastVoiceAt = now;
        }
      }
    } else {
      this.voiceCandidateSince = null;

      // Antes de detectar voz, aprende lentamente el ruido ambiente sin confundir
      // una voz clara con el piso de ruido.
      if (!this.speechDetected && rms <= MAX_NOISE_SAMPLE_RMS) {
        this.noiseFloorRms = this.noiseFloorRms * 0.9 + rms * 0.1;
      }

      if (
        this.speechDetected &&
        this.lastVoiceAt !== null &&
        now - this.lastVoiceAt >= AUTO_STOP_SILENCE_MS
      ) {
        this.stop();
        return;
      }
    }

    this.voiceFrameId = window.requestAnimationFrame(() => this.monitorVoice());
  }

  private stopVoiceDetection(): void {
    if (this.voiceFrameId !== null) {
      window.cancelAnimationFrame(this.voiceFrameId);
      this.voiceFrameId = null;
    }
    this.audioSource?.disconnect();
    this.audioSource = null;
    this.analyser?.disconnect();
    this.analyser = null;
    this.analyserData = null;
    if (this.audioContext) {
      void this.audioContext.close();
      this.audioContext = null;
    }
  }

  private preferredMimeType(): string {
    for (const type of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']) {
      if (MediaRecorder.isTypeSupported(type)) {
        return type;
      }
    }
    return '';
  }

  private cleanupRecording(): void {
    this.clearTimer();
    this.stopVoiceDetection();
    if (this.recorder?.state === 'recording') {
      this.recorder.stop();
    }
    this.recorder = null;
    this.stopTracks();
    this.chunks = [];
    this.blob = null;
    this.durationMs = 0;
    this.recording.set(false);
    const url = this.recordedUrl();
    if (url) {
      URL.revokeObjectURL(url);
      this.recordedUrl.set(null);
    }
  }

  private stopTracks(): void {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }

  private clearTimer(): void {
    if (this.timerId !== null) {
      window.clearInterval(this.timerId);
      this.timerId = null;
    }
  }
}
