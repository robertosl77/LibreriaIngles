import { Component, OnDestroy, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

interface SpeechAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionResultLike {
  readonly length: number;
  [index: number]: SpeechAlternative;
}

interface SpeechRecognitionEventLike {
  results: {
    readonly length: number;
    [index: number]: SpeechRecognitionResultLike;
  };
}

interface SpeechRecognitionErrorLike {
  error: string;
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorLike) => void) | null;
  onend: (() => void) | null;
  start(): void;
  abort(): void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

/**
 * Práctica orientativa de pronunciación, sin guardar audio ni consumir conexiones de IA.
 * Usa reconocimiento de voz del navegador como señal de inteligibilidad, no como evaluación final.
 */
@Component({
  selector: 'app-pronunciation-practice',
  imports: [FormsModule],
  template: `
    <section class="practice" aria-label="Práctica de fonética">
      <header>
        <p class="eyebrow">Práctica · Fonética</p>
        <h3>Pronunciación</h3>
      </header>

      <p>
        Escribí lo que querés decir y practicá cómo suena. Esta práctica no decide si tu
        respuesta al ejercicio es correcta.
      </p>

      <label class="target-label" for="pronunciation-target">Lo que quiero decir</label>
      <input
        id="pronunciation-target"
        class="input"
        type="text"
        autocomplete="off"
        spellcheck="false"
        [(ngModel)]="target"
        (ngModelChange)="resetScore()"
        placeholder="Ej.: I don't know the answer"
      />

      <div class="actions">
        <button class="btn btn-sm" type="button" (click)="playModel()" [disabled]="!target.trim() || listening()">
          ▶ Escuchar modelo
        </button>
        <button class="btn btn-primary btn-sm" type="button" (click)="practice()" [disabled]="!target.trim() || listening()">
          @if (listening()) {
            <span class="listening-dot" aria-hidden="true"></span>
            Escuchando…
          } @else {
            🎙 Practicar ahora
          }
        </button>
      </div>

      @if (error()) {
        <p class="error small">{{ error() }}</p>
      }

      @if (score() !== null) {
        <div class="result">
          <div class="result-head">
            <strong>{{ score() }}%</strong>
            <span>{{ scoreLabel() }}</span>
          </div>
          <div class="meter" role="meter" aria-label="Resultado orientativo de pronunciación" aria-valuemin="0" aria-valuemax="100" [attr.aria-valuenow]="score()">
            <span class="marker" [style.left.%]="score()"></span>
          </div>
          <p class="muted small">
            Resultado orientativo · intento {{ attempts() }}. Podés repetir todas las veces que quieras.
          </p>
        </div>
      }

      <footer>
        <span class="muted small">No se guarda audio ni cuenta como respuesta.</span>
        <button class="btn btn-sm" type="button" (click)="closed.emit()">Entendido, volver al ejercicio</button>
      </footer>
    </section>
  `,
  styles: `
    .practice {
      display: flex; flex-direction: column; gap: 0.65rem;
      background: #f3f6ff; border: 1px solid #c9d6ff; border-radius: 0.6rem; padding: 0.9rem 1rem;
    }
    .practice p, .practice h3 { margin: 0; }
    .eyebrow {
      font-size: 0.75rem; font-weight: 600; letter-spacing: 0.04em;
      text-transform: uppercase; color: #2f4ab3;
    }
    .practice h3 { font-size: 1.05rem; }
    .target-label { font-size: 0.85rem; font-weight: 600; }
    .actions { display: flex; gap: 0.55rem; align-items: center; flex-wrap: wrap; }
    .listening-dot {
      display: inline-block; width: 0.65rem; height: 0.65rem; margin-right: 0.25rem;
      border-radius: 50%; background: currentColor; animation: pulse 0.8s ease-in-out infinite alternate;
    }
    .result { display: flex; flex-direction: column; gap: 0.45rem; padding-top: 0.15rem; }
    .result-head { display: flex; align-items: baseline; gap: 0.65rem; }
    .result-head strong { font-size: 1.35rem; }
    .meter {
      position: relative; height: 0.8rem; border-radius: 999px;
      background: linear-gradient(90deg, #d93025 0%, #f2b01e 52%, #1a9b55 100%);
      box-shadow: inset 0 0 0 1px rgb(0 0 0 / 0.08);
    }
    .marker {
      position: absolute; top: 50%; width: 1rem; height: 1rem; border-radius: 50%;
      background: #fff; border: 3px solid #263238; transform: translate(-50%, -50%);
      box-shadow: 0 1px 4px rgb(0 0 0 / 0.24);
    }
    .error { color: var(--bad); }
    footer { display: flex; gap: 0.8rem; align-items: center; justify-content: space-between; flex-wrap: wrap; }
    footer .btn { margin-left: auto; }
    @keyframes pulse { from { opacity: 0.45; transform: scale(0.85); } to { opacity: 1; transform: scale(1.1); } }
  `
})
export class PronunciationPracticeComponent implements OnDestroy {
  readonly closed = output<void>();

  target = '';
  readonly listening = signal(false);
  readonly score = signal<number | null>(null);
  readonly attempts = signal(0);
  readonly error = signal<string | null>(null);

  private recognition: SpeechRecognitionLike | null = null;

  practice(): void {
    const phrase = this.target.trim();
    if (!phrase || this.listening()) {
      return;
    }

    const w = window as SpeechWindow;
    const Recognition = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Recognition) {
      this.error.set('Este navegador no ofrece reconocimiento de voz para esta práctica.');
      return;
    }

    this.error.set(null);
    this.score.set(null);
    this.recognition?.abort();

    const recognition = new Recognition();
    this.recognition = recognition;
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      const alternative = event.results[0]?.[0];
      if (!alternative) {
        this.error.set('No pude reconocer lo que dijiste. Probá otra vez.');
        return;
      }
      const value = this.pronunciationScore(phrase, alternative.transcript, alternative.confidence);
      this.score.set(value);
      this.attempts.update((count) => count + 1);
    };

    recognition.onerror = (event) => {
      if (event.error === 'aborted') {
        return;
      }
      const message =
        event.error === 'not-allowed'
          ? 'Necesito permiso para usar el micrófono.'
          : event.error === 'no-speech'
            ? 'No detecté voz. Probá acercarte al micrófono.'
            : 'No pude analizar esta práctica. Probá de nuevo.';
      this.error.set(message);
    };

    recognition.onend = () => {
      this.listening.set(false);
      if (this.recognition === recognition) {
        this.recognition = null;
      }
    };

    this.listening.set(true);
    try {
      recognition.start();
    } catch {
      this.listening.set(false);
      this.recognition = null;
      this.error.set('No pude iniciar el micrófono. Probá de nuevo.');
    }
  }

  playModel(): void {
    const phrase = this.target.trim();
    if (!phrase || !('speechSynthesis' in window)) {
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(phrase);
    utterance.lang = 'en-US';
    utterance.rate = 0.9;
    window.speechSynthesis.speak(utterance);
  }

  resetScore(): void {
    this.score.set(null);
    this.error.set(null);
  }

  scoreLabel(): string {
    const value = this.score();
    if (value === null) {
      return '';
    }
    if (value >= 80) {
      return 'Muy bien';
    }
    if (value >= 65) {
      return 'Bien, podés pulirlo un poco más';
    }
    if (value >= 45) {
      return 'Se entiende, pero conviene practicar';
    }
    return 'Probá otra vez más despacio';
  }

  ngOnDestroy(): void {
    this.recognition?.abort();
    window.speechSynthesis?.cancel();
  }

  private pronunciationScore(expected: string, heard: string, confidence: number): number {
    const expectedWords = this.normalize(expected).split(' ').filter(Boolean);
    const heardWords = this.normalize(heard).split(' ').filter(Boolean);
    const maxLength = Math.max(expectedWords.length, heardWords.length, 1);
    const similarity = 1 - this.wordDistance(expectedWords, heardWords) / maxLength;
    const safeSimilarity = Math.max(0, Math.min(1, similarity));
    const safeConfidence =
      Number.isFinite(confidence) && confidence > 0 ? Math.max(0, Math.min(1, confidence)) : safeSimilarity;

    // Es un indicador de práctica: combina cuánto entendió el navegador con su confianza.
    return Math.round((safeSimilarity * 0.75 + safeConfidence * 0.25) * 100);
  }

  private normalize(value: string): string {
    return value
      .toLowerCase()
      .replace(/[^a-z0-9' ]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  private wordDistance(a: string[], b: string[]): number {
    const rows = a.length + 1;
    const cols = b.length + 1;
    const matrix = Array.from({ length: rows }, () => Array<number>(cols).fill(0));

    for (let i = 0; i < rows; i += 1) matrix[i][0] = i;
    for (let j = 0; j < cols; j += 1) matrix[0][j] = j;

    for (let i = 1; i < rows; i += 1) {
      for (let j = 1; j < cols; j += 1) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        matrix[i][j] = Math.min(
          matrix[i - 1][j] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j - 1] + cost
        );
      }
    }
    return matrix[rows - 1][cols - 1];
  }
}
