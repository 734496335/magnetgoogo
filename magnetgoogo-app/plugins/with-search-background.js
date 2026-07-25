const fs = require('node:fs');
const path = require('node:path');
const {
  AndroidConfig,
  withAndroidManifest,
  withDangerousMod,
  withMainApplication,
} = require('@expo/config-plugins');

const TEMPLATE_DIR = path.join(__dirname, 'search-background');
const KOTLIN_FILES = [
  'SearchKeepAlivePackage.kt',
  'SearchKeepAliveModule.kt',
  'SearchKeepAliveService.kt',
  'SearchHeadlessService.kt',
];

function ensurePermission(manifest, name) {
  manifest.manifest['uses-permission'] = manifest.manifest['uses-permission'] || [];
  const permissions = manifest.manifest['uses-permission'];
  if (!permissions.some((item) => item?.$?.['android:name'] === name)) {
    permissions.push({ $: { 'android:name': name } });
  }
}

function ensureService(application, name, attrs) {
  application.service = application.service || [];
  const existing = application.service.find((item) => item?.$?.['android:name'] === name);
  if (existing) {
    existing.$ = { ...existing.$, ...attrs, 'android:name': name };
    return;
  }
  application.service.push({ $: { 'android:name': name, ...attrs } });
}

function withSearchBackgroundManifest(config) {
  return withAndroidManifest(config, (modConfig) => {
    const manifest = modConfig.modResults;
    for (const permission of [
      'android.permission.FOREGROUND_SERVICE',
      'android.permission.FOREGROUND_SERVICE_DATA_SYNC',
      'android.permission.POST_NOTIFICATIONS',
      'android.permission.WAKE_LOCK',
    ]) {
      ensurePermission(manifest, permission);
    }

    const application = AndroidConfig.Manifest.getMainApplicationOrThrow(manifest);
    ensureService(application, '.SearchKeepAliveService', {
      'android:exported': 'false',
      'android:foregroundServiceType': 'dataSync',
      'android:stopWithTask': 'false',
    });
    ensureService(application, '.SearchHeadlessService', {
      'android:exported': 'false',
      'android:stopWithTask': 'false',
    });
    return modConfig;
  });
}

function withSearchBackgroundMainApplication(config) {
  return withMainApplication(config, (modConfig) => {
    if (modConfig.modResults.language !== 'kt') {
      throw new Error('Search background plugin requires a Kotlin MainApplication');
    }
    const registration = 'add(SearchKeepAlivePackage())';
    if (!modConfig.modResults.contents.includes(registration)) {
      const anchor = 'PackageList(this).packages.apply {';
      if (!modConfig.modResults.contents.includes(anchor)) {
        throw new Error('Unable to locate PackageList apply block in MainApplication.kt');
      }
      modConfig.modResults.contents = modConfig.modResults.contents.replace(
        anchor,
        `${anchor}\n              ${registration}`,
      );
    }
    return modConfig;
  });
}

function withSearchBackgroundSources(config) {
  return withDangerousMod(config, ['android', async (modConfig) => {
    const packageName = modConfig.android?.package;
    if (!packageName) throw new Error('expo.android.package is required');

    const javaDir = path.join(
      modConfig.modRequest.projectRoot,
      'android',
      'app',
      'src',
      'main',
      'java',
      ...packageName.split('.'),
    );
    fs.mkdirSync(javaDir, { recursive: true });

    for (const fileName of KOTLIN_FILES) {
      const templatePath = path.join(TEMPLATE_DIR, `${fileName}.template`);
      const outputPath = path.join(javaDir, fileName);
      const contents = fs.readFileSync(templatePath, 'utf8').replaceAll('__PACKAGE__', packageName);
      fs.writeFileSync(outputPath, contents);
    }
    return modConfig;
  }]);
}

module.exports = function withSearchBackground(config) {
  config = withSearchBackgroundManifest(config);
  config = withSearchBackgroundMainApplication(config);
  config = withSearchBackgroundSources(config);
  return config;
};
