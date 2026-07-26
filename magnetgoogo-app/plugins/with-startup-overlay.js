const fs = require('node:fs');
const path = require('node:path');
const {
  withAppBuildGradle,
  withDangerousMod,
  withMainApplication,
} = require('@expo/config-plugins');

const TEMPLATE_DIR = path.join(__dirname, 'startup-overlay');
const SOURCE_FILES = [
  'MainActivity.kt',
  'StartupOverlayView.kt',
  'StartupOverlayModule.kt',
  'StartupOverlayPackage.kt',
];

function withStartupOverlayMainApplication(config) {
  return withMainApplication(config, (modConfig) => {
    if (modConfig.modResults.language !== 'kt') {
      throw new Error('Startup overlay plugin requires a Kotlin MainApplication');
    }
    let contents = modConfig.modResults.contents;
    const registration = 'add(StartupOverlayPackage())';
    if (!contents.includes(registration)) {
      const anchor = 'PackageList(this).packages.apply {';
      if (!contents.includes(anchor)) {
        throw new Error('Unable to locate PackageList apply block in MainApplication.kt');
      }
      contents = contents.replace(anchor, `${anchor}\n              ${registration}`);
    }

    const defaultDeveloperSupport =
      'override fun getUseDeveloperSupport(): Boolean = BuildConfig.DEBUG';
    const standaloneDeveloperSupport =
      'override fun getUseDeveloperSupport(): Boolean = BuildConfig.DEBUG && !BuildConfig.STANDALONE_DEBUG';
    if (contents.includes(defaultDeveloperSupport)) {
      contents = contents.replace(defaultDeveloperSupport, standaloneDeveloperSupport);
    } else if (!contents.includes(standaloneDeveloperSupport)) {
      throw new Error('Unable to configure standalone Debug developer support');
    }

    modConfig.modResults.contents = contents;
    return modConfig;
  });
}

function withStandaloneDebugGradle(config) {
  return withAppBuildGradle(config, (modConfig) => {
    if (modConfig.modResults.language !== 'groovy') {
      throw new Error('Startup overlay plugin requires a Groovy app/build.gradle');
    }
    let contents = modConfig.modResults.contents;

    const standaloneDefinition =
      "def standaloneDebug = (findProperty('standaloneDebug') ?: 'false').toBoolean()";
    if (!contents.includes(standaloneDefinition)) {
      const projectRootLine =
        'def projectRoot = rootDir.getAbsoluteFile().getParentFile().getAbsolutePath()';
      if (!contents.includes(projectRootLine)) {
        throw new Error('Unable to locate projectRoot in app/build.gradle');
      }
      contents = contents.replace(
        projectRootLine,
        `${projectRootLine}\n${standaloneDefinition}`,
      );
    }

    const standaloneVariants =
      'debuggableVariants = standaloneDebug ? [] : ["debug"]';
    if (!contents.includes(standaloneVariants)) {
      const bundleCommand = 'bundleCommand = "export:embed"';
      if (!contents.includes(bundleCommand)) {
        throw new Error('Unable to locate React Native bundleCommand in app/build.gradle');
      }
      contents = contents.replace(
        bundleCommand,
        `${bundleCommand}\n    ${standaloneVariants}`,
      );
    }

    const standaloneBuildConfig =
      'buildConfigField "boolean", "STANDALONE_DEBUG", "${standaloneDebug}"';
    if (!contents.includes(standaloneBuildConfig)) {
      const releaseLevelField =
        'buildConfigField "String", "REACT_NATIVE_RELEASE_LEVEL", "\\\"${findProperty(\'reactNativeReleaseLevel\') ?: \'stable\'}\\\""';
      if (!contents.includes(releaseLevelField)) {
        throw new Error('Unable to locate defaultConfig buildConfig fields');
      }
      contents = contents.replace(
        releaseLevelField,
        `${releaseLevelField}\n        ${standaloneBuildConfig}`,
      );
    }

    modConfig.modResults.contents = contents;
    return modConfig;
  });
}

function withStartupOverlaySources(config) {
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

    for (const fileName of SOURCE_FILES) {
      const templatePath = path.join(TEMPLATE_DIR, `${fileName}.template`);
      const outputPath = path.join(javaDir, fileName);
      const contents = fs.readFileSync(templatePath, 'utf8').replaceAll('__PACKAGE__', packageName);
      fs.writeFileSync(outputPath, contents);
    }
    return modConfig;
  }]);
}

module.exports = function withStartupOverlay(config) {
  config = withStartupOverlayMainApplication(config);
  config = withStandaloneDebugGradle(config);
  config = withStartupOverlaySources(config);
  return config;
};
