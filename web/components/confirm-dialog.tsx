"use client";

// Every destructive or irreversible action asks first.
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

export function ConfirmDialog({
  trigger,
  title,
  description,
  confirmLabel,
  onConfirm,
  disabled,
  children,
}: {
  /** The trigger element (e.g. a Button), rendered with `children` as its label. */
  trigger: React.ReactElement;
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger render={trigger} disabled={disabled}>
        {children}
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogCancel variant="default" onClick={onConfirm}>
            {confirmLabel}
          </AlertDialogCancel>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

