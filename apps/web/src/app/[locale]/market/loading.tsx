export default function Loading() {
  return (
    <div className="grid gap-3" aria-busy="true">
      <div className="h-14 animate-pulse rounded-full bg-slate-200/80" />
      <div className="grid grid-cols-2 gap-3">
        <div className="h-36 animate-pulse rounded-3xl bg-slate-200/80" />
        <div className="h-36 animate-pulse rounded-3xl bg-slate-200/80" />
        <div className="h-36 animate-pulse rounded-3xl bg-slate-200/80" />
        <div className="h-36 animate-pulse rounded-3xl bg-slate-200/80" />
      </div>
    </div>
  );
}
