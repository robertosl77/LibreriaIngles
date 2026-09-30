import { Component, OnDestroy, input, output, signal } from '@angular/core';

export interface RecordedAudio {
  blob: Blob;
  durationMs: number;
}

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
          } @else if (confirmed()) {
            <span class="confirmed small"><strong>✓ Respuesta grabada</strong></span>
            <button class="btn btn-sm" type="button" (click)="start()" [disabled]="busy()">
              Grabar de nuevo
            </button>
          } @else {
            <button class="record-btn" type="button" (click)="start()" [disabled]="busy()">
              <span class="record-icon" aria-hidden="true"></span>
              <span>Grabar respuesta</span>
            </button>
            <span class="muted small">Máximo {{ maxSeconds() }} segundos.</span>
          }
        </div>
      } @else {
        <audio [src]="recordedUrl()" controls></audio>
        @if (confirmed()) {
          <div class="row">
            <span class="confirmed small"><strong>✓ Respuesta grabada</strong></span>
            <button class="btn btn-sm" type="button" (click)="start()" [disabled]="busy()">
              Grabar de nuevo
            </button>
            <span class="muted small">{{ elapsedSeconds() }} s</span>
          </div>
        } @else {
          <div class="row">
            <button class="btn btn-primary btn-sm" type="button" (click)="accept()" [disabled]="busy()">
              @if (busy()) { <span class="spinner"></span> Transcribiendo… } @else { Confirmar respuesta }
            </button>
            <button class="btn btn-sm" type="button" (click)="start()" [disabled]="busy()">
              Volver a grabar
            </button>
            <span class="muted small">{{ elapsedSeconds() }} s</span>
          </div>
        }
      }
    </div>
  `,
  styles: `
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

  readonly recording = signal(false);
  readonly recordedUrl = signal<string | null>(null);
  readonly elapsedSeconds = signal(0);
  readonly error = signal<string | null>(null);

  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: BlobPart[] = [];
  private blob: Blob | null = null;
  private startedAt = 0;
  private durationMs = 0;
  private timerId: number | null = null;

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
      this.recordingStarted.emit();
      this.timerId = window.setInterval(() => {
        const elapsed = Date.now() - this.startedAt;
        this.elapsedSeconds.set(Math.min(this.maxSeconds(), Math.ceil(elapsed / 1000)));
        if (elapsed >= this.maxSeconds() * 1000) {
          this.stop();
        }
      }, 250);
    } catch {
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
