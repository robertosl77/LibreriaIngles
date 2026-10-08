import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { ActiveAiConnections } from '../../core/models';
import { ConnectionsManagerComponent } from '../../shared/connections-manager.component';
import { MyServiceComponent } from '../../shared/my-service.component';

@Component({
  selector: 'app-ai-settings',
  imports: [ConnectionsManagerComponent, MyServiceComponent],
  template: `
    <main class="page stack">
      <div class="page-header">
        <div>
          @if (isOwner()) {
            <h1>IA de la plataforma</h1>
            <p class="muted">
              Estas conexiones las usás vos (clases, asistente de campañas) y las heredan todos los que
              tienen un servicio con la IA de la plataforma. Se usan en orden de prioridad (1 = primero):
              si una falla o se queda sin cuota, la app pasa sola a la siguiente. Las API keys se guardan
              cifradas; podés copiarlas explícitamente desde el icono junto a cada credencial.
            </p>
          } @else if (keysUnused()) {
            <h1>IA</h1>
            <p class="muted">
              @if (corporate()) {
                Tu organización administra la IA de tus clases. No tenés que configurar nada.
              } @else {
                Tus clases se generan y corrigen con la IA de la plataforma incluida en tu servicio.
                No tenés que configurar nada.
              }
            </p>
          } @else {
            <h1>Conexiones de IA</h1>
            <p class="muted">
              Se usan en orden de prioridad (1 = primero). Si una falla o se queda sin cuota, la app
              pasa sola a la siguiente. Las API keys se guardan cifradas. Una vez guardadas, no vuelven
              al navegador.
            </p>
          }
        </div>
      </div>

      <app-my-service />

      @if (isOwner() || !keysUnused()) {
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

        @if (hybrid()) {
          <p class="banner banner-info small">
            Si tus conexiones no están disponibles, tus clases usan la IA
            {{ corporate() ? 'que administra tu organización' : 'de la plataforma incluida en tu servicio' }}.
          </p>
        }

        @if (isOwner()) {
          <!-- T-217: tope por persona sumando todas las conexiones (cambiar de conexión no lo reinicia). -->
          <section class="card stack">
            <h2>Límite diario por persona</h2>
            <p class="muted small">
              Pedidos a la IA por persona en 24 h, sumando todas las conexiones de la plataforma. Vos no
              tenés tope. Vacío = sin tope.
            </p>
            <div class="row">
              <input type="number" min="1" placeholder="Sin tope" [value]="personCap() ?? ''"
                     (input)="capDraft = $any($event.target).value" aria-label="Pedidos por persona por día" />
              <button type="button" class="button" [disabled]="savingCap()" (click)="saveCap()">Guardar</button>
              @if (capMessage()) { <span class="small muted">{{ capMessage() }}</span> }
            </div>
          </section>

          <!-- T-200: una sola lista para sr.macros, la de la plataforma (la usa él y la heredan todos). -->
          <app-connections-manager
            scope="platform"
            title="Conexiones de la plataforma"
            [focusConnectionId]="focusedConnectionId"
            [activeId]="active().default?.connectionId ?? null"
            [audioId]="active().audio?.connectionId ?? null"
            (changed)="refreshActive()"
          />
        } @else {
          <app-connections-manager
            scope="account"
            title="Tus conexiones"
            [focusConnectionId]="focusedConnectionId"
            [activeId]="active().default?.connectionId ?? null"
            [audioId]="active().audio?.connectionId ?? null"
            (changed)="refreshActive()"
          />
        }
      } @else if (ownKeys() > 0) {
        <!-- Plataforma con keys propias ya cargadas: puede verlas, editarlas o borrarlas. -->
        <app-connections-manager
          scope="account"
          title="Tus conexiones guardadas"
          note="No se usan mientras tengas este servicio; cuando venza, vuelven a usarse. Podés editarlas, pausarlas o eliminarlas."
          [allowCreate]="false"
          [focusConnectionId]="focusedConnectionId"
          (changed)="refreshActive()"
        />
      }
    </main>
  `
})
export class AiSettingsComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  readonly focusedConnectionId = this.connectionIdFromQuery();

  readonly isOwner = computed(() => this.auth.me()?.account.isPlatformOwner ?? false);
  /** T-055: con un servicio que no usa keys propias (Plataforma) no se ofrece cargarlas. */
  readonly keysUnused = computed(() => this.auth.me()?.service.ownKeys === 'unused');
  readonly ownKeys = computed(() => this.auth.me()?.ai.own ?? 0);
  /** T-200: el empleado no ve de dónde viene la IA en detalle: la administra su organización. */
  readonly corporate = computed(() => this.auth.me()?.service.linkType === 'CORPORATE');
  readonly hybrid = computed(() => {
    const service = this.auth.me()?.service;
    return !this.isOwner() && !!service?.usesOwnKeys && !!service?.usesPlatform;
  });
  readonly active = signal<ActiveAiConnections>({ default: null, audio: null });

  readonly personCap = signal<number | null>(null);
  readonly savingCap = signal(false);
  readonly capMessage = signal('');
  capDraft = '';

  async saveCap(): Promise<void> {
    const raw = this.capDraft.trim();
    const value = raw === '' ? null : Number(raw);
    if (value !== null && (!Number.isInteger(value) || value < 1)) {
      this.capMessage.set('Tiene que ser un número entero, 1 o más.');
      return;
    }
    this.savingCap.set(true);
    try {
      const saved = await firstValueFrom(this.api.setAiLimits(value));
      this.personCap.set(saved.personDailyRequests);
      this.capMessage.set('Guardado.');
    } catch {
      this.capMessage.set('No se pudo guardar.');
    } finally {
      this.savingCap.set(false);
    }
  }

  private connectionIdFromQuery(): number | null {
    const value = Number(this.route.snapshot.queryParamMap.get('connectionId'));
    return Number.isInteger(value) && value > 0 ? value : null;
  }

  async ngOnInit(): Promise<void> {
    await this.refreshActive();
    if (this.isOwner()) {
      try {
        const limits = await firstValueFrom(this.api.aiLimits());
        this.personCap.set(limits.personDailyRequests);
        this.capDraft = limits.personDailyRequests?.toString() ?? '';
      } catch { /* sin datos: queda vacío */ }
    }
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
