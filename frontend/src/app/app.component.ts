import { Component, OnInit } from '@angular/core';

import { HealthService } from './core/health.service';

@Component({
  selector: 'app-root',
  standalone: true,
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent implements OnInit {
  backendStatus = 'Verificando backend…';

  constructor(private readonly healthService: HealthService) {}

  ngOnInit(): void {
    this.healthService.check().subscribe({
      next: () => {
        this.backendStatus = 'Backend conectado';
      },
      error: () => {
        this.backendStatus = 'Backend no disponible';
      }
    });
  }
}
