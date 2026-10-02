import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-platform',
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  template: `
    <main class="page stack platform-page">
      <header class="platform-header">
        <div>
          <h1>Plataforma</h1>
          <p class="muted">Monitoreo y administración de la IA provista por Librería Inglés.</p>
        </div>

        <nav class="platform-tabs" aria-label="Secciones de plataforma">
          <a
            routerLink="resumen"
            routerLinkActive="active"
            [routerLinkActiveOptions]="{ exact: true }"
          >
            Resumen
          </a>
          <a
            routerLink="configuracion"
            routerLinkActive="active"
            [routerLinkActiveOptions]="{ exact: true }"
          >
            Configuración
          </a>
        </nav>
      </header>

      <router-outlet />
    </main>
  `,
  styles: `
    .platform-page { gap: 1.2rem; }

    .platform-header {
      display: flex;
      flex-direction: column;
      gap: 0.9rem;
    }

    .platform-header h1,
    .platform-header p {
      margin: 0;
    }

    .platform-header p {
      margin-top: 0.3rem;
      max-width: 46rem;
    }

    .platform-tabs {
      display: flex;
      gap: 0.2rem;
      border-bottom: 1px solid var(--border);
    }

    .platform-tabs a {
      position: relative;
      padding: 0.55rem 0.85rem 0.65rem;
      color: var(--muted);
      font-weight: 650;
      text-decoration: none;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      transition: color 0.15s ease, border-color 0.15s ease;
    }

    .platform-tabs a:hover {
      color: inherit;
    }

    .platform-tabs a.active {
      color: inherit;
      border-bottom-color: var(--accent);
    }

    @media (max-width: 560px) {
      .platform-tabs {
        overflow-x: auto;
      }

      .platform-tabs a {
        white-space: nowrap;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      .platform-tabs a { transition: none; }
    }
  `
})
export class PlatformComponent {}
