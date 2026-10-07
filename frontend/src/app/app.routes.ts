import { Routes } from '@angular/router';

import { authGuard, guestGuard, platformOwnerGuard } from './core/auth.guard';
import { ShellComponent } from './layout/shell.component';
import { AiSettingsComponent } from './pages/ai-settings/ai-settings.component';
import { CertificateComponent } from './pages/certificate/certificate.component';
import { ClassComponent } from './pages/class/class.component';
import { ConsumptionComponent } from './pages/consumption/consumption.component';
import { DashboardComponent } from './pages/dashboard/dashboard.component';
import { HistoryComponent } from './pages/history/history.component';
import { InvitationComponent } from './pages/invitation/invitation.component';
import { HomeComponent } from './pages/home/home.component';
import { LandingComponent } from './pages/landing/landing.component';
import { LevelComponent } from './pages/level/level.component';
import { LoginComponent } from './pages/login/login.component';
import { OrganizationOnboardingComponent } from './pages/organization-onboarding/organization-onboarding.component';
import { CampaignsAdminComponent } from './pages/platform/campaigns-admin.component';
import { PlatformConfigComponent } from './pages/platform/platform-config.component';
import { PlatformOverviewComponent } from './pages/platform/platform-overview.component';
import { PlatformComponent } from './pages/platform/platform.component';

export const routes: Routes = [
  { path: '', component: LandingComponent, title: 'Librería Inglés' },
  // Público: verificación del certificado de nivel (T-024).
  { path: 'certificado/:code', component: CertificateComponent, title: 'Certificado · Librería Inglés' },
  { path: 'invitacion/:token', component: InvitationComponent, title: 'Invitación · Librería Inglés' },
  { path: 'login', component: LoginComponent, canActivate: [guestGuard], title: 'Ingresar · Librería Inglés' },
  { path: 'empresa/alta', component: OrganizationOnboardingComponent, title: 'Registrar organización · Librería Inglés' },
  {
    path: 'app',
    component: ShellComponent,
    canActivate: [authGuard],
    canActivateChild: [authGuard],
    children: [
      { path: '', component: HomeComponent, title: 'Inicio · Librería Inglés' },
      { path: 'nivel', component: LevelComponent, title: 'Nivel · Librería Inglés' },
      { path: 'ia', component: AiSettingsComponent, title: 'Conexiones de IA · Librería Inglés' },
      { path: 'clase/:id', component: ClassComponent, title: 'Clase · Librería Inglés' },
      { path: 'progreso', component: DashboardComponent, title: 'Progreso · Librería Inglés' },
      { path: 'historial', component: HistoryComponent, title: 'Historial · Librería Inglés' },
      { path: 'consumo', component: ConsumptionComponent, title: 'Consumo · Librería Inglés' },
      {
        path: 'plataforma',
        component: PlatformComponent,
        canActivate: [platformOwnerGuard],
        children: [
          { path: '', pathMatch: 'full', redirectTo: 'resumen' },
          {
            path: 'resumen',
            component: PlatformOverviewComponent,
            title: 'Resumen de plataforma · Librería Inglés'
          },
          {
            path: 'configuracion',
            component: PlatformConfigComponent,
            title: 'Configuración de plataforma · Librería Inglés'
          },
          {
            path: 'campanas',
            component: CampaignsAdminComponent,
            title: 'Campañas · Librería Inglés'
          }
        ]
      }
    ]
  },
  { path: '**', redirectTo: '' }
];
