const { withMainApplication } = require('@expo/config-plugins');

const MARKER = '// MAGNETGOOGO_IPV4_FIRST_NETWORK_V1';

function applyIpv4FirstNetworking(contents) {
  if (contents.includes(MARKER)) return contents;

  const importAnchor = 'import android.content.res.Configuration';
  if (!contents.includes(importAnchor)) {
    throw new Error('Unable to locate MainApplication import anchor');
  }

  const imports = `${importAnchor}\n\nimport com.facebook.react.modules.network.OkHttpClientFactory\nimport com.facebook.react.modules.network.OkHttpClientProvider\nimport java.net.Inet4Address\nimport java.net.InetAddress\nimport okhttp3.Dns`;
  contents = contents.replace(importAnchor, imports);

  const onCreateAnchor = '  override fun onCreate() {\n    super.onCreate()';
  if (!contents.includes(onCreateAnchor)) {
    throw new Error('Unable to locate MainApplication.onCreate');
  }

  const factory = `  override fun onCreate() {\n    super.onCreate()\n    ${MARKER}\n    OkHttpClientProvider.setOkHttpClientFactory(\n      OkHttpClientFactory {\n        OkHttpClientProvider.createClientBuilder()\n          .dns(\n            object : Dns {\n              override fun lookup(hostname: String): List<InetAddress> =\n                Dns.SYSTEM.lookup(hostname).sortedBy { address ->\n                  if (address is Inet4Address) 0 else 1\n                }\n            },\n          )\n          .build()\n      },\n    )`;
  return contents.replace(onCreateAnchor, factory);
}

function withIpv4FirstMainApplication(config) {
  return withMainApplication(config, (modConfig) => {
    if (modConfig.modResults.language !== 'kt') {
      throw new Error('IPv4-first network plugin requires a Kotlin MainApplication');
    }
    modConfig.modResults.contents = applyIpv4FirstNetworking(modConfig.modResults.contents);
    return modConfig;
  });
}

module.exports = function withNetworkIpv4Preference(config) {
  return withIpv4FirstMainApplication(config);
};
module.exports.applyIpv4FirstNetworking = applyIpv4FirstNetworking;
