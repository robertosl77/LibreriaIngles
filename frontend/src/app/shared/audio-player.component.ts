import { Component, OnDestroy, OnInit, computed, input, signal } from '@angular/core';

/**
 * Listening (T-025): reproduce un texto con la voz sintética del navegador (Web Speech API).
 * No hay archivo de audio: se regenera en cada reproducción (documento funcional §15).
 */
@Component({
  selector: 'app-audio-player',
  template: `
    @if (!supported()) {
      <p class="banner banner-bad small">
        Tu navegador no puede reproducir voz. Probá con Chrome o Edge actualizados.
      </p>
    } @else {
      <div class="player" [class.playing]="playing()">
        <button
          class="play"
          type="button"
          (click)="toggle()"
          [disabled]="!playing() && exhausted()"
          [attr.aria-label]="playing() ? 'Detener audio' : 'Reproducir audio'"
        >
          @if (playing()) {
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="1.5" fill="currentColor"/></svg>
          } @else {
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M8 5.5v13l11-6.5-11-6.5Z" fill="currentColor"/></svg>
          }
        </button>
        <div class="info">
          <span class="label">
            @if (playing()) { Reproduciendo… } @else if (plays() === 0) { Escuchá el audio } @else { Escuchar de nuevo }
          </span>
          @if (maxPlays(); as max) {
            <span class="muted small">
              {{ exhausted() ? 'Ya usaste las ' + max + ' reproducciones' : 'Reproducciones: ' + plays() + ' de ' + max }}
            </span>
          }
        </div>
        <div class="speed" role="group" aria-label="Velocidad">
          <button type="button" [class.on]="slow()" (click)="slow.set(true)">Lento</button>
          <button type="button" [class.on]="!slow()" (click)="slow.set(false)">Normal</button>
        </div>
      </div>
      @if (noEnglishVoice()) {
        <p class="muted small">
          No encontramos una voz en inglés en tu sistema; se usa la voz por defecto. En Windows podés
          agregarla en Configuración → Hora e idioma → Voz.
        </p>
      }
    }
  `,
  styles: `
    :host { display: block; }
    .player {
      display: flex; align-items: center; gap: 0.8rem; flex-wrap: wrap;
      padding: 0.6rem 0.8rem; border: 1px solid #c9d6ff; background: #f3f6ff; border-radius: 0.8rem;
    }
    .play {
      width: 2.6rem; height: 2.6rem; border-radius: 50%; border: 0; flex: none; cursor: pointer;
      display: inline-flex; align-items: center; justify-content: center;
      background: #2f4ab3; color: #fff;
    }
    .play:disabled { background: #9aa7d6; cursor: not-allowed; }
    .play:focus-visible { outline: 2px solid #2f4ab3; outline-offset: 2px; }
    .playing .play { animation: pulse 1.2s ease-in-out infinite; }
    @keyframes pulse { 50% { box-shadow: 0 0 0 6px rgb(47 74 179 / 0.18); } }
    .info { display: flex; flex-direction: column; gap: 0.1rem; flex: 1; min-width: 9rem; }
    .label { font-weight: 600; color: #2f4ab3; }
    .speed { display: inline-flex; border: 1px solid #c9d6ff; border-radius: 999px; overflow: hidden; }
    .speed button { border: 0; background: transparent; padding: 0.3rem 0.7rem; font: inherit; font-size: 0.8rem; cursor: pointer; color: #2f4ab3; }
    .speed button.on { background: #2f4ab3; color: #fff; }
    @media (prefers-reduced-motion: reduce) { .playing .play { animation: none; } }
  `
})
export class AudioPlayerComponent implements OnInit, OnDestroy {
  readonly text = input.required<string>();
  readonly lang = input('en-US');
  readonly rate = input(1);
  /** En el examen se limita la cantidad de reproducciones (null = sin límite). */
  readonly maxPlays = input<number | null>(null);

  readonly supported = signal(typeof window !== 'undefined' && 'speechSynthesis' in window);
  readonly playing = signal(false);
  readonly plays = signal(0);
  readonly slow = signal(false);
  readonly noEnglishVoice = signal(false);
  readonly exhausted = computed(() => {
    const max = this.maxPlays();
    return max !== null && this.plays() >= max;
  });

  private voice: SpeechSynthesisVoice | null = null;
  private readonly onVoices = () => this.pickVoice();

  ngOnInit(): void {
    if (!this.supported()) {
      return;
    }
    this.pickVoice();
    speechSynthesis.addEventListener('voiceschanged', this.onVoices);
  }

  ngOnDestroy(): void {
    if (!this.supported()) {
      return;
    }
    speechSynthesis.removeEventListener('voiceschanged', this.onVoices);
    if (this.playing()) {
      speechSynthesis.cancel();
    }
  }

  /** Prefiere voces "naturales"/online del idioma pedido; si no, cualquier voz en inglés. */
  private pickVoice(): void {
    const voices = speechSynthesis.getVoices();
    if (!voices.length) {
      return;
    }
    const lang = this.lang().toLowerCase();
    const exact = voices.filter((v) => v.lang.toLowerCase().replace('_', '-') === lang);
    const english = voices.filter((v) => v.lang.toLowerCase().startsWith('en'));
    const pool = exact.length ? exact : english;
    const natural = pool.find((v) => /natural|online|google/i.test(v.name));
    this.voice = natural ?? pool[0] ?? null;
    this.noEnglishVoice.set(pool.length === 0);
  }

  toggle(): void {
    if (this.playing()) {
      speechSynthesis.cancel();
      this.playing.set(false);
      return;
    }
    if (this.exhausted()) {
      return;
    }
    // Otro reproductor sonando en la página se corta.
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(this.text());
    utterance.lang = this.voice?.lang ?? this.lang();
    if (this.voice) {
      utterance.voice = this.voice;
    }
    const base = this.rate() || 1;
    utterance.rate = this.slow() ? Math.max(0.5, base * 0.75) : base;
    utterance.onend = () => this.playing.set(false);
    utterance.onerror = () => this.playing.set(false);
    this.plays.update((n) => n + 1);
    this.playing.set(true);
    speechSynthesis.speak(utterance);
  }
}
