// Shown by every list and detail page when there is nothing to show.
import { Card, CardContent } from "@/components/ui/card";

export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="py-6 text-center text-sm text-muted-foreground">{children}</CardContent>
    </Card>
  );
}
