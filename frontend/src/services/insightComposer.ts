import type { ScoringBreakdown, FrictionCategory } from '../types/scoring';

const FRICTION_LABELS: Record<FrictionCategory, string> = {
  reporting_fragmentation: 'Reporting Fragmentation',
  process_inefficiency: 'Process Inefficiency',
  tooling_inconsistency: 'Tooling Inconsistency',
  scaling_strain: 'Scaling Strain',
  customer_experience_friction: 'Customer Experience Issues',
};

const FRICTION_EXPLANATIONS: Record<FrictionCategory, string> = {
  reporting_fragmentation: "The company likely does not have a clear, unified way of tracking and understanding its data across teams.",
  scaling_strain: "The company is growing quickly, which can create operational pressure and make coordination harder.",
  tooling_inconsistency: "The company may be using too many different tools that don't work well together.",
  process_inefficiency: "The company may rely on manual or inefficient processes that slow things down.",
  customer_experience_friction: "Customers may be experiencing confusion, delays, or frustration when using the product or service."
};

const FRICTION_TO_ADVICE: Record<FrictionCategory, string> = {
  reporting_fragmentation: "Focus on helping them organize their data and create clear, unified reporting across teams.",
  scaling_strain: "Focus on improving coordination and communication structures as teams grow.",
  tooling_inconsistency: "Focus on consolidating tools and creating clearer workflows.",
  process_inefficiency: "Focus on streamlining processes and identifying bottlenecks.",
  customer_experience_friction: "Focus on understanding customer pain points and improving touchpoints."
};

const FRICTION_TO_FUNCTION: Record<FrictionCategory, string> = {
  reporting_fragmentation: "data and analytics",
  scaling_strain: "operations and coordination",
  tooling_inconsistency: "tooling and infrastructure",
  process_inefficiency: "operations and process",
  customer_experience_friction: "customer success and experience"
};

const PROBLEM_DEFINITIONS: Record<FrictionCategory, string> = {
  reporting_fragmentation: "likely struggling to maintain clear visibility across data as it scales teams and operations",
  scaling_strain: "likely facing coordination challenges as multiple teams grow and work in parallel",
  tooling_inconsistency: "likely dealing with fragmented tools that don't communicate well with each other",
  process_inefficiency: "likely dealing with manual processes that slow down decision-making and execution",
  customer_experience_friction: "likely facing challenges in maintaining consistent customer touchpoints and service quality"
};

const PROFILE_SKILLS: Record<FrictionCategory, string[]> = {
  reporting_fragmentation: [
    "structure and organize data into clear insights",
    "build reporting systems that scale with the business",
    "bridge the gap between data and business decisions"
  ],
  scaling_strain: [
    "create coordination frameworks across teams",
    "build processes that scale with growth",
    "enable clear communication across growing organizations"
  ],
  tooling_inconsistency: [
    "evaluate and consolidate tooling strategies",
    "create unified workflows across platforms",
    "reduce tool complexity and improve integrations"
  ],
  process_inefficiency: [
    "identify and eliminate process bottlenecks",
    "streamline operations and workflows",
    "create efficiency across team functions"
  ],
  customer_experience_friction: [
    "map and improve customer touchpoints",
    "create consistent customer journey experiences",
    "build feedback loops between customers and teams"
  ]
};

export function formatFrictionCategory(cat: string): string {
  return FRICTION_LABELS[cat as FrictionCategory] ?? cat.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function explainFrictionCategory(cat: string): string {
  return FRICTION_EXPLANATIONS[cat as FrictionCategory] ?? "This area may need attention.";
}

export function getFrictionAdvice(cat: string): string {
  return FRICTION_TO_ADVICE[cat as FrictionCategory] ?? "Help them improve clarity and alignment.";
}

export function getFrictionLevel(score: number): { level: string; description: string } {
  if (score >= 6) {
    return { level: "High", description: "There are strong signs that the company may be experiencing internal friction or operational challenges." };
  }
  if (score >= 3) {
    return { level: "Moderate", description: "There are some signs that the company may face internal challenges as they grow." };
  }
  return { level: "Low", description: "Limited signs of internal friction detected in the evidence collected so far." };
}

interface CategoryScore {
  category: FrictionCategory;
  score: number;
}

export function getTopCategories(breakdown: ScoringBreakdown): CategoryScore[] {
  return Object.entries(breakdown)
    .map(([category, data]) => ({ category: category as FrictionCategory, score: data.score }))
    .sort((a, b) => b.score - a.score);
}

function inferFunctionArea(signals: string[]): string {
  const lowerSignals = signals.map(s => s.toLowerCase()).join(' ');
  
  if (lowerSignals.includes('analytics') || lowerSignals.includes('data') || lowerSignals.includes('bi')) {
    return "data and analytics function";
  }
  if (lowerSignals.includes('report') || lowerSignals.includes('quarter') || lowerSignals.includes('revenue')) {
    return "data and reporting function";
  }
  if (lowerSignals.includes('hire') || lowerSignals.includes('role') || lowerSignals.includes('position')) {
    return "operations and talent function";
  }
  if (lowerSignals.includes('growth') || lowerSignals.includes('scale') || lowerSignals.includes('expand')) {
    return "operations and scaling function";
  }
  if (lowerSignals.includes('product') || lowerSignals.includes('feature')) {
    return "product and development function";
  }
  if (lowerSignals.includes('customer') || lowerSignals.includes('client')) {
    return "customer success function";
  }
  if (lowerSignals.includes('team') || lowerSignals.includes('lead')) {
    return "leadership and team function";
  }
  
  return "business operations";
}

function humanizeSignalText(text: string): string {
  const lower = text.toLowerCase();
  
  if (lower.includes('growth') || lower.includes('scale') || lower.includes('expand')) {
    return "The company shows signs of growth and expansion";
  }
  if (lower.includes('hire') || lower.includes('role') || lower.includes('position') || lower.includes('open job')) {
    return "The company is actively hiring for new positions";
  }
  if (lower.includes('analytics') || lower.includes('data') || lower.includes('bi') || lower.includes('data analyst')) {
    return "The company is investing in analytics and data capabilities";
  }
  if (lower.includes('report') || lower.includes('quarter') || lower.includes('revenue')) {
    return "The company communicates about performance and results";
  }
  if (lower.includes('team') || lower.includes('lead')) {
    return "The company is building out its leadership team";
  }
  if (lower.includes('customer') || lower.includes('client') || lower.includes('success')) {
    return "The company focuses on customer success";
  }
  if (lower.includes('product') || lower.includes('launch') || lower.includes('release')) {
    return "The company actively develops and releases products";
  }
  if (lower.includes('blog') || lower.includes('news') || lower.includes('press')) {
    return "The company maintains active communications";
  }
  if (lower.includes('career') || lower.includes('jobs')) {
    return "The company has an active careers page";
  }
  if (lower.includes('api') || lower.includes('developer')) {
    return "The company provides developer resources";
  }
  if (lower.includes('security') || lower.includes('compliance')) {
    return "The company emphasizes security and compliance";
  }
  if (lower.includes('integration') || lower.includes('partner')) {
    return "The company works with integration partners";
  }
  if (lower.includes('mobile') || lower.includes('app')) {
    return "The company invests in mobile experience";
  }
  
  if (text.length > 60) return text.slice(0, 60) + "...";
  return text;
}

export function transformSignalToObservation(text: string): string {
  const observation = humanizeSignalText(text);
  return observation.charAt(0).toUpperCase() + observation.slice(1);
}

export function generateObservations(signalTexts: string[]): string[] {
  if (!signalTexts || signalTexts.length === 0) return ["Limited information available"];
  const unique = [...new Set(signalTexts.slice(0, 5).map(s => humanizeSignalText(s)))];
  return unique.slice(0, 4);
}

export function generateFunctionalArea(signals: string[], primaryFriction: FrictionCategory): string {
  const funcFromSignals = inferFunctionArea(signals);
  const funcFromFriction = FRICTION_TO_FUNCTION[primaryFriction] ?? "business operations";
  
  return funcFromSignals !== "business operations" ? funcFromSignals : funcFromFriction;
}

export function defineTheProblem(primaryFriction: FrictionCategory): string {
  return PROBLEM_DEFINITIONS[primaryFriction] ?? "facing operational challenges as they grow";
}

export function whyTheyAreHiring(signals: string[]): string {
  const lowerSignals = signals.map(s => s.toLowerCase()).join(' ');
  
  if (lowerSignals.includes('analytics') || lowerSignals.includes('data')) {
    return "The presence of analytics hiring suggests the company is trying to improve how it collects, structures, or uses data for decision-making.";
  }
  if (lowerSignals.includes('hire') || lowerSignals.includes('role')) {
    return "The active hiring suggests the company is trying to build capability in areas where they're currently stretched.";
  }
  if (lowerSignals.includes('growth') || lowerSignals.includes('scale')) {
    return "The growth signals suggest the company is trying to scale operations to keep pace with business expansion.";
  }
  if (lowerSignals.includes('report')) {
    return "The reporting-related signals suggest the company is trying to improve visibility into business performance.";
  }
  
  return "The hiring and growth patterns suggest the company is actively trying to build capability in key areas.";
}

export function whereToAddValue(primaryFriction: FrictionCategory): string {
  const func = FRICTION_TO_FUNCTION[primaryFriction] ?? "business operations";
  const advice = FRICTION_TO_ADVICE[primaryFriction] ?? "Help them improve clarity.";
  
  return `There is a clear opportunity to help the company ${advice.toLowerCase().replace('Focus on ', '')} in their ${func}.`;
}

export function idealProfile(primaryFriction: FrictionCategory): string[] {
  return PROFILE_SKILLS[primaryFriction] ?? [
    "identify operational gaps and opportunities",
    "create clarity in business processes",
    "enable better decision-making"
  ];
}

export function positioningGuidance(primaryFriction: FrictionCategory): string {
  const func = FRICTION_TO_FUNCTION[primaryFriction] ?? "business operations";

  return `How to position yourself with this company: someone who helps teams improve ${func} through better processes, clearer data, and scalable solutions.`;
}

export function generateWhatThisMeans(signals: string[], _primaryFriction: string): string {
  if (!signals || signals.length === 0) return "Limited data available to determine what this means.";
  
  const categories = signals.slice(0, 5).map(s => {
    const lower = s.toLowerCase();
    if (lower.includes('growth') || lower.includes('scale')) return 'growth';
    if (lower.includes('hire') || lower.includes('role')) return 'hiring';
    if (lower.includes('analytics') || lower.includes('data')) return 'data';
    if (lower.includes('report')) return 'reporting';
    return 'other';
  });
  
  const hasGrowth = categories.includes('growth');
  const hasHiring = categories.includes('hiring');
  const hasData = categories.includes('data');
  const hasReporting = categories.includes('reporting');
  
  if (hasGrowth && hasHiring) return "The company is actively growing and hiring, which often creates complexity in how teams share information and make decisions.";
  if (hasData && hasHiring) return "The company is investing in data capabilities while scaling teams, which can create challenges in keeping everyone aligned.";
  if (hasGrowth && hasReporting) return "Rapid growth often surfaces gaps in how the company tracks and reports on performance across teams.";
  if (hasHiring) return "Active hiring suggests the company is scaling, which often requires better coordination and processes.";
  
  return "These patterns often indicate a company in transition, which may benefit from clearer structures.";
}

export function generateWhatsHappening(companyName: string, signalTexts: string[]): string {
  if (!signalTexts || signalTexts.length === 0) return `${companyName} appears to be in an early stage with limited information available.`;

  const categories = signalTexts.slice(0, 5).map(s => humanizeSignalText(s));
  const unique = [...new Set(categories)];
  
  if (unique.length === 0) return `${companyName} shows signs of activity. More data would help provide clearer insights.`;
  if (unique.length === 1) return `${companyName}: ${unique[0].toLowerCase()}.`;
  if (unique.length === 2) return `${companyName}: ${unique[0].toLowerCase()} and ${unique[1].toLowerCase()}.`;
  
  return `${companyName}: ${unique.slice(0, 2).join(', ').toLowerCase()}, among other signs.`;
}

export function generateOpportunityValue(_companyName: string, primary: FrictionCategory): string {
  const advice = getFrictionAdvice(primary);
  return `This company would likely benefit from ${advice.toLowerCase()}`;
}

export function generateWorkingWithCompany(_companyName: string, primary: FrictionCategory): string {
  const advice = getFrictionAdvice(primary);
  return `You would probably focus on ${advice.toLowerCase()}`;
}

interface ConfidenceParams {
  signalCount: number;
  collectionRunCount: number;
  hasRepeatedSignals: boolean;
}

export function generateConfidenceNarrative({ signalCount, collectionRunCount, hasRepeatedSignals }: ConfidenceParams): string {
  if (collectionRunCount >= 3 && hasRepeatedSignals && signalCount >= 5) return "High confidence - we observed consistent patterns across multiple sources.";
  if (collectionRunCount >= 2 && signalCount >= 3) return "Moderate confidence - patterns detected across a few sources.";
  if (signalCount >= 5) return "Good confidence based on the volume of observations.";
  if (signalCount >= 2) return "Limited confidence - we have some observations but would benefit from more data.";
  return "Limited information available. More data would strengthen these insights.";
}