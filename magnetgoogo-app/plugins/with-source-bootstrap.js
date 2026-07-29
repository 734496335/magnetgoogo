const { withDangerousMod } = require('@expo/config-plugins');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const KEY_HEX = '0986e63db310b07bffd3ef35c94c8f6d91561588ddaf98db7faa7907106b34de';
const EXPECTED_ALL_RULES = 357;
const MIN_GREEN_RULES = 100;
const MIN_GREEN_POOLS = 40;
const TARGET_RELATIVE = path.join(
  'android',
  'app',
  'src',
  'main',
  'assets',
  'source-bootstrap',
  'bootstrap-sources.enc.json',
);

function extractRules(raw) {
  if (!raw || typeof raw !== 'object') return [];
  if (Array.isArray(raw)) return raw.filter((item) => item && typeof item === 'object');
  if (Array.isArray(raw.rulesets)) {
    return raw.rulesets.flatMap((ruleset) => (
      Array.isArray(ruleset?.rules)
        ? ruleset.rules.filter((item) => item && typeof item === 'object')
        : []
    ));
  }
  if (Array.isArray(raw.sources)) {
    return raw.sources.filter((item) => item && typeof item === 'object');
  }
  return [];
}

function summarizeCanonical(raw) {
  const rules = extractRules(raw);
  const green = rules.filter((rule) => rule?.health?.status === 'green');
  const pools = new Set(
    green
      .map((rule) => String(rule?.quality?.pool_id || '').trim())
      .filter(Boolean),
  );
  return {
    allRules: rules.length,
    greenRules: green.length,
    greenPools: pools.size,
  };
}

function assertExpectedInventory(audit) {
  if (audit.allRules !== EXPECTED_ALL_RULES) {
    throw new Error(
      `[with-source-bootstrap] canonical rule inventory mismatch: `
      + `${audit.allRules}; expected ${EXPECTED_ALL_RULES}`,
    );
  }
  if (audit.greenRules < MIN_GREEN_RULES || audit.greenPools < MIN_GREEN_POOLS) {
    throw new Error(
      `[with-source-bootstrap] qualified inventory below safety floor: `
      + `${audit.greenRules} green / ${audit.greenPools} pools; `
      + `minimum ${MIN_GREEN_RULES}/${MIN_GREEN_POOLS}`,
    );
  }
  if (audit.greenPools > audit.greenRules) {
    throw new Error('[with-source-bootstrap] green pool count exceeds green rule count');
  }
}

function loadConfig(configPath) {
  if (!fs.existsSync(configPath)) {
    return {
      source_expiry_hours: 72,
      source_schema_version: 1,
      min_version: '0.1.0',
    };
  }
  const value = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`[with-source-bootstrap] invalid config at ${configPath}`);
  }
  return value;
}

function decryptBootstrap(encoded) {
  const payload = JSON.parse(encoded);
  const key = Buffer.from(KEY_HEX, 'hex');
  const expectedMac = crypto
    .createHmac('sha256', key)
    .update(payload.ct, 'utf8')
    .digest('hex');
  if (!crypto.timingSafeEqual(Buffer.from(expectedMac, 'hex'), Buffer.from(payload.sig, 'hex'))) {
    throw new Error('[with-source-bootstrap] candidate HMAC roundtrip failed');
  }
  const decipher = crypto.createDecipheriv('aes-256-cbc', key, Buffer.from(payload.iv, 'hex'));
  const compressed = Buffer.concat([
    decipher.update(Buffer.from(payload.ct, 'base64')),
    decipher.final(),
  ]);
  const plaintext = payload.gz ? zlib.gunzipSync(compressed) : compressed;
  return JSON.parse(plaintext.toString('utf8'));
}

function buildSourceBootstrap({ sourcePath, configPath, now = new Date(), iv } = {}) {
  if (!sourcePath || !configPath) {
    throw new Error('[with-source-bootstrap] sourcePath and configPath are required');
  }
  const canonical = JSON.parse(fs.readFileSync(sourcePath, 'utf8'));
  const audit = summarizeCanonical(canonical);
  assertExpectedInventory(audit);

  const config = loadConfig(configPath);
  const expiryHours = Number(config.source_expiry_hours ?? 72);
  const schemaVersion = Number(config.source_schema_version ?? 1);
  const minAppVersion = String(config.min_version ?? '0.1.0');
  if (!Number.isFinite(expiryHours) || expiryHours < 48) {
    throw new Error(`[with-source-bootstrap] unsafe source_expiry_hours=${expiryHours}`);
  }

  const issuedAt = new Date(now);
  if (!Number.isFinite(issuedAt.getTime())) {
    throw new Error('[with-source-bootstrap] invalid build time');
  }
  const expiresAt = new Date(issuedAt.getTime() + expiryHours * 60 * 60 * 1000);
  const envelope = {
    schema_version: schemaVersion,
    issued_at: issuedAt.toISOString(),
    expires_at: expiresAt.toISOString(),
    min_app_version: minAppVersion,
    payload: canonical,
  };

  const plaintext = Buffer.from(JSON.stringify(envelope), 'utf8');
  const compressed = zlib.gzipSync(plaintext, { level: 9 });
  const key = Buffer.from(KEY_HEX, 'hex');
  const candidateIv = iv ? Buffer.from(iv) : crypto.randomBytes(16);
  if (candidateIv.length !== 16) {
    throw new Error('[with-source-bootstrap] IV must be 16 bytes');
  }
  const cipher = crypto.createCipheriv('aes-256-cbc', key, candidateIv);
  const ciphertext = Buffer.concat([cipher.update(compressed), cipher.final()]);
  const ct = ciphertext.toString('base64');
  const payload = {
    iv: candidateIv.toString('hex'),
    ct,
    sig: crypto.createHmac('sha256', key).update(ct, 'utf8').digest('hex'),
    gz: true,
  };
  const encoded = JSON.stringify(payload);

  const roundtrip = decryptBootstrap(encoded);
  const roundtripAudit = summarizeCanonical(roundtrip.payload);
  assertExpectedInventory(roundtripAudit);
  if (
    roundtrip.issued_at !== envelope.issued_at
    || roundtrip.expires_at !== envelope.expires_at
    || roundtrip.min_app_version !== envelope.min_app_version
  ) {
    throw new Error('[with-source-bootstrap] candidate envelope roundtrip mismatch');
  }

  return {
    encoded,
    audit,
    issuedAt: envelope.issued_at,
    expiresAt: envelope.expires_at,
    minAppVersion,
    bytes: Buffer.byteLength(encoded),
  };
}

function writeAtomic(targetPath, content) {
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  const temporary = `${targetPath}.${process.pid}.${Date.now()}.tmp`;
  try {
    fs.writeFileSync(temporary, content, 'utf8');
    fs.renameSync(temporary, targetPath);
  } finally {
    fs.rmSync(temporary, { force: true });
  }
}

function installSourceBootstrap(projectRoot) {
  const sourcePath = path.resolve(projectRoot, '..', 'sources.json');
  const configPath = path.resolve(projectRoot, '..', 'mg-data', 'config.json');
  const targetPath = path.resolve(projectRoot, TARGET_RELATIVE);
  const candidate = buildSourceBootstrap({ sourcePath, configPath });
  writeAtomic(targetPath, candidate.encoded);
  console.log(
    `[with-source-bootstrap] bundled ${candidate.audit.greenRules} green rules / `
      + `${candidate.audit.greenPools} pools (${candidate.bytes} bytes, expires ${candidate.expiresAt})`,
  );
  return { ...candidate, targetPath };
}

function withSourceBootstrap(config) {
  return withDangerousMod(config, [
    'android',
    async (modConfig) => {
      installSourceBootstrap(modConfig.modRequest.projectRoot);
      return modConfig;
    },
  ]);
}

module.exports = withSourceBootstrap;
module.exports.buildSourceBootstrap = buildSourceBootstrap;
module.exports.decryptBootstrap = decryptBootstrap;
module.exports.installSourceBootstrap = installSourceBootstrap;
module.exports.summarizeCanonical = summarizeCanonical;
