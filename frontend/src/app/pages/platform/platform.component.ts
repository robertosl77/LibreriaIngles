import { Component, OnDestroy, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { Subscription, filter } from 'rxjs';

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
          <p class="muted">{{ description() }}</p>
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
      max-width: 52rem;
    }
  `
})
export class PlatformComponent implements OnDestroy {
  private readonly router = inject(Router);
  private readonly routeSubscription: Subscription;

  readonly tabs = PLATFORM_TABS;
  readonly description = signal(this.descriptionFor(this.router.url));

  constructor() {
    this.routeSubscription = this.router.events
      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe((event) => this.description.set(this.descriptionFor(event.urlAfterRedirects)));
  }

  ngOnDestroy(): void {
    this.routeSubscription.unsubscribe();
  }

  private descriptionFor(url: string): string {
    return url.includes('/configuracion')
      ? 'Configuración de fuentes, servicios, beneficios, cuentas, campañas, invitaciones y conexiones.'
      : 'Información general, estadísticas y estado actual de la plataforma.';
  }
}
