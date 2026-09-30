import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from '../core/auth.service';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <header class="shell-header">
      <div class="shell-inner">
        <a class="brand" routerLink="/app">Librería Inglés</a>
        <nav aria-label="Principal">
          <a routerLink="/app" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">Inicio</a>
          <a routerLink="/app/progreso" routerLinkActive="active">Progreso</a>
          <a routerLink="/app/historial" routerLinkActive="active">Historial</a>
          <a routerLink="/app/ia" routerLinkActive="active">IA</a>
          @if (auth.me()?.account?.isPlatformOwner) {
            <a routerLink="/app/plataforma" routerLinkActive="active">Plataforma</a>
          }
        </nav>
        <div class="user">
          @if (auth.me(); as me) {
            @if (me.studyProfile.operationalLevel) {
              <a class="chip" routerLink="/app/nivel" title="Nivel operativo">{{ me.studyProfile.operationalLevel }}</a>
            }
            <span class="muted small email">{{ me.account.displayName || me.account.email }}</span>
          }
          <button type="button" class="btn btn-sm" (click)="auth.logout()">Salir</button>
        </div>
      </div>
    </header>
    <router-outlet />
  `,
  styles: `
    .shell-header {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .shell-inner {
      max-width: 980px;
      margin: 0 auto;
      padding: 0.7rem 1rem;
      display: flex;
      align-items: center;
      gap: 1.2rem;
      flex-wrap: wrap;
    }
    .brand {
      font-weight: 750;
      text-decoration: none;
    }
    nav {
      display: flex;
      gap: 0.3rem;
      flex: 1;
      flex-wrap: wrap;
    }
    nav a {
      text-decoration: none;
      padding: 0.4rem 0.7rem;
      border-radius: 0.6rem;
      color: var(--muted);
      font-weight: 600;
      font-size: 0.92rem;
    }
    nav a.active {
      background: var(--info-bg);
      color: var(--text);
    }
    .user {
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }
    .user .chip {
      text-decoration: none;
    }
    @media (max-width: 640px) {
      .email { display: none; }
      nav { order: 3; flex-basis: 100%; }
    }
  `
})
export class ShellComponent {
  readonly auth = inject(AuthService);
}
