"use client"

import React, { useEffect } from 'react';
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react';

export default function Toast({ message, type = 'info', duration = 3000, onClose }) {
  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        onClose();
      }, duration);
      return () => clearTimeout(timer);
    }
  }, [duration, onClose]);

  const config = {
    success: {
      bg: 'bg-green-50 border-green-200',
      text: 'text-green-800',
      icon: CheckCircle,
      iconColor: 'text-green-600'
    },
    error: {
      bg: 'bg-red-50 border-red-200',
      text: 'text-red-800',
      icon: AlertCircle,
      iconColor: 'text-red-600'
    },
    warning: {
      bg: 'bg-yellow-50 border-yellow-200',
      text: 'text-yellow-800',
      icon: AlertTriangle,
      iconColor: 'text-yellow-600'
    },
    info: {
      bg: 'bg-blue-50 border-blue-200',
      text: 'text-blue-800',
      icon: Info,
      iconColor: 'text-blue-600'
    }
  };

  const { bg, text, icon: Icon, iconColor } = config[type];

  return (
    <div className={`fixed top-4 right-4 z-50 max-w-md animate-slide-in-right`}>
      <div className={`${bg} border-2 rounded-lg shadow-lg p-4 flex items-start gap-3`}>
        <Icon className={`w-5 h-5 ${iconColor} shrink-0 mt-0.5`} />
        <p className={`${text} flex-1 text-sm font-medium`}>{message}</p>
        <button
          onClick={onClose}
          className={`${text} hover:opacity-70 shrink-0`}
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

// Toast Container for managing multiple toasts
export function ToastContainer({ toasts, removeToast }) {
  return (
    <div className="fixed top-4 right-4 z-50 space-y-2">
      {toasts.map((toast) => (
        <Toast
          key={toast.id}
          message={toast.message}
          type={toast.type}
          duration={toast.duration}
          onClose={() => removeToast(toast.id)}
        />
      ))}
    </div>
  );
}