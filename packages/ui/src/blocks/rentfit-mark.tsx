import { cn } from "@rentfit/ui/lib/utils";

/** Brand mark: a house outline on the primary colour. Inline SVG, so no asset is needed. */
export function RentfitMark({ size = 64, className }: { size?: number; className?: string }) {
  return (
    <svg
      role="img"
      aria-label="RentFit"
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={cn("rounded-xl shadow-sm", className)}
    >
      <rect width="64" height="64" rx="14" className="fill-primary" />
      <path
        d="M16 31 32 18l16 13v15a2 2 0 0 1-2 2H37V37h-10v11H18a2 2 0 0 1-2-2Z"
        className="fill-none stroke-primary-foreground"
        strokeWidth="3.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}
