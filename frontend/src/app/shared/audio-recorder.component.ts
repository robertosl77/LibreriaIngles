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
          @if (!recording()) {
            <button class="btn btn-sm" type="button" (click)="start()" [disabled]="busy()">
              Grabar respuesta
            </button>
            <span class="muted small">Máximo {{ maxSeconds() }} segundos.</span>
          } @else {
            <button class="btn btn-sm btn-danger" type="button" (click)="stop()">
              Detener
            </button>
            <strong class="small recording">Grabando… {{ elapsedSeconds() }} s</strong>
          }
        </div>
      } @else {
        <audio [src]="recordedUrl()" controls></audio>
        <div class="row">
          <button class="btn btn-primary btn-sm" type="button" (click)="accept()" [disabled]="busy()">
            @if (busy()) { <span class="spinner"></span> Transcribiendo… } @else { Usar esta grabación }
          </button>
          <button class="btn btn-sm" type="button" (click)="reset()" [disabled]="busy()">
            Volver a grabar
          </button>
          <span class="muted small">{{ elapsedSeconds() }} s</span>
        </div>
      }
    </div>
  `,
  styles: `
    .recorder { gap: 0.55rem; padding: 0.7rem; border: 1px solid var(--border); border-radius: 0.6rem; background: var(--bg); }
    audio { width: min(100%, 32rem); height: 2.4rem; }
    .recording { color: var(--bad); }
    .error { color: var(--bad); margin: 0; }
  `
})
export class AudioRecorderComponent implements OnDestroy {
  readonly busy = input(false);
  readonly maxSeconds = input(60);
  readonly accepted = output<RecordedAudio>();

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
