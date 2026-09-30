import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { ConnectionsManagerComponent } from '../../shared/connections-manager.component';

@Component({
  selector: 'app-ai-settings',
  imports: [ConnectionsManagerComponent, RouterLink],
  template: `
    <main class="page stack">
      <div class="page-header">
        <div>
          <h1>Conexiones de IA</h1>
          <p class="muted">
            Se usan en orden de prioridad (1 = primero). Si una falla o se queda sin cuota, la app
            pasa sola a la siguiente. Las API keys se guardan cifradas y nunca vuelven al navegador.
          </p>
        </div>
      </div>

      @if (isOwner()) {
        <p class="banner banner-info small">
          Las conexiones de la plataforma, sus límites y el consumo se administran en el
          <a routerLink="/app/plataforma">portal de plataforma</a>.
        </p>
      }

      <app-connections-manager scope="account" title="Tus conexiones" />
    </main>
  `
})
export class AiSettingsComponent {
  private readonly auth = inject(AuthService);
  readonly isOwner = computed(() => this.auth.me()?.account.isPlatformOwner ?? false);
}
