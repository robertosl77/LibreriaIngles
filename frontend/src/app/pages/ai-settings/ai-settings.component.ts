import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { ActiveAiConnections } from '../../core/models';
import { ConnectionsManagerComponent } from '../../shared/connections-manager.component';
import { MyServiceComponent } from '../../shared/my-service.component';

@Component({
  selector: 'app-ai-settings',
  imports: [ConnectionsManagerComponent, MyServiceComponent, RouterLink],
  template: `
    <main class="page stack">
      <div class="page-header">
        <div>
          <h1>{{ keysUnused() ? 'IA' : 'Conexiones de IA' }}</h1>
          @if (keysUnused()) {
            <p class="muted">
              Tus clases se generan y corrigen con la IA incluida en tu servicio. No tenés que
              configurar nada.
            </p>
          } @else {
            <p class="muted">
              Se usan en orden de prioridad (1 = primero). Si una falla o se queda sin cuota, la app
              pasa sola a la siguiente. Las API keys se guardan cifradas.
              @if (isOwner()) {
                Como dueño de la plataforma, podés copiarlas explícitamente desde el icono junto a cada credencial.
              } @else {
                Una vez guardadas, no vuelven al navegador.
              }
            </p>
          }
        </div>
      </div>

      <app-my-service />

      @if (!keysUnused()) {
        @if (active().default; as current) {
          <p class="banner banner-info small">
            En uso ahora: <strong>{{ current.connection }}</strong>
            @if (current.providerLabel !== current.connection) { · {{ current.providerLabel }} }
            @if (current.model) { · motor <strong>{{ current.model }}</strong> }
            @if (active().audio; as audio) {
              @if (audio.connection !== current.connection || audio.model !== current.model) {
                <br />
                Para audio: <strong>{{ audio.connection }}</strong>
                @if (audio.providerLabel !== audio.connection) { · {{ audio.providerLabel }} }
                @if (audio.model) { · motor <strong>{{ audio.model }}</strong> }
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
      } @else if (ownKeys() > 0) {
        <!-- Plataforma con keys propias ya cargadas: puede verlas, editarlas o borrarlas. -->
        <app-connections-manager
          scope="account"
          title="Tus conexiones guardadas"
          note="No se usan mientras tengas este servicio; cuando venza, vuelven a usarse. Podés editarlas, pausarlas o eliminarlas."
          [allowCreate]="false"
          (changed)="refreshActive()"
        />
      }
    </main>
  `
})
export class AiSettingsComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);

  readonly isOwner = computed(() => this.auth.me()?.account.isPlatformOwner ?? false);
  /** T-055: con un servicio que no usa keys propias (Plataforma) no se ofrece cargarlas. */
  readonly keysUnused = computed(() => this.auth.me()?.service.ownKeys === 'unused');
  readonly ownKeys = computed(() => this.auth.me()?.ai.own ?? 0);
  readonly active = signal<ActiveAiConnections>({ default: null, audio: null });

  async ngOnInit(): Promise<void> {
    await this.refreshActive();
  }

  async refreshActive(): Promise<void> {
    try {
      void this.auth.refreshMe().catch(() => undefined);
      this.active.set(await firstValueFrom(this.api.activeAiConnections()));
    } catch {
      this.active.set({ default: null, audio: null });
    }
  }
}
