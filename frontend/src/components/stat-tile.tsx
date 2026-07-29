import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";

interface StatTileProps {
  label: string;
  value: string;
  tone?: "default" | "good" | "critical";
  hint?: string;
}

export function StatTile({ label, value, tone = "default", hint }: StatTileProps) {
  return (
    <Card>
      <CardContent className="p-5">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p
          className={cn(
            "mt-1 text-2xl font-semibold tabular-nums",
            tone === "good" && "text-[color:var(--status-good)]",
            tone === "critical" && "text-[color:var(--status-critical)]",
          )}
        >
          {value}
        </p>
        {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}
