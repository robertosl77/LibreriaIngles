import { ClassStatus } from '../core/models';

export const STATUS_LABELS: Record<ClassStatus, string> = {
  GENERATING: 'Generando',
  GENERATION_FAILED: 'Error al generar',
  READY: 'Sin empezar',
  IN_PROGRESS: 'En progreso',
  AWAITING_EVALUATION: 'Esperando corrección',
  COMPLETED: 'Completada'
};

export function statusChip(status: ClassStatus): string {
  switch (status) {
    case 'COMPLETED':
      return 'chip chip-ok';
    case 'AWAITING_EVALUATION':
    case 'IN_PROGRESS':
      return 'chip chip-warn';
    case 'GENERATION_FAILED':
      return 'chip chip-bad';
    default:
      return 'chip';
  }
}

export function scoreChip(score: number | null): string {
  if (score === null) {
    return 'chip';
  }
  if (score >= 85) {
    return 'chip chip-ok';
  }
  if (score >= 60) {
    return 'chip chip-warn';
  }
  return 'chip chip-bad';
}
