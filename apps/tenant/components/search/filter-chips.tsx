"use client";

import { Badge } from "@rentfit/ui/components/badge";
import { X } from "lucide-react";

import type { Chip } from "@/lib/search";

/** The thread's active filters; removing one sends a filter patch. */
export function FilterChips({ chips, onRemove, disabled }: { chips: Chip[]; onRemove: (field: string) => void; disabled?: boolean }) {
  if (!chips.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5" aria-label="Active filters">
      {chips.map((c) => (
        <Badge key={c.field} variant="secondary" className="gap-1 py-1 pl-2.5 pr-1">
          {c.label}
          <button
            type="button"
            disabled={disabled}
            onClick={() => onRemove(c.field)}
            className="rounded-full p-0.5 hover:bg-background/60 disabled:opacity-50"
            aria-label={`Remove ${c.label}`}
          >
            <X className="size-3" />
          </button>
        </Badge>
      ))}
    </div>
  );
}
