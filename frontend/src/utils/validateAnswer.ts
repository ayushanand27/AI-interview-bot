export const MAX_ANSWER_LENGTH = 2000;

/** Warn when an answer looks like a mistaken paste (chat, files, prompts). */

const SUSPICIOUS_PATTERNS: { pattern: RegExp; message: string }[] = [
  {
    pattern: /\.(pdf|html|docx?|md)\b/i,
    message: "contains file names (.pdf, .html, etc.)",
  },
  {
    pattern: /architecture\.html|task3_architecture/i,
    message: "looks like architecture/task documentation",
  },
  {
    pattern: /prompt for claude|please improve my current architecture/i,
    message: "looks like a copied AI prompt",
  },
  {
    pattern: /your current task 3 architecture/i,
    message: "looks like project notes, not an interview answer",
  },
  {
    pattern: /^AI_Interview_Platform/i,
    message: "looks like an attachment name",
  },
];

export function isAnswerTooLong(answer: string): boolean {
  return answer.trim().length > MAX_ANSWER_LENGTH;
}

export function getAnswerWarnings(answer: string): string[] {
  const warnings: string[] = [];
  const trimmed = answer.trim();

  if (trimmed.length > MAX_ANSWER_LENGTH) {
    warnings.push(
      `Answer exceeds ${MAX_ANSWER_LENGTH} characters. Please shorten your response.`,
    );
  } else if (trimmed.length > MAX_ANSWER_LENGTH * 0.9) {
    warnings.push(`Answer is nearly at the ${MAX_ANSWER_LENGTH} character limit.`);
  }

  for (const { pattern, message } of SUSPICIOUS_PATTERNS) {
    if (pattern.test(trimmed)) {
      warnings.push(`Answer ${message}.`);
    }
  }

  return warnings;
}

export function confirmAnswerSubmit(answer: string): boolean {
  if (isAnswerTooLong(answer)) {
    window.alert(
      `Your answer exceeds ${MAX_ANSWER_LENGTH} characters. Please shorten it before submitting.`,
    );
    return false;
  }

  const warnings = getAnswerWarnings(answer);
  if (warnings.length === 0) return true;

  const preview =
    answer.length > 200 ? `${answer.slice(0, 200)}…` : answer;

  return window.confirm(
    `This answer may not be what you intended:\n\n` +
      warnings.map((w) => `• ${w}`).join("\n") +
      `\n\nPreview:\n"${preview}"\n\nSubmit anyway?`,
  );
}

export function isSuspiciousAnswer(answer: string | undefined): boolean {
  if (!answer) return false;
  return getAnswerWarnings(answer).length > 0;
}
