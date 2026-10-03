import { Component, Input, OnChanges, OnInit, SimpleChanges, inject, output, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AiSource, PlatformService } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';

const SOURCES: { key: AiSource; label: string }[] = [
  { key: 'BYOK', label: 'Propias keys' },
  { key: 'PLATFORM', label: 'Plataforma' },
  { key: 'HYBRID', label: 'Híbrido' }
];

@Component({
  selector: 'app-services-admin',
  imports: [CollapseCardComponent],
  template: `
    <app-collapse-card
      title="Servicios"
      description="Tipos de servicio definidos por el modelo de negocio."
    >
      <div class="service-types">
        <article>
          <strong>Personal</strong>
          <p class="muted small">Cuenta individual, sin organización asociada.</p>
        </article>
      </div>
      <p class="muted tiny note">
        Corporativa se incorpora con la etapa de empresas. Los servicios no se crean ni editan desde este portal.
      </p>
    </app-collapse-card>

    <app-collapse-card
      title="Membresías"
      description="Definen qué cruces entre Servicio y Fuente de IA están habilitados."
    >
      @if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else {
        <div class="membership-matrix">
          <div class="matrix-head">Servicio</div>
          @for (source of sources; track source.key) {
            <div class="matrix-head">{{ source.label }}</div>
          }

          <div class="service-label">Personal</div>
          @for (source of sources; track source.key) {
            @if (membership(source.key); as item) {
              <div class="membership-cell" [class.inactive]="!item.active">
                <span [class]="item.active ? 'chip chip-ok' : 'chip'">
                  {{ item.active ? 'Habilitada' : 'Deshabilitada' }}
                </span>

                <button
                  class="btn btn-sm"
                  [class.btn-danger]="item.active"
                  type="button"
                  (click)="setActive(item, !item.active)"
                  [disabled]="busyId() === item.id || (item.active && !item.canDisable)"
                  [title]="item.active && !item.canDisable ? disableReason(item) : ''"
                >
                  {{ item.active ? 'Deshabilitar' : 'Habilitar' }}
                </button>

                @if (item.active && !item.canDisable) {
                  <p class="muted tiny blocker">{{ disableReason(item) }}</p>
                }
              </div>
            } @else {
              <div class="membership-cell inactive">
                <span class="muted small">No disponible</span>
              </div>
            }
          }
        </div>
      }
    </app-collapse-card>
  `,
  styles: `
    :host { display: contents; }

    .service-types {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0.75rem;
    }

    .service-types article {
      max-width: 18rem;
      padding: 0.75rem;
      border: 1px solid var(--border);
      border-radius: 0.6rem;
      background: var(--bg);
    }

    .service-types article p { margin: 0.25rem 0 0; }
    .note { margin: 0.8rem 0 0; }
    .tiny { font-size: 0.76rem; }

    .membership-matrix {
      display: grid;
      grid-template-columns: 5.5rem repeat(3, minmax(0, 1fr));
      gap: 0.6rem;
      align-items: stretch;
    }

    .matrix-head {
      padding: 0 0.35rem 0.15rem;
      font-size: 0.82rem;
      color: var(--muted);
      font-weight: 600;
      white-space: nowrap;
    }

    .service-label {
      display: flex;
      align-items: center;
      padding: 0.8rem 0.35rem;
      font-size: 0.95rem;
      font-weight: 600;
    }

    .membership-cell {
      min-width: 0;
      min-height: 8.2rem;
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 0.65rem;
      padding: 0.8rem;
      border: 1px solid var(--border);
      border-radius: 0.6rem;
      background: var(--bg);
      box-sizing: border-box;
    }

    .membership-cell.inactive { opacity: 0.7; }
    .blocker {
      margin: 0;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }

    @media (max-width: 760px) {
      .service-types { grid-template-columns: 1fr; }

      .membership-matrix {
        grid-template-columns: 1fr;
      }

      .matrix-head:first-child,
      .service-label {
        display: none;
      }

      .matrix-head {
        padding-top: 0.35rem;
      }
    }
  `
})
export class ServicesAdminComponent implements OnInit, OnChanges {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  @Input() refreshVersion = 0;
  readonly changed = output<void>();

  readonly sources = SOURCES;
  readonly combinations = signal<PlatformService[]>([]);
  readonly loading = signal(true);
  readonly busyId = signal<number | null>(null);

  membership(source: AiSource): PlatformService | null {
    return this.combinations().find(
      (item) => item.linkType === 'PERSONAL' && item.source === source
    ) ?? null;
  }

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['refreshVersion'] && !changes['refreshVersion'].firstChange) {
      void this.load();
    }
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.combinations.set(await firstValueFrom(this.api.platformServices()));
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  disableReason(item: PlatformService): string {
    const blockers: string[] = [];
    if (item.activeAccounts) blockers.push(`${item.activeAccounts} cuenta(s)`);
    if (item.activeBenefits) blockers.push(`${item.activeBenefits} beneficio(s)`);
    if (item.activeCampaigns) blockers.push(`${item.activeCampaigns} campaña(s)`);
    if (item.activeInvitations) blockers.push(`${item.activeInvitations} invitación(es)`);
    return 'En uso por ' + blockers.join(', ') + ' vigente(s).';
  }

  async setActive(item: PlatformService, active: boolean): Promise<void> {
    if (item.active === active) return;
    this.busyId.set(item.id);
    try {
      await firstValueFrom(this.api.updatePlatformService(item.id, { active }));
      await this.load();
      this.toast.success(active ? 'Membresía habilitada.' : 'Membresía deshabilitada.');
      this.changed.emit();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busyId.set(null);
    }
  }
}
