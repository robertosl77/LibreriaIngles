import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { ActiveAiConnections } from '../../core/models';
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

      @if (active().default; as current) {
        <p class="banner banner-info small">
          En uso ahora: <strong>{{ current.connection }}</strong> ·
          {{ current.providerLabel }} · motor <strong>{{ current.model }}</strong>
          @if (active().audio; as audio) {
            @if (audio.connectionId !== current.connectionId) {
              <br />
              Para audio: <strong>{{ audio.connection }}</strong> ·
              {{ audio.providerLabel }} · motor <strong>{{ audio.model }}</strong>
            }
          }
        </p>
      } @else {
        <p class="banner banner-info small">
          No hay una conexión de IA disponible en este momento.
        </p>
      }

      @if (isOwner()) {
        <p class="banner banner-info small">
          Las conexiones de la plataforma, sus límites y el consumo se administran en el
          <a routerLink="/app/plataforma">portal de plataforma</a>.
        </p>
      }

      <app-connections-manager
        scope="account"
        title="Tus conexiones"
        (changed)="refreshActive()"
      />
    </main>
  `
})
export class AiSettingsComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);

  readonly isOwner = computed(() => this.auth.me()?.account.isPlatformOwner ?? false);
  readonly active = signal<ActiveAiConnections>({ default: null, audio: null });

  async ngOnInit(): Promise<void> {
    await this.refreshActive();
  }

  async refreshActive(): Promise<void> {
    try {
      this.active.set(await firstValueFrom(this.api.activeAiConnections()));
    } catch {
      this.active.set({ default: null, audio: null });
    }
  }
}
