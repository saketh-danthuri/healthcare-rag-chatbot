/* ============================================================
   Static configuration - suggested questions, labels, etc.
   ============================================================ */

export const SUGGESTED_QUESTIONS = [
  {
    icon: "AlertTriangle",
    title: "Troubleshoot Job Failure",
    question: "What should I do if CFT303A has not started by 3 AM?",
  },
  {
    icon: "FileText",
    title: "Runbook Procedure",
    question: "Show me the escalation path for CLMU load failures",
  },
  {
    icon: "Database",
    title: "Query Claims Data",
    question: "How many claims are currently in pending status?",
  },
  {
    icon: "BookOpen",
    title: "Process Knowledge",
    question: "What is the runbook procedure for ATL101Y failures?",
  },
] as const;

export const ACTION_TYPE_LABELS: Record<string, string> = {
  send_escalation_email: "Send Escalation Email",
  send_email: "Send Escalation Email",
  query_database: "Query Database",
};

/** Map tool_name from backend to action_type for approval endpoint */
export const TOOL_TO_ACTION_TYPE: Record<string, string> = {
  send_escalation_email: "send_email",
  query_database: "query_database",
};

export const HEALTH_POLL_INTERVAL = 30000; // 30 seconds
