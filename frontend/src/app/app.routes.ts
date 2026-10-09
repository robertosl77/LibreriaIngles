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
import { BankReviewComponent } from './pages/platform/bank-review.component';
import { PlatformComponent } from './pages/platform/platform.component';

export const routes: Routes = [
  { path: '', component: LandingComponent },
  // Público: verificación del certificado de nivel (T-024).
  { path: 'certificado/:code', component: CertificateComponent, title: 'Certificado' },
  { path: 'invitacion/:token', component: InvitationComponent, title: 'Invitación' },
  { path: 'login', component: LoginComponent, canActivate: [guestGuard], title: 'Ingresar' },
  { path: 'empresa/alta', component: OrganizationOnboardingComponent, title: 'Registrar organización' },
  {
    path: 'app',
    component: ShellComponent,
    canActivate: [authGuard],
    canActivateChild: [authGuard],
    children: [
      { path: '', component: HomeComponent, title: 'Inicio' },
      { path: 'nivel', component: LevelComponent, title: 'Nivel' },
      { path: 'ia', component: AiSettingsComponent, title: 'Conexiones de IA' },
      { path: 'clase/:id', component: ClassComponent, title: 'Clase' },
      { path: 'progreso', component: DashboardComponent, title: 'Progreso' },
      { path: 'historial', component: HistoryComponent, title: 'Historial' },
      { path: 'consumo', component: ConsumptionComponent, title: 'Consumo' },
      {
        path: 'plataforma',
        component: PlatformComponent,
        canActivate: [platformOwnerGuard],
        children: [
          { path: '', pathMatch: 'full', redirectTo: 'resumen' },
          {
            path: 'resumen',
            component: PlatformOverviewComponent,
            title: 'Resumen de plataforma'
          },
          {
            path: 'configuracion',
            component: PlatformConfigComponent,
            title: 'Configuración de plataforma'
          },
          {
            path: 'campanas',
            component: CampaignsAdminComponent,
            title: 'Campañas'
          },
          {
            path: 'ejercicios',
            component: BankReviewComponent,
            title: 'Ejercicios en revisión'
          }
        ]
      }
    ]
  },
  { path: '**', redirectTo: '' }
];
