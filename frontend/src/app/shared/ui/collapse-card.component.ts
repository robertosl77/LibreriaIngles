import { Component, input } from '@angular/core';

/**
 * Tarjeta colapsable estándar de Librería Inglés.
 *
 * Extraída del patrón <details>/<summary> usado originalmente en Progreso.
 * Este componente es la única fuente de verdad visual/funcional para collapses
 * reutilizables. Para una cabecera simple usar title/description; para una
 * cabecera rica proyectar un nodo con el atributo collapse-header.
 */
@Component({
  selector: 'app-collapse-card',
  template: `
    <details class="card ui-collapse" [open]="open()">
      <summary>
        @if (title()) {
          <div class="default-heading">
            <strong class="collapse-title">{{ title() }}</strong>
            @if (description()) {
              <span class="muted small collapse-description">{{ description() }}</span>
            }
          </div>
        } @else {
          <div class="custom-heading">
            <ng-content select="[collapse-header]" />
          </div>
        }
        <span class="chevron" aria-hidden="true"></span>
      </summary>

      <div class="collapse-body">
        <ng-content />
      </div>
    </details>
  `,
  styles: `
    :host { display: contents; }

    .ui-collapse { padding: 0; overflow: clip; }

    summary {
      list-style: none;
      cursor: pointer;
      padding: 0.9rem 1.1rem;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 0.8rem;
      align-items: center;
    }

    summary::-webkit-details-marker { display: none; }

    summary:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: -2px;
      border-radius: var(--radius);
    }

    .default-heading {
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 0.18rem;
    }

    .collapse-title {
      font-size: 1.05rem;
      line-height: 1.25;
    }

    .collapse-description {
      line-height: 1.35;
    }

    .custom-heading { min-width: 0; }

    .chevron {
      width: 0.55rem;
      height: 0.55rem;
      border-right: 2px solid var(--muted);
      border-bottom: 2px solid var(--muted);
      transform: rotate(45deg);
      transition: transform 0.15s ease;
      margin: 0 0.2rem 0.2rem;
      flex: none;
    }

    .ui-collapse[open] .chevron {
      transform: rotate(-135deg);
      margin-bottom: -0.2rem;
    }

    .collapse-body {
      padding: 0.8rem 1.1rem 1rem;
      border-top: 1px solid var(--border);
    }

    @media (max-width: 560px) {
      summary {
        padding: 0.8rem 0.9rem;
        gap: 0.55rem;
      }

      .collapse-body { padding: 0.75rem 0.9rem 0.9rem; }
    }

    @media (prefers-reduced-motion: reduce) {
      .chevron { transition: none; }
    }
  `
})
export class CollapseCardComponent {
  readonly title = input('');
  readonly description = input('');
  readonly open = input(false);
}
