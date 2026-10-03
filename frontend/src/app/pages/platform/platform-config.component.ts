import { Component, signal } from '@angular/core';

import { ConnectionsManagerComponent } from '../../shared/connections-manager.component';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';
import { AiSourcesInfoComponent } from './ai-sources-info.component';
import { AccountsAdminComponent } from './accounts-admin.component';
import { BenefitsAdminComponent } from './benefits-admin.component';
import { CampaignsAdminComponent } from './campaigns-admin.component';
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
    CampaignsAdminComponent,
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

      <app-campaigns-admin />

      <app-invitations-admin />

      <app-collapse-card
        title="Conexiones de la plataforma"
        description="API keys, modelos, prioridades, límites y estado de las conexiones usadas por la plataforma."
      >
        <app-connections-manager
          scope="platform"
          title="Conexiones de la plataforma"
          [embedded]="true"
        />
      </app-collapse-card>
    </section>
  `,
  styles: ``
})
export class PlatformConfigComponent {
  readonly configurationRefreshVersion = signal(0);

  configurationChanged(): void {
    this.configurationRefreshVersion.update((value) => value + 1);
  }
}
