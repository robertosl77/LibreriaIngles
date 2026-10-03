import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { TabNavComponent, TabNavItem } from '../../shared/ui/tab-nav.component';

const PLATFORM_TABS: TabNavItem[] = [
  { label: 'Resumen', route: 'resumen' },
  { label: 'Configuración', route: 'configuracion' }
];

@Component({
  selector: 'app-platform',
  imports: [RouterOutlet, TabNavComponent],
  template: `
    <main class="page stack platform-page">
      <header class="platform-header">
        <div>
          <h1>Plataforma</h1>
          <p class="muted">Monitoreo y administración de la IA provista por Librería Inglés.</p>
        </div>

        <app-tab-nav [items]="tabs" ariaLabel="Secciones de plataforma" />
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
  `
})
export class PlatformComponent {
  readonly tabs = PLATFORM_TABS;
}
