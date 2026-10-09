import { DatePipe, DecimalPipe, KeyValuePipe } from '@angular/common';
import { Component, effect, inject, input, signal, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { Certificate } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { BrandService } from '../../core/brand.service';

/**
 * Certificado de nivel (T-024). Página pública de verificación y a la vez el documento:
 * plantilla fija (sin IA), se regenera idéntica desde los datos guardados.
 * "Descargar PDF" usa la impresión del navegador con estilos de impresión A4 horizontal.
 */
@Component({
  selector: 'app-certificate',
  imports: [DatePipe, DecimalPipe, KeyValuePipe, RouterLink],
  template: `
    <main class="wrap">
      @if (loading()) {
        <p class="muted"><span class="spinner"></span> Cargando certificado…</p>
      }
      @if (!loading() && cert(); as c) {
        <div class="actions no-print">
          @if (auth.isLoggedIn()) {
            <a class="btn btn-sm" routerLink="/app">← Volver</a>
          }
          <span class="verified">✓ Certificado verificado · {{ c.code }}</span>
          <button class="btn btn-sm" type="button" (click)="copyLink()">Copiar enlace</button>
          <button class="btn btn-sm btn-primary" type="button" (click)="print()">Descargar PDF</button>
        </div>

        <article class="sheet" aria-label="Certificado">
          <div class="frame">
            <header>
              <p class="brand">{{ brand.name() }}</p>
              <h1>Certificado de nivel</h1>
              <p class="lead">Se certifica que</p>
            </header>

            <p class="holder">{{ c.holderName }}</p>

            <p class="lead">
              aprobó el examen de nivel <strong>{{ c.level }}</strong>
              @if (c.levelName) { <span>&nbsp;({{ c.levelName }})</span> }
              con un resultado de <strong>{{ c.score | number: '1.0-1' }}%</strong>.
            </p>

            <ul class="areas">
              @for (area of c.areaScores | keyvalue: keepOrder; track area.key) {
                <li><span>{{ area.key }}</span><strong>{{ area.value | number: '1.0-0' }}%</strong></li>
              }
            </ul>

            <footer>
              <div class="meta">
                <span class="label">Fecha de emisión</span>
                <span>{{ c.issuedAt | date: 'dd/MM/yyyy' }}</span>
              </div>
              <div class="seal" aria-hidden="true"><span>{{ c.level }}</span></div>
              <div class="meta right">
                <span class="label">Código de verificación</span>
                <span class="code">{{ c.code }}</span>
                <span class="url">{{ verifyUrl() }}</span>
              </div>
            </footer>

            <p class="notice">{{ c.notice }}</p>
          </div>
        </article>
      }
      @if (!loading() && !cert()) {
        <section class="card missing">
          <h1>Certificado no encontrado</h1>
          <p class="muted">El código <strong>{{ code() }}</strong> no corresponde a ningún certificado emitido por {{ brand.name() }}.</p>
        </section>
      }
    </main>
  `,
  styles: `
    :host { display: block; min-height: 100vh; background: var(--bg); }
    .wrap { max-width: 1060px; margin: 0 auto; padding: 1.5rem 1rem 3rem; display: flex; flex-direction: column; gap: 1rem; }
    .actions { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
    .verified { margin-right: auto; color: var(--ok); font-weight: 600; font-size: 0.9rem; }
    .missing { max-width: 560px; margin: 4rem auto; }

    .sheet {
      aspect-ratio: 297 / 210; width: 100%;
      background: #fffdf8; color: #1d1a14;
      box-shadow: 0 10px 40px rgb(0 0 0 / 0.12);
      padding: 2.2%;
      font-family: Georgia, 'Times New Roman', serif;
    }
    .frame {
      height: 100%; box-sizing: border-box;
      border: 2px solid #b8943c; outline: 1px solid #b8943c; outline-offset: -8px;
      padding: 4% 7%;
      display: flex; flex-direction: column; align-items: center; justify-content: space-between; text-align: center;
    }
    header { display: flex; flex-direction: column; align-items: center; gap: 0.4rem; }
    .brand { margin: 0; letter-spacing: 0.3em; text-transform: uppercase; font-size: clamp(0.65rem, 1.2vw, 0.85rem); color: #8a6a1f; }
    h1 { margin: 0; font-size: clamp(1.4rem, 4vw, 2.6rem); font-weight: 400; letter-spacing: 0.02em; }
    .lead { margin: 0; font-size: clamp(0.8rem, 1.6vw, 1.1rem); }
    .holder {
      margin: 0; font-size: clamp(1.4rem, 4.2vw, 2.8rem); font-style: italic;
      padding: 0 2rem 0.3rem; border-bottom: 1px solid #b8943c; min-width: 55%;
    }
    .areas {
      list-style: none; margin: 0; padding: 0;
      display: flex; gap: clamp(0.6rem, 2.5vw, 2rem); flex-wrap: wrap; justify-content: center;
      font-size: clamp(0.7rem, 1.3vw, 0.95rem);
    }
    .areas li { display: flex; flex-direction: column; gap: 0.1rem; }
    .areas span { color: #6b5d3f; }
    footer { width: 100%; display: grid; grid-template-columns: 1fr auto 1fr; align-items: end; gap: 1rem; }
    .meta { display: flex; flex-direction: column; gap: 0.15rem; text-align: left; font-size: clamp(0.65rem, 1.2vw, 0.9rem); }
    .meta.right { text-align: right; }
    .label { color: #6b5d3f; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.08em; }
    .code { font-family: ui-monospace, monospace; font-weight: 700; }
    .url { font-family: ui-monospace, monospace; font-size: 0.8em; color: #6b5d3f; word-break: break-all; }
    .seal {
      width: clamp(3.5rem, 9vw, 6rem); aspect-ratio: 1; border-radius: 50%;
      background: radial-gradient(circle at 35% 30%, #f3dc9c, #c9a347 60%, #a8822c);
      display: flex; align-items: center; justify-content: center;
      box-shadow: inset 0 0 0 4px rgb(255 255 255 / 0.35);
    }
    .seal span { font-weight: 700; color: #4d3a0e; font-size: clamp(1rem, 2.4vw, 1.6rem); font-family: Georgia, serif; }
    .notice { margin: 0; font-size: clamp(0.55rem, 0.95vw, 0.72rem); color: #6b5d3f; max-width: 85%; font-family: system-ui, sans-serif; }

    @media (max-width: 640px) {
      .sheet { aspect-ratio: auto; }
      .frame { gap: 1.1rem; padding: 7% 6%; }
      footer { grid-template-columns: 1fr; justify-items: center; }
      .meta, .meta.right { text-align: center; }
    }
        @page { size: A4 landscape; margin: 0; }
    @media print {
      :host { background: #fff; min-height: 0; }
      .no-print { display: none !important; }
      .wrap { padding: 0; max-width: none; }
      .sheet { box-shadow: none; width: 297mm; height: 210mm; aspect-ratio: auto; padding: 6mm; }
      .brand { font-size: 10pt; } h1 { font-size: 30pt; } .lead { font-size: 13pt; }
      .holder { font-size: 32pt; } .areas { font-size: 11pt; gap: 10mm; }
      .meta { font-size: 10pt; } .seal { width: 26mm; } .seal span { font-size: 18pt; }
      .notice { font-size: 7.5pt; }
    }
  `
})
export class CertificateComponent {
  readonly brand = inject(BrandService);
  readonly code = input.required<string>();

  readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  readonly cert = signal<Certificate | null>(null);
  readonly loading = signal(true);

  /** Mantener el orden de áreas tal como se guardó. */
  readonly keepOrder = (): number => 0;

  constructor() {
    effect(() => {
      const code = this.code();
      untracked(() => void this.load(code));
    });
  }

  private async load(code: string): Promise<void> {
    this.loading.set(true);
    try {
      this.cert.set(await firstValueFrom(this.api.certificate(code)));
    } catch {
      this.cert.set(null);
    } finally {
      this.loading.set(false);
    }
  }

  verifyUrl(): string {
    return `${location.origin}/certificado/${this.cert()?.code ?? this.code()}`;
  }

  print(): void {
    const previous = document.title;
    document.title = `Certificado ${this.cert()?.level} - ${this.cert()?.holderName}`;
    window.print();
    document.title = previous;
  }

  async copyLink(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.verifyUrl());
      this.toast.success('Enlace de verificación copiado.');
    } catch {
      this.toast.show(this.verifyUrl());
    }
  }
}
