import {
  PlatformCampaignPolicyCapabilities,
  PlatformCampaignPolicyDraft
} from '../../core/models';

export interface CampaignPolicyTemplate {
  id: string;
  title: string;
  description: string;
  draft: PlatformCampaignPolicyDraft;
}

export function campaignPolicyTemplateIssues(
  template: CampaignPolicyTemplate,
  capabilities: PlatformCampaignPolicyCapabilities
): string[] {
  const issues: string[] = [];
  const kind = capabilities.kinds.find((item) => item.key === template.draft.kind);
  if (!kind?.available) {
    issues.push(`Tipo no disponible: ${template.draft.kind}`);
  }

  const appliesMode = capabilities.appliesToModes.find(
    (item) => item.key === template.draft.appliesTo.mode
  );
  if (!appliesMode?.available) {
    issues.push(`Alcance no disponible: ${template.draft.appliesTo.mode}`);
  }

  if (
    template.draft.appliesTo.mode === 'CAMPAIGNS' &&
    template.draft.appliesTo.campaignIds.length === 0
  ) {
    issues.push('La plantilla requiere seleccionar al menos una campaña.');
  }

  for (const rule of template.draft.rules) {
    const capability = capabilities.rules.find((item) => item.key === rule.field);
    if (!capability?.available) {
      issues.push(`Condición no disponible: ${rule.field}`);
      continue;
    }
    if (!capability.operators.includes(rule.operator)) {
      issues.push(`Operador ${rule.operator} no válido para ${rule.field}`);
    }
    if (
      capability.requiresWindow &&
      (rule.windowDays < (capability.windowMinDays ?? 1) ||
        rule.windowDays > (capability.windowMaxDays ?? 3650))
    ) {
      issues.push(`Ventana inválida para ${rule.field}`);
    }
  }

  return issues;
}

function suppression(
  id: string,
  title: string,
  description: string,
  name: string,
  rules: PlatformCampaignPolicyDraft['rules']
): CampaignPolicyTemplate {
  return {
    id,
    title,
    description,
    draft: {
      name,
      description,
      kind: 'SUPPRESSION',
      enabled: true,
      appliesTo: { mode: 'ALL', campaignIds: [] },
      rules
    }
  };
}

export const CAMPAIGN_POLICY_TEMPLATES: CampaignPolicyTemplate[] = [
  suppression(
    'campaign-cooldown-7d',
    'Enfriamiento 7 días',
    'Bloquea una nueva campaña si la persona recibió al menos una campaña durante los últimos 7 días.',
    'Enfriamiento general · 7 días',
    [{ field: 'CAMPAIGN_GRANTS_COUNT', operator: 'GTE', value: 1, windowDays: 7 }]
  ),
  suppression(
    'campaign-cooldown-30d',
    'Enfriamiento 30 días',
    'Bloquea una nueva campaña si la persona recibió al menos una campaña durante los últimos 30 días.',
    'Enfriamiento general · 30 días',
    [{ field: 'CAMPAIGN_GRANTS_COUNT', operator: 'GTE', value: 1, windowDays: 30 }]
  ),
  suppression(
    'campaign-cooldown-90d',
    'Enfriamiento 90 días',
    'Bloquea una nueva campaña si la persona recibió al menos una campaña durante los últimos 90 días.',
    'Enfriamiento general · 90 días',
    [{ field: 'CAMPAIGN_GRANTS_COUNT', operator: 'GTE', value: 1, windowDays: 90 }]
  ),
  suppression(
    'same-benefit-30d',
    'No repetir Benefit · 30 días',
    'Bloquea la campaña candidata si la persona ya recibió ese mismo Benefit durante los últimos 30 días.',
    'No repetir el mismo Benefit · 30 días',
    [{ field: 'SAME_BENEFIT_GRANTS_COUNT', operator: 'GTE', value: 1, windowDays: 30 }]
  ),
  suppression(
    'same-benefit-90d',
    'No repetir Benefit · 90 días',
    'Bloquea la campaña candidata si la persona ya recibió ese mismo Benefit durante los últimos 90 días.',
    'No repetir el mismo Benefit · 90 días',
    [{ field: 'SAME_BENEFIT_GRANTS_COUNT', operator: 'GTE', value: 1, windowDays: 90 }]
  )
];
