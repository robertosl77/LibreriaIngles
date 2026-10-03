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
  }
,
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
  }
];
