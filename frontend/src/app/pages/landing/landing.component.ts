import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { HealthService } from '../../core/health.service';

@Component({
  selector: 'app-landing',
  imports: [RouterLink],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.css'
})
export class LandingComponent implements OnInit {
  private readonly healthService = inject(HealthService);
  readonly backendStatus = signal('Verificando backend…');

  ngOnInit(): void {
    this.healthService.check().subscribe({
      next: () => this.backendStatus.set('Backend conectado'),
      error: () => this.backendStatus.set('Backend no disponible')
    });
  }
}
