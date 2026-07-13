import React from 'react';
import { ConfirmationDialog } from './ConfirmationDialog';

interface UnsavedChangesDialogProps {
  isOpen: boolean;
  onStay: () => void;
  onDiscard: () => void;
}

export function UnsavedChangesDialog({ isOpen, onStay, onDiscard }: UnsavedChangesDialogProps) {
  return (
    <ConfirmationDialog
      isOpen={isOpen}
      title="Unsaved changes"
      description="You have unsaved changes. Leave without saving?"
      confirmText="Discard changes"
      cancelText="Stay"
      onConfirm={onDiscard}
      onCancel={onStay}
      isDestructive={false}
    />
  );
}
