import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

import { ConnectionsManagerComponent } from '../../shared/connections-manager.component';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';
import { AiSourcesInfoComponent } from './ai-sources-info.component';
import { AccountsAdminComponent } from './accounts-admin.component';
import { BenefitsAdminComponent } from './benefits-admin.component';
import { InvitationsAdminComponent } from './invitations-admin.component';
import { ServicesAdminComponent } from './services-admin.component';

@Component({
  selector: 'app-platform-config',
  imports: [
    ConnectionsManagerComponent,
    CollapseCardComponent,
    AiSourcesInfoComponent,
    AccountsAdminComponent,
    ServicesAdminComponent,
    BenefitsAdminComponent,
    InvitationsAdminComponent
  ],
  template: `
    <section class="stack">
      <app-ai-sources-info />

      <app-services-admin
        [refreshVersion]="configurationRefreshVersion()"
        (changed)="configurationChanged()"
      />

      <app-accounts-admin
        [refreshVersion]="configurationRefreshVersion()"
        (changed)="configurationChanged()"
      />

      <app-benefits-admin
        [refreshVersion]="configurationRefreshVersion()"
        (changed)="configurationChanged()"
      />


      <app-invitations-admin />

      <app-collapse-card
        title="Conexiones de la plataforma"
        description="API keys, modelos, prioridades, límites y estado de las conexiones usadas por la plataforma."
        [open]="focusedConnectionId !== null"
      >
        <app-connections-manager
          scope="platform"
          title="Conexiones de la plataforma"
          [embedded]="true"
          [focusConnectionId]="focusedConnectionId"
        />
      </app-collapse-card>
    </section>
  `,
  styles: ``
})
export class PlatformConfigComponent {
  private readonly route = inject(ActivatedRoute);
  readonly focusedConnectionId = this.connectionIdFromQuery();

  private connectionIdFromQuery(): number | null {
    const value = Number(this.route.snapshot.queryParamMap.get('connectionId'));
    return Number.isInteger(value) && value > 0 ? value : null;
  }

  readonly configurationRefreshVersion = signal(0);

  configurationChanged(): void {
    this.configurationRefreshVersion.update((value) => value + 1);
  }
}
