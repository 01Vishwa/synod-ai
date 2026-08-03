import React, { useEffect, useRef } from 'react';

interface ConfirmationDialogProps {
  isOpen: boolean;
  title: string;
  description: React.ReactNode;
  confirmText: string;
  cancelText?: string;
  onConfirm: () => void;
  onCancel: () => void;
  isDestructive?: boolean;
}

export function ConfirmationDialog({
  isOpen,
  title,
  description,
  confirmText,
  cancelText = 'Cancel',
  onConfirm,
  onCancel,
  isDestructive = true
}: ConfirmationDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (isOpen && !dialog.open) {
      dialog.showModal();
    } else if (!isOpen && dialog.open) {
      dialog.close();
    }
  }, [isOpen]);

  useEffect(() => {
    const dialog = dialogRef.current;
    const handleCancel = (e: Event) => {
      e.preventDefault();
      onCancel();
    };
    dialog?.addEventListener('cancel', handleCancel);
    return () => dialog?.removeEventListener('cancel', handleCancel);
  }, [onCancel]);

  return (
    <dialog
      ref={dialogRef}
      style={{
        padding: 'var(--space-6)',
        border: '1px solid var(--color-border-strong)',
        borderRadius: 'var(--radius-md)',
        background: 'var(--color-surface)',
        color: 'var(--color-text)',
        maxWidth: '400px',
        boxShadow: '0 10px 25px rgba(0,0,0,0.2)',
        margin: 'auto'
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <h3 style={{ margin: 0, fontSize: 'var(--text-lg)' }}>{title}</h3>
        <div style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-base)', lineHeight: 1.5 }}>
          {description}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)', marginTop: 'var(--space-2)' }}>
          <button 
            type="button" 
            className="btn-ghost" 
            onClick={onCancel}
          >
            {cancelText}
          </button>
          <button 
            type="button" 
            className="btn-primary" 
            onClick={onConfirm}
            style={isDestructive ? { background: 'var(--color-primary)', color: 'var(--color-primary-fg)' } : undefined}
          >
            {confirmText}
          </button>
        </div>
      </div>
      <style dangerouslySetInnerHTML={{ __html: `
        dialog::backdrop {
          background: var(--color-overlay);
          backdrop-filter: blur(2px);
        }
      `}} />
    </dialog>
  );
}
