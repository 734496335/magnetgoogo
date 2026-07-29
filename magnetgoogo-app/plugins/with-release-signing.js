const { withAppBuildGradle } = require('@expo/config-plugins');

const MARKER = '// MAGNETGOOGO_RELEASE_SIGNING_V1';

function applyReleaseSigning(contents) {
  const alreadyCurrent =
    contents.includes(MARKER) &&
    contents.includes('def releaseSigningRequested =') &&
    contents.includes('if (releaseSigningRequested && !releaseKeystore.exists())') &&
    contents.includes("applicationIdSuffix '.debug'");
  if (alreadyCurrent) return contents;

  const newline = contents.includes('\r\n') ? '\r\n' : '\n';
  const legacyHeaderPattern = /\s*\/\/ MAGNETGOOGO_RELEASE_SIGNING_V1\r?\n\s*def releaseStorePassword[^\r\n]*\r?\n\s*def releaseKeyAlias[^\r\n]*\r?\n\s*def releaseKeyPassword[^\r\n]*\r?\n\s*def releaseKeystore[^\r\n]*\r?\n(?:\s*def releaseSigningRequested[^\r\n]*\r?\n)?/;
  contents = contents.replace(legacyHeaderPattern, newline);
  const androidPattern = /android\s*\{[ \t]*(?:\r?\n)?/;
  if (!androidPattern.test(contents)) {
    throw new Error('with-release-signing: android block was not found');
  }

  const androidHeader = [
    'android {',
    `    ${MARKER}`,
    '    def releaseStorePassword = System.getenv("RELEASE_STORE_PASSWORD")',
    '    def releaseKeyAlias = System.getenv("RELEASE_KEY_ALIAS")',
    '    def releaseKeyPassword = System.getenv("RELEASE_KEY_PASSWORD")',
    "    def releaseKeystore = file('../../../releases/magnetgoogo-release-new.keystore')",
    '    def releaseSigningRequested = gradle.startParameter.taskNames.any { it.toLowerCase().contains("release") }',
    '',
  ].join(newline);
  contents = contents.replace(androidPattern, `${androidHeader}${newline}`);

  const signingBlock = [
    '    signingConfigs {',
    '        debug {',
    "            storeFile file('debug.keystore')",
    "            storePassword 'android'",
    "            keyAlias 'androiddebugkey'",
    "            keyPassword 'android'",
    '        }',
    '        release {',
    '            if (releaseSigningRequested && !releaseKeystore.exists()) {',
    '                throw new GradleException("Release keystore is missing: " + releaseKeystore)',
    '            }',
    '            if (releaseSigningRequested && (!releaseStorePassword || !releaseKeyAlias || !releaseKeyPassword)) {',
    '                throw new GradleException("Release signing environment variables are incomplete")',
    '            }',
    '            storeFile releaseKeystore',
    '            storePassword releaseStorePassword ?: ""',
    '            keyAlias releaseKeyAlias ?: ""',
    '            keyPassword releaseKeyPassword ?: ""',
    '        }',
    '    }',
  ].join(newline);

  // Expo prebuild can reuse a native directory that already contains an older
  // release signing block. Replace the complete signing section instead of
  // requiring the pristine debug-only template.
  const signingSectionPattern = /\s{4}signingConfigs\s*\{[\s\S]*?\r?\n\s{4}\}\s*\r?\n\s{4}buildTypes\s*\{/;
  if (!signingSectionPattern.test(contents)) {
    throw new Error('with-release-signing: generated signing/buildTypes blocks were not found');
  }
  contents = contents.replace(
    signingSectionPattern,
    `${signingBlock}${newline}    buildTypes {`,
  );

  const releaseAssignmentPattern = /(buildTypes\s*\{[\s\S]*?\r?\n\s{8}release\s*\{[\s\S]*?signingConfig\s+)signingConfigs\.(?:debug|release)/;
  if (!releaseAssignmentPattern.test(contents)) {
    throw new Error('with-release-signing: release signing assignment was not found');
  }
  contents = contents.replace(releaseAssignmentPattern, '$1signingConfigs.release');

  const debugBuildTypePattern = /(buildTypes\s*\{[\s\S]*?\r?\n\s{8}debug\s*\{\r?\n)([\s\S]*?\r?\n\s{8}\})/;
  if (!debugBuildTypePattern.test(contents)) {
    throw new Error('with-release-signing: debug build type was not found');
  }
  if (!contents.includes("applicationIdSuffix '.debug'")) {
    contents = contents.replace(
      debugBuildTypePattern,
      `$1            applicationIdSuffix '.debug'${newline}$2`,
    );
  }
  return contents;
}

module.exports = function withReleaseSigning(config) {
  return withAppBuildGradle(config, (gradleConfig) => {
    if (gradleConfig.modResults.language !== 'groovy') {
      throw new Error('with-release-signing supports Groovy build.gradle only');
    }
    gradleConfig.modResults.contents = applyReleaseSigning(gradleConfig.modResults.contents);
    return gradleConfig;
  });
};

module.exports.applyReleaseSigning = applyReleaseSigning;
