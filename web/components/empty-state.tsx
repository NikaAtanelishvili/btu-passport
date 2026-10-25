// Shown by every list and detail page when there is nothing to show.
import { Card, CardContent } from "@/components/ui/card";

export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <Card className="border-[1.5px] border-dashed border-foreground ring-0">
      <CardContent className="py-8 text-center text-base text-muted-foreground">{children}</CardContent>
    </Card>
  );
}
