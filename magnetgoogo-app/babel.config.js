module.exports = function (api) {
  api.cache(true);
  const plugins = [];
  // Strip console.log in production builds (keep console.error / console.warn)
  if (process.env.NODE_ENV === 'production') {
    plugins.push(['transform-remove-console', { exclude: ['error', 'warn'] }]);
  }
  return {
    presets: ['babel-preset-expo'],
    plugins,
  };
};
