import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './core/auth.guard';
import { ShellComponent } from './layout/shell.component';
import { AiSettingsComponent } from './pages/ai-settings/ai-settings.component';
import { ClassComponent } from './pages/class/class.component';
import { DashboardComponent } from './pages/dashboard/dashboard.component';
import { HistoryComponent } from './pages/history/history.component';
import { HomeComponent } from './pages/home/home.component';
import { LandingComponent } from './pages/landing/landing.component';
import { LevelComponent } from './pages/level/level.component';
import { LoginComponent } from './pages/login/login.component';

export const routes: Routes = [
  { path: '', component: LandingComponent, title: 'Librería Inglés' },
  { path: 'login', component: LoginComponent, canActivate: [guestGuard], title: 'Ingresar · Librería Inglés' },
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
      { path: 'historial', component: HistoryComponent, title: 'Historial · Librería Inglés' }
    ]
  },
  { path: '**', redirectTo: '' }
];
