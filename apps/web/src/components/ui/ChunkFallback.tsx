export function ChunkFallback() {
  return (
    <div role="status" aria-busy="true" className="grid min-w-0 gap-3">
      <div className="h-8 w-2/3 max-w-xs animate-pulse bg-ink/10" />
      <div className="h-36 animate-pulse bg-ink/10" />
      <div className="h-36 animate-pulse bg-ink/10" />
    </div>
  );
}
