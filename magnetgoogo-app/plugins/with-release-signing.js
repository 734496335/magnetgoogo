const { withAppBuildGradle } = require('@expo/config-plugins');

const MARKER = '// MAGNETGOOGO_RELEASE_SIGNING_V1';

function applyReleaseSigning(contents) {
  if (contents.includes(MARKER)) return contents;

  const androidAnchor = 'android {\n';
  if (!contents.includes(androidAnchor)) {
    throw new Error('with-release-signing: android block was not found');
  }
  contents = contents.replace(
    androidAnchor,
    `${androidAnchor}    ${MARKER}\n    def releaseStorePassword = System.getenv("RELEASE_STORE_PASSWORD")\n    def releaseKeyAlias = System.getenv("RELEASE_KEY_ALIAS")\n    def releaseKeyPassword = System.getenv("RELEASE_KEY_PASSWORD")\n    def releaseKeystore = file('../../../releases/magnetgoogo-release-new.keystore')\n\n`,
  );

  const debugSigning = `    signingConfigs {\n        debug {\n            storeFile file('debug.keystore')\n            storePassword 'android'\n            keyAlias 'androiddebugkey'\n            keyPassword 'android'\n        }\n    }`;
  if (!contents.includes(debugSigning)) {
    throw new Error('with-release-signing: generated debug signing block was not found');
  }
  const signingBlock = `    signingConfigs {\n        debug {\n            storeFile file('debug.keystore')\n            storePassword 'android'\n            keyAlias 'androiddebugkey'\n            keyPassword 'android'\n        }\n        release {\n            if (!releaseKeystore.exists()) {\n                throw new GradleException("Release keystore is missing: " + releaseKeystore)\n            }\n            if (!releaseStorePassword || !releaseKeyAlias || !releaseKeyPassword) {\n                throw new GradleException("Release signing environment variables are incomplete")\n            }\n            storeFile releaseKeystore\n            storePassword releaseStorePassword\n            keyAlias releaseKeyAlias\n            keyPassword releaseKeyPassword\n        }\n    }`;
  contents = contents.replace(debugSigning, signingBlock);

  const releaseAnchor = `        release {\n            // Caution! In production, you need to generate your own keystore file.\n            // see https://reactnative.dev/docs/signed-apk-android.\n            signingConfig signingConfigs.debug`;
  if (contents.includes(releaseAnchor)) {
    contents = contents.replace(
      releaseAnchor,
      `        release {\n            signingConfig signingConfigs.release`,
    );
  } else {
    const releaseDebugSigning = `        release {\n            signingConfig signingConfigs.debug`;
    if (!contents.includes(releaseDebugSigning)) {
      throw new Error('with-release-signing: release signing assignment was not found');
    }
    contents = contents.replace(
      releaseDebugSigning,
      `        release {\n            signingConfig signingConfigs.release`,
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
