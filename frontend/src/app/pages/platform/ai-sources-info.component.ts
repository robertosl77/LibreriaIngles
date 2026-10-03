import { Component } from '@angular/core';

import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';

@Component({
  selector: 'app-ai-sources-info',
  imports: [CollapseCardComponent],
  template: `
    <app-collapse-card
      title="Fuentes de IA"
      description="Modalidades disponibles para definir de dónde obtiene IA cada servicio."
    >
      <div class="sources">
        <article>
          <strong>Propias keys (BYOK)</strong>
          <p class="muted small">La persona usa sus propias conexiones y credenciales de IA.</p>
        </article>
        <article>
          <strong>Plataforma</strong>
          <p class="muted small">La persona usa las conexiones de IA administradas por Librería Inglés.</p>
        </article>
        <article>
          <strong>Híbrido</strong>
          <p class="muted small">Hoy usa las conexiones propias primero y recurre a Plataforma cuando corresponde.</p>
        </article>
      </div>
      <p class="muted tiny note">
        Hoy estas tres fuentes son fijas. La estrategia futura de Híbrido podrá evolucionar sin
        redefinir los Servicios.
      </p>
    </app-collapse-card>
  `,
  styles: `
    .sources {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0.75rem;
    }

    article {
      padding: 0.75rem;
      border: 1px solid var(--border);
      border-radius: 0.6rem;
      background: var(--bg);
    }

    article p { margin: 0.25rem 0 0; }
    .note { margin: 0.8rem 0 0; }
    .tiny { font-size: 0.76rem; }

    @media (max-width: 760px) {
      .sources { grid-template-columns: 1fr; }
    }
  `
})
export class AiSourcesInfoComponent {}
