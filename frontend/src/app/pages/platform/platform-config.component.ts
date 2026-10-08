import { Component, signal } from '@angular/core';

import { AiSourcesInfoComponent } from './ai-sources-info.component';
import { AccountsAdminComponent } from './accounts-admin.component';
import { BenefitsAdminComponent } from './benefits-admin.component';
import { InvitationsAdminComponent } from './invitations-admin.component';
import { ServicesAdminComponent } from './services-admin.component';

@Component({
  selector: 'app-platform-config',
  imports: [
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
