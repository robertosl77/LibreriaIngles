# UI compartida

Esta carpeta concentra primitivas visuales reutilizables de Librería Inglés. La regla es simple:
si un patrón visual se repite en más de una pantalla, no se copia su HTML/CSS; se extrae acá y las
pantallas consumen el mismo componente.

## Componentes actuales

- `CollapseCardComponent`: fuente única del patrón colapsable basado en `<details>/<summary>`.
  Fue extraído del Dashboard de Progreso y se reutiliza también en Plataforma. El chevron, foco,
  espaciado, borde, comportamiento responsive y reducción de movimiento viven en un solo lugar.
- `ActiveToggleComponent`: control booleano Activo/Inactivo reutilizable. Servicios y Beneficios
  consumen exactamente el mismo componente.
- `TabNavComponent`: navegación horizontal por tabs/rutas con el mismo subrayado activo,
  espaciado, scroll responsive y reducción de movimiento. Plataforma ya consume esta pieza.

## Criterio para componentes futuros

Botones, switches, tarjetas, estados y otros controles que empiecen a repetirse deben converger a
esta capa compartida en lugar de generar una variante nueva por pantalla. La futura adopción de una
librería externa (por ejemplo Bootstrap) debería poder resolverse principalmente dentro de esta capa,
sin reescribir la lógica funcional de cada página.
