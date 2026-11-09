/* Navigation entries (shared by the sidebar and the hash router). */
import { Activity, BellRing, Bot, Boxes, GitBranch, LayoutDashboard, Network, ScrollText } from "lucide-react";

export const PAGES = [
  { id: "dashboard", label: "Overview", icon: LayoutDashboard },
  { id: "system", label: "System", icon: Activity },
  { id: "cicd", label: "Pipelines", icon: GitBranch },
  { id: "containers", label: "Containers", icon: Boxes },
  { id: "infrastructure", label: "Infrastructure", icon: Network },
  { id: "assistant", label: "AI assistant", icon: Bot },
  { id: "logs", label: "Logs", icon: ScrollText },
  { id: "alerts", label: "Alerts", icon: BellRing },
];
