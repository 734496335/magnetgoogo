import { Search, X } from 'lucide-react';

export function SearchField({
  value,
  placeholder,
  onChange,
  onClear,
  large = false,
}: {
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  onClear?: () => void;
  large?: boolean;
}) {
  return (
    <div
      className={
        large
          ? 'relative flex h-[66px] w-full items-center rounded-[30px] bg-white/80 px-7 shadow-[0_2px_6px_rgba(0,0,0,0.04),0_12px_32px_rgba(180,170,155,0.24)] ring-1 ring-white/60 backdrop-blur-xl'
          : 'relative flex h-[52px] items-center rounded-[23px] bg-white/80 px-4 shadow-[0_2px_6px_rgba(0,0,0,0.03),0_10px_28px_rgba(180,170,155,0.20)] ring-1 ring-white/60 backdrop-blur-xl'
      }
    >
      <Search
        className={large ? 'relative z-10 h-6 w-6 text-[#858da0]' : 'relative z-10 h-5 w-5 text-[#858da0]'}
        strokeWidth={large ? 1.9 : 2}
      />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className={
          large
            ? 'relative z-10 ml-4 flex-1 border-none bg-transparent text-[17px] font-medium text-[#5d6578] outline-none placeholder:text-[#a0a8b8]'
            : 'relative z-10 ml-3 flex-1 border-none bg-transparent text-[16px] font-medium text-[#5d6578] outline-none placeholder:text-[#a0a8b8]'
        }
      />
      {onClear && value ? (
        <button
          type="button"
          onClick={onClear}
          className="relative z-10 flex h-8 w-8 items-center justify-center rounded-full text-[#97a0b1] transition hover:bg-[#f5f7fb]"
        >
          <X className="h-4 w-4" strokeWidth={2.2} />
        </button>
      ) : null}
    </div>
  );
}
