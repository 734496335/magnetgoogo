export function DeviceFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative mx-auto w-full max-w-[424px] rounded-[52px] border border-white/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.88),rgba(255,255,255,0.72))] p-[11px] shadow-[0_36px_140px_rgba(201,193,182,0.36)] backdrop-blur-2xl">
      <div className="absolute inset-[4px] rounded-[48px] border border-[rgba(255,255,255,0.92)]" />
      <div className="absolute inset-[8px] rounded-[45px] border border-[rgba(238,234,227,0.95)]" />
      <div className="absolute inset-[13px] rounded-[41px] border border-[rgba(255,255,255,0.9)]" />
      <div className="pointer-events-none absolute inset-x-10 top-[14px] h-10 rounded-full bg-[linear-gradient(180deg,rgba(255,255,255,0.72),rgba(255,255,255,0))] blur-md" />
      <div className="relative overflow-hidden rounded-[40px] bg-[linear-gradient(180deg,#fffefc_0%,#fdfbf8_58%,#fdfcf9_100%)] px-6 pb-6 pt-4">
        <StatusBar />
        {children}
      </div>
    </div>
  );
}

function StatusBar() {
  return (
    <div className="mb-8 flex items-center justify-between px-2 text-[15px] font-semibold text-[#111111]">
      <span>9:41</span>
      <div className="flex items-center gap-[6px]">
        <span className="flex items-end gap-[2px]">
          <span className="h-[5px] w-[3px] rounded-sm bg-[#111111]" />
          <span className="h-[7px] w-[3px] rounded-sm bg-[#111111]" />
          <span className="h-[9px] w-[3px] rounded-sm bg-[#111111]" />
          <span className="h-[11px] w-[3px] rounded-sm bg-[#111111]" />
        </span>
        <svg className="h-[11px] w-[15px]" viewBox="0 0 16 12" fill="none">
          <path d="M0.8 4.2a9.4 9.4 0 0 1 14.4 0" stroke="#111111" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M3.6 7a5.8 5.8 0 0 1 8.8 0" stroke="#111111" strokeWidth="1.6" strokeLinecap="round" />
          <circle cx="8" cy="10.5" r="1.2" fill="#111111" />
        </svg>
        <span className="relative block h-[11px] w-[20px] rounded-[3px] border-[1.5px] border-[#111111]">
          <span className="absolute inset-[2px] rounded-[1px] bg-[#111111]" />
          <span className="absolute -right-[3px] top-[2.5px] h-[4px] w-[2px] rounded-r-sm bg-[#111111]" />
        </span>
      </div>
    </div>
  );
}
