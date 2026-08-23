// src/components/ServiceBadge.tsx
import React from 'react';
import { StatusResponse } from '@/types';

interface ServiceBadgeProps {
  quotaStatus: StatusResponse | null;
  isBackendOffline: boolean;
}

export const ServiceBadge: React.FC<ServiceBadgeProps> = ({ quotaStatus, isBackendOffline }) => {
  if (isBackendOffline) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700 ring-1 ring-inset ring-rose-600/20">
        <span className="h-1.5 w-1.5 rounded-full bg-rose-500 animate-pulse" />
        Service Temporarily Unavailable
      </span>
    );
  }

  // Sprawdzamy czy limity we wszystkich dostępnych trybach zostały wyczerpane
  const isExceeded =
    quotaStatus?.modes &&
    Object.values(quotaStatus.modes).length > 0 &&
    Object.values(quotaStatus.modes).every((mode) => (mode?.remaining_rpd ?? 0) <= 0);

  if (isExceeded) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-600/20">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
        Daily Requests Exceeded
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
      Service Available
    </span>
  );
};