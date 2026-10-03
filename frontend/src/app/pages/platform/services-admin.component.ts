import { Component, Input, OnChanges, OnInit, SimpleChanges, inject, output, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AiSource, LinkType, PlatformService } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { ActiveToggleComponent } from '../../shared/ui/active-toggle.component';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';

const SOURCE_SHORT: Record<AiSource, string> = {
  BYOK: 'Propias keys (BYOK)',
  PLATFORM: 'Plataforma',
  HYBRID: 'Híbrido'
};

const LINK_SHORT: Record<LinkType, string> = {
  PERSONAL: 'Individual',
  CORPORATE: 'Empresa'
};

@Component({
  selector: 'app-services-admin',
  imports: [ActiveToggleComponent, CollapseCardComponent],
  template: `
    <app-collapse-card
      title="Servicios"
      description="Tipos de servicio definidos por el modelo de negocio."
    >
      <div class="service-types">
        <article>
          <strong>Individual</strong>
          <p class="muted small">Cuenta personal, sin empresa asociada.</p>
        </article>
      </div>
      <p class="muted tiny note">
        Empresa se incorpora con la etapa corporativa. Los tipos de servicio no se crean ni editan desde este portal.
      </p>
    </app-collapse-card>

    <app-collapse-card
      title="Combinaciones"
      description="Habilitá qué cruces Servicio × Fuente pueden utilizarse."
    >
      @if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else {
        <div class="combinations">
          @for (item of personalCombinations(); track item.id) {
            <article class="combination" [class.inactive]="!item.active">
              <div>
                <strong>{{ linkShort[item.linkType] }}</strong>
                <p class="source">{{ sourceShort[item.source] }}</p>
              </div>

              <app-active-toggle
                [value]="item.active"
                [disabled]="busyId() === item.id || (item.active && !item.canDisable)"
                (valueChange)="setActive(item, $event)"
              />

              @if (item.active && !item.canDisable) {
                <p class="muted tiny blocker">{{ disableReason(item) }}</p>
              }
            </article>
          }
        </div>
      }
    </app-collapse-card>
  `,
  styles: `
    :host { display: contents; }

    .service-types,
    .combinations {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0.75rem;
    }

    article {
      padding: 0.75rem;
      border: 1px solid var(--border);
      border-radius: 0.6rem;
      background: var(--bg);
    }

    article p { margin: 0.25rem 0 0; }
    .service-types article { max-width: 18rem; }
    .source { font-size: 0.9rem; }
    .note { margin: 0.8rem 0 0; }
    .tiny { font-size: 0.76rem; }

    .combination {
      display: flex;
      flex-direction: column;
      gap: 0.7rem;
      justify-content: space-between;
    }

    .combination.inactive { opacity: 0.68; }
    .blocker { min-height: 2.1em; }

    @media (max-width: 760px) {
      .service-types,
      .combinations { grid-template-columns: 1fr; }
    }
  `
})
export class ServicesAdminComponent implements OnInit, OnChanges {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  @Input() refreshVersion = 0;
  readonly changed = output<void>();

  readonly sourceShort = SOURCE_SHORT;
  readonly linkShort = LINK_SHORT;
  readonly combinations = signal<PlatformService[]>([]);
  readonly loading = signal(true);
  readonly busyId = signal<number | null>(null);

  personalCombinations(): PlatformService[] {
    return this.combinations().filter((item) => item.linkType === 'PERSONAL');
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
    return 'No se puede deshabilitar: ' + blockers.join(', ') + ' vigente(s).';
  }

  async setActive(item: PlatformService, active: boolean): Promise<void> {
    if (item.active === active) return;
    this.busyId.set(item.id);
    try {
      await firstValueFrom(this.api.updatePlatformService(item.id, { active }));
      await this.load();
      this.toast.success(active ? 'Combinación habilitada.' : 'Combinación deshabilitada.');
      this.changed.emit();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busyId.set(null);
    }
  }
}
