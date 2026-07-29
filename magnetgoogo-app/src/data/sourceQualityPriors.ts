export interface PoolQualityPrior {
  global: number;
  latin: number;
  cjk: number;
  code: number;
  mixed: number;
  coverage: number;
}

export interface SourceQualityPriorsFile {
  schema_version: number;
  generated_at: string;
  trusted: boolean;
  evidence: {
    mode: string;
    device: string;
    bait_labels: string[];
    host_count: number;
    pool_count: number;
    static_sha256: string;
    relevance_threshold: number;
  };
  pools: Record<string, PoolQualityPrior>;
}

export const SOURCE_QUALITY_PRIORS: SourceQualityPriorsFile = {
  schema_version: 1,
  generated_at: '2026-07-27T21:48:14+08:00',
  trusted: true,
  evidence: {
    mode: 'exhaustive-benchmark',
    device: 'a1ea223a',
    bait_labels: [
      'EN movie',
      'ZH movie',
      'EN anime',
      'ZH anime',
      'EN series',
      'ZH series',
      'Software',
      'Code title',
    ],
    host_count: 233,
    pool_count: 53,
    static_sha256: '7839ce02b68230261d6a09f4664ea033115bd4a49be4e8b700f764a045422259',
    relevance_threshold: 30,
  },
  pools: {
    btsow: { global: 98.43, latin: 98.46, cjk: 98.31, code: 98.70, mixed: 98.38, coverage: 1.0 },
    knaben: { global: 89.20, latin: 96.35, cjk: 77.11, code: 96.89, mixed: 86.73, coverage: 1.0 },
    berrl: { global: 70.95, latin: 79.52, cjk: 63.10, code: 60.24, mixed: 71.31, coverage: 1.0 },
    movih: { global: 70.32, latin: 78.52, cjk: 62.86, code: 59.94, mixed: 70.69, coverage: 1.0 },
    tpb: { global: 67.80, latin: 99.73, cjk: 14.59, code: 99.71, mixed: 57.16, coverage: 0.625 },
    wuji: { global: 64.06, latin: 60.98, cjk: 67.09, code: 67.27, mixed: 64.03, coverage: 1.0 },
    'mag-index': { global: 63.94, latin: 61.23, cjk: 66.77, code: 66.34, mixed: 64.00, coverage: 1.0 },
    '0cili': { global: 63.85, latin: 61.03, cjk: 66.69, code: 66.62, mixed: 63.86, coverage: 1.0 },
    'seed8/zzb': { global: 59.17, latin: 67.47, cjk: 45.30, code: 67.54, mixed: 56.38, coverage: 0.875 },
    cililianjie: { global: 58.11, latin: 58.44, cjk: 54.83, code: 66.65, mixed: 56.63, coverage: 1.0 },
    cilisousuo: { global: 58.09, latin: 58.57, cjk: 54.62, code: 66.61, mixed: 56.59, coverage: 1.0 },
    rutor: { global: 55.61, latin: 97.81, cjk: 13.47, code: 13.26, mixed: 55.64, coverage: 0.5 },
    xiongmao: { global: 54.23, latin: 60.74, cjk: 49.11, code: 43.55, mixed: 54.92, coverage: 1.0 },
    laowang: { global: 53.99, latin: 60.32, cjk: 48.92, code: 43.82, mixed: 54.62, coverage: 1.0 },
    kd705: { global: 51.93, latin: 49.98, cjk: 39.00, code: 98.50, mixed: 44.49, coverage: 0.75 },
    nyaa: { global: 49.43, latin: 48.35, cjk: 62.74, code: 13.81, mixed: 55.55, coverage: 0.5 },
    foxs: { global: 41.03, latin: 45.17, cjk: 33.25, code: 47.82, mixed: 39.21, coverage: 0.875 },
    '1337x': { global: 40.72, latin: 67.20, cjk: 14.26, code: 14.21, mixed: 40.73, coverage: 0.5 },
    lemon: { global: 39.33, latin: 32.28, cjk: 42.31, code: 58.54, mixed: 37.30, coverage: 0.625 },
    yts: { global: 32.40, latin: 51.50, cjk: 13.34, code: 13.17, mixed: 32.42, coverage: 0.375 },
    'proxyit.de': { global: 18.59, latin: 14.62, cjk: 14.58, code: 46.50, mixed: 14.60, coverage: 0.125 },
    'unblock-portal': { global: 14.98, latin: 14.98, cjk: 14.98, code: 14.98, mixed: 14.98, coverage: 0.0 },
    'cilibao/clb': { global: 14.96, latin: 14.98, cjk: 14.94, code: 14.98, mixed: 14.96, coverage: 0.0 },
    glodls: { global: 14.96, latin: 14.93, cjk: 14.98, code: 14.98, mixed: 14.96, coverage: 0.0 },
    'cilimao/clm': { global: 14.61, latin: 14.62, cjk: 14.64, code: 14.48, mixed: 14.63, coverage: 0.0 },
    sobt: { global: 14.28, latin: 14.34, cjk: 14.44, code: 13.56, mixed: 14.39, coverage: 0.0 },
    ciligou: { global: 14.21, latin: 14.13, cjk: 14.19, code: 14.58, mixed: 14.16, coverage: 0.0 },
    'torrents-csv': { global: 14.05, latin: 14.24, cjk: 13.84, code: 13.91, mixed: 14.04, coverage: 0.0 },
    rarbg: { global: 13.95, latin: 14.00, cjk: 13.86, code: 14.02, mixed: 13.93, coverage: 0.0 },
    animetosho: { global: 13.57, latin: 13.65, cjk: 13.42, code: 13.73, mixed: 13.54, coverage: 0.0 },
    torrentgalaxy: { global: 13.47, latin: 13.48, cjk: 13.42, code: 13.60, mixed: 13.45, coverage: 0.0 },
    bitsearch: { global: 12.99, latin: 13.27, cjk: 12.69, code: 12.74, mixed: 12.98, coverage: 0.0 },
    btmulu: { global: 12.91, latin: 13.04, cjk: 12.78, code: 12.81, mixed: 12.91, coverage: 0.0 },
    magnetdl: { global: 12.70, latin: 12.61, cjk: 12.75, code: 12.93, mixed: 12.68, coverage: 0.0 },
    meijumi: { global: 11.33, latin: 11.16, cjk: 11.53, code: 11.44, mixed: 11.34, coverage: 0.0 },
    mikan: { global: 10.94, latin: 11.33, cjk: 9.59, code: 13.46, mixed: 10.46, coverage: 0.0 },
    fitgirl: { global: 9.60, latin: 7.48, cjk: 11.57, code: 12.19, mixed: 9.53, coverage: 0.0 },
    '6v-dytt': { global: 9.23, latin: 9.56, cjk: 7.22, code: 13.92, mixed: 8.39, coverage: 0.0 },
    '101mag': { global: 1.99, latin: 1.99, cjk: 1.98, code: 1.99, mixed: 1.98, coverage: 0.0 },
    dmhy: { global: 1.99, latin: 1.99, cjk: 1.99, code: 1.99, mixed: 1.99, coverage: 0.0 },
    'solo:javbus.com': { global: 1.99, latin: 1.99, cjk: 1.98, code: 1.99, mixed: 1.98, coverage: 0.0 },
    'solo:lulutang.com': { global: 1.99, latin: 1.98, cjk: 1.99, code: 1.99, mixed: 1.98, coverage: 0.0 },
    'solo:u3c3.com': { global: 1.99, latin: 1.99, cjk: 1.99, code: 1.99, mixed: 1.99, coverage: 0.0 },
    'solo:yhg007.com': { global: 1.99, latin: 1.99, cjk: 1.98, code: 1.99, mixed: 1.98, coverage: 0.0 },
    btdig: { global: 1.98, latin: 1.98, cjk: 1.98, code: 1.99, mixed: 1.98, coverage: 0.0 },
    'solo:0mag.net': { global: 1.98, latin: 1.99, cjk: 1.98, code: 1.99, mixed: 1.98, coverage: 0.0 },
    tokyotosho: { global: 1.94, latin: 1.90, cjk: 1.98, code: 1.99, mixed: 1.94, coverage: 0.0 },
    'cnbrand:cilimo': { global: 1.92, latin: 1.85, cjk: 1.98, code: 1.99, mixed: 1.92, coverage: 0.0 },
    'solo:jzcilifa1.shop': { global: 1.92, latin: 1.85, cjk: 1.99, code: 1.99, mixed: 1.92, coverage: 0.0 },
    'solo:m.zhongzidi.com': { global: 1.83, latin: 1.68, cjk: 1.98, code: 1.99, mixed: 1.83, coverage: 0.0 },
    'solo:clmmbt.com': { global: 1.68, latin: 1.37, cjk: 1.99, code: 1.99, mixed: 1.68, coverage: 0.0 },
    'solo:rrjav.com': { global: 0.0, latin: 0.0, cjk: 0.0, code: 0.0, mixed: 0.0, coverage: 0.0 },
    uindex: { global: 0.0, latin: 0.0, cjk: 0.0, code: 0.0, mixed: 0.0, coverage: 0.0 },
  },
};
