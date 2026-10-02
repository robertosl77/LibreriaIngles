import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-platform',
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  template: `
    <main class="page stack">
      <div class="page-header">
        <div>
          <h1>Plataforma</h1>
          <p class="muted">
            Área exclusiva del dueño de Librería Inglés. Separá el monitoreo operativo de la
            configuración para administrar la plataforma sin mezclar responsabilidades.
          </p>
        </div>
      </div>

      <nav class="platform-tabs" aria-label="Secciones de plataforma">
        <a
          routerLink="resumen"
          routerLinkActive="active"
          [routerLinkActiveOptions]="{ exact: true }"
        >
          Resumen
          <span class="muted small">Uso, actividad y salud</span>
        </a>
        <a
          routerLink="configuracion"
          routerLinkActive="active"
          [routerLinkActiveOptions]="{ exact: true }"
        >
          Configuración
          <span class="muted small">Servicios, beneficios y motores</span>
        </a>
      </nav>

      <router-outlet />
    </main>
  `,
  styles: `
    .platform-tabs {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 0.6rem;
      padding: 0.35rem;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--card);
    }

    .platform-tabs a {
      display: flex;
      flex-direction: column;
      gap: 0.12rem;
      padding: 0.75rem 0.9rem;
      border-radius: calc(var(--radius) - 0.2rem);
      color: inherit;
      text-decoration: none;
      transition: background 0.15s ease, box-shadow 0.15s ease;
    }

    .platform-tabs a:hover {
      background: var(--bg);
    }

    .platform-tabs a.active {
      background: var(--bg);
      box-shadow: inset 0 0 0 1px var(--border);
      font-weight: 700;
    }

    .platform-tabs a.active .muted {
      font-weight: 400;
    }

    @media (max-width: 640px) {
      .platform-tabs { grid-template-columns: 1fr; }
    }

    @media (prefers-reduced-motion: reduce) {
      .platform-tabs a { transition: none; }
    }
  `
})
export class PlatformComponent {}
