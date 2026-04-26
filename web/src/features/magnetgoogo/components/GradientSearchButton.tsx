import { ArrowRight } from 'lucide-react';

export function GradientSearchButton({
  disabled,
  searching,
}: {
  disabled: boolean;
  searching: boolean;
}) {
  return (
    <div className="relative w-full max-w-[280px]">
      {/* Colorful animated shadow — blurred clone behind the button */}
      <div
        className="btn-color-flow btn-shadow-flow pointer-events-none absolute inset-0 rounded-full opacity-50 blur-xl"
        style={{ background: 'linear-gradient(90deg,#4facfe 0%,#a855f7 25%,#ff6b9d 48%,#ffa751 72%,#7bf48c 100%)', backgroundSize: '200% 100%' }}
      />
      <button
        type="submit"
        disabled={disabled}
        className="btn-color-flow group relative flex h-[52px] w-full items-center justify-center overflow-hidden rounded-full bg-[linear-gradient(90deg,#4facfe,#a855f7,#ff6b9d,#ffa751,#7bf48c,#4facfe)] px-6 text-[15px] font-semibold tracking-[0.01em] text-white shadow-[inset_0_2px_0_rgba(255,255,255,0.55),inset_0_-2px_4px_rgba(0,0,0,0.08)] transition duration-300 hover:translate-y-[-1px] disabled:cursor-not-allowed disabled:opacity-75"
      >
        <span className="relative grid w-full grid-cols-[1fr_auto_1fr] items-center">
          <span className="col-start-2 justify-self-center">{searching ? '搜索中...' : '搜索磁力'}</span>
          <ArrowRight
            className="col-start-3 mr-1 h-6 w-6 justify-self-end transition-transform duration-300 group-hover:translate-x-1"
            strokeWidth={2.2}
          />
        </span>
      </button>
    </div>
  );
}
