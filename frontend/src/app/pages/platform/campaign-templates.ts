import {
  CampaignNotification,
  CampaignRule,
  CampaignTrigger
} from '../../core/models';

export interface CampaignTemplate {
  id: string;
  title: string;
  description: string;
  name: string;
  trigger: CampaignTrigger;
  rules: CampaignRule[];
  priority: number;
  stackable: boolean;
  maxRecipients: number | null;
  startsAt?: string;
  endsAt?: string;
  notification: CampaignNotification;
  message: string;
}

export const CAMPAIGN_TEMPLATES: CampaignTemplate[] = [
  {
    id: 'welcome-no-membership',
    title: 'Bienvenida',
    description: 'Primer login de una cuenta personal que todavía no tiene membresía.',
    name: 'Bienvenida · primer login sin membresía',
    trigger: 'FIRST_LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'HAS_GRANTED_SERVICE', operator: 'EQ', value: false }
    ],
    priority: 100,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Te damos un beneficio para que puedas empezar a usar Librería Inglés.'
  },
  {
    id: 'first-login-personal',
    title: 'Primer ingreso',
    description: 'Todas las cuentas personales en su primer login, tengan o no membresía.',
    name: 'Primer ingreso · cuentas personales',
    trigger: 'FIRST_LOGIN',
    rules: [{ field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' }],
    priority: 100,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: ''
  },
  {
    id: 'login-without-membership',
    title: 'Sin membresía',
    description: 'Al ingresar, alcanza a cuentas personales que todavía no tienen membresía.',
    name: 'Usuarios sin membresía · al ingresar',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'HAS_GRANTED_SERVICE', operator: 'EQ', value: false }
    ],
    priority: 100,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: ''
  },
  {
    id: 'login-with-membership',
    title: 'Con membresía',
    description: 'Al ingresar, alcanza a quienes ya tienen una membresía otorgada.',
    name: 'Beneficio extra · usuarios con membresía',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'HAS_GRANTED_SERVICE', operator: 'EQ', value: true }
    ],
    priority: 100,
    stackable: true,
    maxRecipients: null,
    notification: 'IN_APP',
    message: ''
  },
  {
    id: 'source-byok',
    title: 'Propias keys',
    description: 'Cuentas cuya fuente de IA actual es BYOK.',
    name: 'Usuarios con propias keys',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'SERVICE_SOURCE', operator: 'EQ', value: 'BYOK' }
    ],
    priority: 100,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: ''
  },
  {
    id: 'source-platform',
    title: 'IA de plataforma',
    description: 'Cuentas que actualmente usan la IA de la plataforma.',
    name: 'Usuarios con IA de plataforma',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'SERVICE_SOURCE', operator: 'EQ', value: 'PLATFORM' }
    ],
    priority: 100,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: ''
  },
  {
    id: 'source-hybrid',
    title: 'Híbrido',
    description: 'Cuentas cuya fuente actual combina propias keys y plataforma.',
    name: 'Usuarios con membresía híbrida',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'SERVICE_SOURCE', operator: 'EQ', value: 'HYBRID' }
    ],
    priority: 100,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: ''
  },
  {
    id: 'anniversary-year',
    title: 'Antigüedad de 1 año',
    description: 'Usuarios con al menos 365 días desde su registro.',
    name: 'Fidelización · 1 año desde registro',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'DAYS_SINCE_CREATED', operator: 'GTE', value: 365 }
    ],
    priority: 100,
    stackable: true,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Gracias por seguir aprendiendo con Librería Inglés.'
  },
  {
    id: 'recent-30-days',
    title: 'Registrados recientemente',
    description: 'Usuarios con hasta 30 días desde su registro.',
    name: 'Usuarios nuevos · primeros 30 días',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'DAYS_SINCE_CREATED', operator: 'LTE', value: 30 }
    ],
    priority: 100,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: ''
  },
  {
    id: 'email-domain',
    title: 'Dominio de email',
    description: 'Base para una campaña destinada a un dominio concreto. Cambiá empresa.com.',
    name: 'Campaña · dominio de email',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'EMAIL_DOMAIN', operator: 'EQ', value: 'empresa.com' }
    ],
    priority: 100,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: ''
  },
  {
    id: 'limited-100',
    title: 'Cupo limitado',
    description: 'Promoción general limitada a los primeros 100 beneficiarios.',
    name: 'Promoción limitada · primeros 100',
    trigger: 'LOGIN',
    rules: [{ field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' }],
    priority: 100,
    stackable: false,
    maxRecipients: 100,
    notification: 'IN_APP',
    message: ''
  },
  {
    id: 'win-back-inactive',
    title: 'Volvé a estudiar',
    description: 'Al volver a ingresar, detecta 60 días sin clases y sin servicio vigente.',
    name: 'Volvé a estudiar',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'HAS_GRANTED_SERVICE', operator: 'EQ', value: false },
      { field: 'DAYS_SINCE_LAST_ACTIVITY', operator: 'GTE', value: 60 }
    ],
    priority: 60,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: '¡Qué bueno verte de nuevo! Tenemos un beneficio para ayudarte a retomar.'
  },
  {
    id: 'expired-service',
    title: 'Servicio vencido',
    description: 'Al volver, segmenta cuentas cuyo último servicio venció hace al menos 30 días.',
    name: 'Regreso después del vencimiento',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'HAS_GRANTED_SERVICE', operator: 'EQ', value: false },
      { field: 'DAYS_SINCE_SERVICE_EXPIRED', operator: 'GTE', value: 30 }
    ],
    priority: 70,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Tenemos una propuesta para que vuelvas a practicar inglés.'
  },
  {
    id: 'service-expiring-soon',
    title: 'Servicio próximo a vencer',
    description: 'Cuentas personales con servicio vigente que vence dentro de los próximos 7 días.',
    name: 'Retención · servicio próximo a vencer',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'HAS_GRANTED_SERVICE', operator: 'EQ', value: true },
      { field: 'DAYS_UNTIL_SERVICE_EXPIRES', operator: 'LTE', value: 7 }
    ],
    priority: 65,
    stackable: true,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Tu servicio está próximo a vencer. Tenemos un beneficio para acompañarte.'
  },
  {
    id: 'document-country-ar',
    title: 'País documental · Argentina',
    description: 'Ejemplo de segmentación por país documental declarado. AR no implica residencia ni ubicación actual.',
    name: 'Segmentación · documento Argentina',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'DOCUMENT_COUNTRY', operator: 'EQ', value: 'AR' }
    ],
    priority: 100,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: ''
  },
  {
    id: 'subscription-origin-invitation',
    title: 'Origen · invitación',
    description: 'Cuentas cuyo servicio vigente fue otorgado mediante una invitación.',
    name: 'Fidelización · origen invitación',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'HAS_GRANTED_SERVICE', operator: 'EQ', value: true },
      { field: 'SUBSCRIPTION_ORIGIN', operator: 'EQ', value: 'INVITATION' }
    ],
    priority: 70,
    stackable: true,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Gracias por seguir aprendiendo con el servicio que recibiste mediante una invitación.'
  },
  {
    id: 'never-studied',
    title: 'Registrado pero nunca practicó',
    description: 'Detecta cuentas que todavía no completaron ninguna clase.',
    name: 'Empezá tu primera clase',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'NEVER_STUDIED', operator: 'EQ', value: true }
    ],
    priority: 80,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Tu primera práctica está lista cuando quieras empezar.'
  },
  {
    id: 'weekly-consistency',
    title: 'Constancia semanal',
    description: 'Al menos 5 clases cada día durante los últimos 7 días.',
    name: 'Premio por constancia semanal',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'MIN_CLASSES_PER_ACTIVE_DAY', operator: 'GTE', value: 5, windowDays: 7 },
      { field: 'ACTIVE_STUDY_DAYS', operator: 'GTE', value: 7, windowDays: 7 }
    ],
    priority: 50,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Tu constancia merece un reconocimiento.'
  },
  {
    id: 'monthly-active',
    title: 'Alta actividad mensual',
    description: 'Al menos 20 días con actividad dentro de los últimos 30 días.',
    name: 'Fidelización · alta actividad mensual',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'ACTIVE_STUDY_DAYS', operator: 'GTE', value: 20, windowDays: 30 }
    ],
    priority: 55,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Gracias por mantener una práctica tan constante.'
  },
  {
    id: 'writing-needs-review-active',
    title: 'Writing necesita repaso',
    description: 'Usuarios activos cuyo progreso agregado de Writing está en NEEDS_REVIEW.',
    name: 'Recuperación · Writing necesita repaso',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'ABILITY_STATUS', subject: 'WRITING', operator: 'EQ', value: 'NEEDS_REVIEW' },
      { field: 'ACTIVE_STUDY_DAYS', operator: 'GTE', value: 5, windowDays: 14 }
    ],
    priority: 45,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Vemos que seguís practicando. Te damos un impulso para reforzar Writing.'
  },
  {
    id: 'frequent-appeals',
    title: 'Apelaciones frecuentes',
    description: 'Usuarios que apelaron al menos 3 correcciones durante los últimos 14 días.',
    name: 'Acompañamiento · apelaciones frecuentes',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'APPEALS_COUNT', operator: 'GTE', value: 3, windowDays: 14 }
    ],
    priority: 40,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Queremos acompañarte para revisar cómo está funcionando tu experiencia de corrección.'
  },
  {
    id: 'speaking-never-used',
    title: 'Probar Speaking',
    description: 'Usuarios con al menos 20 clases completadas en 30 días que todavía nunca respondieron hablando.',
    name: 'Adopción · primera experiencia con Speaking',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'CLASSES_COMPLETED', operator: 'GTE', value: 20, windowDays: 30 },
      { field: 'SPEAKING_RESPONSES', operator: 'EQ', value: 0 }
    ],
    priority: 55,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Ya venís practicando con constancia. Te invitamos a probar una actividad hablando.'
  },
  {
    id: 'byok-key-failures',
    title: 'BYOK con fallas de credencial o cuota',
    description: 'Usuarios BYOK con al menos 3 fallos de sus propias conexiones por credencial inválida o cuota durante los últimos 7 días.',
    name: 'Conversión · BYOK con fallas repetidas',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'SERVICE_SOURCE', operator: 'EQ', value: 'BYOK' },
      {
        field: 'AI_FAILURES_COUNT',
        filters: { ownerType: 'ACCOUNT', errorCode: 'CREDENTIAL_OR_QUOTA' },
        operator: 'GTE',
        value: 3,
        windowDays: 7
      }
    ],
    priority: 40,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Tus propias conexiones de IA tuvieron varias dificultades. Podemos ofrecerte una alternativa para seguir practicando.'
  },
  {
    id: 'byok-never-activated',
    title: 'BYOK configurado pero nunca activado',
    description: 'Usuarios BYOK con una conexión propia activa configurada hace al menos 7 días y sin ningún uso real exitoso.',
    name: 'Onboarding técnico · BYOK sin activación',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'SERVICE_SOURCE', operator: 'EQ', value: 'BYOK' },
      { field: 'DAYS_SINCE_BYOK_CONFIGURED_WITHOUT_SUCCESS', operator: 'GTE', value: 7 }
    ],
    priority: 40,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Tu conexión propia todavía no logró completar un uso exitoso. Queremos ayudarte a ponerla en funcionamiento.'
  },
  {
    id: 'study-streak',
    title: 'Racha de estudio',
    description: 'Usuarios con una racha actual de al menos 7 días consecutivos.',
    name: 'Fidelización · racha de 7 días',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'STUDY_STREAK_DAYS', operator: 'GTE', value: 7 }
    ],
    priority: 55,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: '¡Siete días seguidos practicando! Seguí así.'
  },
  {
    id: 'failed-exams-follow-up',
    title: 'Acompañamiento tras exámenes desaprobados',
    description: 'Usuarios que desaprobaron al menos 2 exámenes de nivel durante los últimos 30 días.',
    name: 'Acompañamiento · exámenes desaprobados',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'EXAMS_FAILED', operator: 'GTE', value: 2, windowDays: 30 }
    ],
    priority: 45,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Queremos acompañarte para que puedas volver a intentarlo con más práctica.'
  },
  {
    id: 'started-not-completed-classes',
    title: 'Dificultad para completar clases',
    description: 'Usuarios que iniciaron al menos 5 clases en 7 días pero completaron como máximo 1.',
    name: 'Acompañamiento · clases iniciadas sin completar',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'CLASSES_STARTED', operator: 'GTE', value: 5, windowDays: 7 },
      { field: 'CLASSES_COMPLETED', operator: 'LTE', value: 1, windowDays: 7 },
      { field: 'CLASSES_NOT_COMPLETED', operator: 'GTE', value: 4, windowDays: 7 }
    ],
    priority: 45,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Vimos que estás intentando practicar. Queremos darte un impulso para completar tus clases.'
  },
  {
    id: 'recover-broken-streak',
    title: 'Recuperar racha interrumpida',
    description: 'Usuarios cuya última racha duró al menos 30 días y se cortó hace entre 2 y 5 días.',
    name: 'Recuperación · racha de 30 días interrumpida',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'LAST_ENDED_STREAK_DAYS', operator: 'GTE', value: 30 },
      { field: 'DAYS_SINCE_STREAK_BROKEN', operator: 'GTE', value: 2 },
      { field: 'DAYS_SINCE_STREAK_BROKEN', operator: 'LTE', value: 5 }
    ],
    priority: 50,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Tu racha fue muy buena. Te damos un incentivo para ayudarte a retomarla.'
  },
  {
    id: 'launch-cohort-date-range',
    title: 'Cohorte por fecha',
    description: 'Cuentas personales registradas dentro de un período concreto y sin membresía otorgada.',
    name: 'Cohorte de lanzamiento · sin membresía',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'CREATED_AT', operator: 'GTE', value: '2026-09-01T00:00:00+00:00' },
      { field: 'CREATED_AT', operator: 'LTE', value: '2026-09-15T23:59:59+00:00' },
      { field: 'HAS_GRANTED_SERVICE', operator: 'EQ', value: false }
    ],
    priority: 75,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Tenemos un beneficio especial para esta cohorte de usuarios.'
  },
  {
    id: 'onboarding-platform-never-started',
    title: 'Onboarding sin primera clase',
    description: 'Usuarios de Plataforma con hasta 14 días desde el registro que todavía nunca completaron una clase.',
    name: 'Empujón inicial · Plataforma sin primera clase',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'DAYS_SINCE_CREATED', operator: 'LTE', value: 14 },
      { field: 'SERVICE_SOURCE', operator: 'EQ', value: 'PLATFORM' },
      { field: 'NEVER_STUDIED', operator: 'EQ', value: true }
    ],
    priority: 65,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Queremos ayudarte a completar tu primera práctica.'
  },
  {
    id: 'active-service-churn-prevention',
    title: 'Prevención de abandono',
    description: 'Usuarios con membresía vigente que llevan al menos 21 días sin completar una clase.',
    name: 'Prevención de abandono · membresía vigente',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'HAS_GRANTED_SERVICE', operator: 'EQ', value: true },
      { field: 'DAYS_SINCE_LAST_ACTIVITY', operator: 'GTE', value: 21 }
    ],
    priority: 45,
    stackable: true,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Vimos que hace un tiempo no practicás. Tenemos un incentivo para ayudarte a retomar.'
  },
  {
    id: 'steady-low-volume-streak',
    title: 'Constancia sin alto volumen',
    description: 'Racha de al menos 21 días con un promedio máximo de 1,5 clases por día en esa ventana.',
    name: 'Premio por hábito sostenido',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'STUDY_STREAK_DAYS', operator: 'GTE', value: 21 },
      { field: 'AVERAGE_CLASSES_PER_DAY', operator: 'LTE', value: 1.5, windowDays: 21 }
    ],
    priority: 50,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Tu hábito sostenido merece un reconocimiento.'
  },
  {
    id: 'successful-return-after-expiry',
    title: 'Regreso exitoso',
    description: 'Usuarios que tuvieron un servicio vencido, hoy vuelven a tener membresía y completaron al menos 10 clases en 14 días.',
    name: 'Premio por regreso exitoso',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'HAS_GRANTED_SERVICE', operator: 'EQ', value: true },
      { field: 'DAYS_SINCE_SERVICE_EXPIRED', operator: 'GTE', value: 30 },
      { field: 'CLASSES_COMPLETED', operator: 'GTE', value: 10, windowDays: 14 }
    ],
    priority: 50,
    stackable: true,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Volviste y recuperaste el ritmo. Queremos reconocer ese regreso.'
  },
  {
    id: 'seasonal-summer-window',
    title: 'Campaña estacional',
    description: 'Promoción para cuentas personales durante una ventana estacional concreta. Las fechas quedan precargadas y son editables.',
    name: 'Estacional · verano 2026/2027',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' }
    ],
    priority: 55,
    stackable: false,
    maxRecipients: null,
    startsAt: '2026-12-15T00:00',
    endsAt: '2027-01-15T23:59',
    notification: 'IN_APP',
    message: 'Tenemos una propuesta especial para acompañarte durante esta temporada.'
  },
  {
    id: 'engaged-byok-platform-trial',
    title: 'Prueba de Plataforma para BYOK activo',
    description: 'Usuarios BYOK sin membresía otorgada, con al menos 12 días activos y 25 clases en los últimos 30 días.',
    name: 'Conversión · BYOK activo a prueba de Plataforma',
    trigger: 'LOGIN',
    rules: [
      { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
      { field: 'HAS_GRANTED_SERVICE', operator: 'EQ', value: false },
      { field: 'SERVICE_SOURCE', operator: 'EQ', value: 'BYOK' },
      { field: 'ACTIVE_STUDY_DAYS', operator: 'GTE', value: 12, windowDays: 30 },
      { field: 'CLASSES_COMPLETED', operator: 'GTE', value: 25, windowDays: 30 }
    ],
    priority: 60,
    stackable: false,
    maxRecipients: null,
    notification: 'IN_APP',
    message: 'Por tu constancia, queremos que pruebes una modalidad con IA de Librería Inglés.'
  }
];
