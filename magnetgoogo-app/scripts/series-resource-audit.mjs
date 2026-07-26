import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  inferSeriesSeason,
  resourceDisplayTitle,
  resourceEpisodeIdentity,
  sortMediaResources,
  uniqueMagnetResources,
} from '../src/core/mediaResourceTitle.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const feedPath = path.resolve(here, '..', '..', 'data', 'resource_index', 'series_latest_100_feed.json');

if (!fs.existsSync(feedPath)) {
  console.error(`Series Feed not found: ${feedPath}`);
  process.exitCode = 1;
} else {
  const feed = JSON.parse(fs.readFileSync(feedPath, 'utf8'));
  if (!Array.isArray(feed.items)) {
    throw new Error('Series source Feed must expose an items array');
  }
  const summary = {
    item_count: feed.items.length,
    magnet_count: 0,
    unique_magnet_count: 0,
    duplicate_magnet_count: 0,
    episode_resource_count: 0,
    season_pack_count: 0,
    unknown_identity_count: 0,
    generic_title_count: 0,
    recovered_generic_title_count: 0,
    unrecovered_generic_title_count: 0,
    items_out_of_source_order: 0,
    items_with_title_field_season_conflict: 0,
    items_without_episode_resources: 0,
    items_with_cross_season_resources: 0,
    cross_season_resource_count: 0,
    repeated_display_title_groups: 0,
  };
  const examples = {
    unknown_identity: [],
    cross_season: [],
    repeated_display_title: [],
    out_of_order: [],
    title_field_season_conflict: [],
  };

  for (const item of feed.items) {
    const fallbackSeason = inferSeriesSeason(item.title, item.season_number);
    if (item.season_number && fallbackSeason !== item.season_number) {
      summary.items_with_title_field_season_conflict += 1;
      if (examples.title_field_season_conflict.length < 20) {
        examples.title_field_season_conflict.push({
          title: item.title,
          season_number: item.season_number,
          title_season: fallbackSeason,
        });
      }
    }
    const magnets = item.resources.filter((resource) => resource.resource_type === 'magnet');
    const uniqueMagnets = uniqueMagnetResources(magnets);
    const sorted = sortMediaResources(uniqueMagnets, fallbackSeason);
    summary.magnet_count += magnets.length;
    summary.unique_magnet_count += uniqueMagnets.length;

    const originalIdentityKeys = [];
    let episodeResourceCount = 0;
    let itemCrossSeasonCount = 0;
    const displayGroups = new Map();

    for (const resource of uniqueMagnets) {
      const identity = resourceEpisodeIdentity(resource, fallbackSeason);
      const rawTitle = resource.display_title.trim();
      const displayTitle = resourceDisplayTitle(resource, fallbackSeason);
      if (/^(?:4k|2160p?|1080p?|720p|480p|hd|bd|web-?dl|磁力|magnet)$/i.test(rawTitle)) {
        summary.generic_title_count += 1;
        if (identity?.kind === 'episode') summary.recovered_generic_title_count += 1;
      }

      if (identity?.kind === 'episode') {
        summary.episode_resource_count += 1;
        episodeResourceCount += 1;
        originalIdentityKeys.push([
          identity.season,
          identity.episodeStart ?? Number.MAX_SAFE_INTEGER,
          identity.episodeEnd ?? Number.MAX_SAFE_INTEGER,
        ]);
      } else if (identity?.kind === 'season-pack') {
        summary.season_pack_count += 1;
      } else {
        summary.unknown_identity_count += 1;
        if (examples.unknown_identity.length < 20) {
          examples.unknown_identity.push({
            title: item.title,
            season_number: item.season_number,
            display_title: rawTitle,
            recovered_title: displayTitle,
          });
        }
      }

      if (identity && identity.season !== fallbackSeason) {
        itemCrossSeasonCount += 1;
        summary.cross_season_resource_count += 1;
        if (examples.cross_season.length < 20) {
          examples.cross_season.push({
            title: item.title,
            item_season: fallbackSeason,
            resource_season: identity.season,
            episode: identity.label,
            display_title: rawTitle,
          });
        }
      }

      const group = displayGroups.get(displayTitle) ?? [];
      group.push(resource.info_hash || resource.url);
      displayGroups.set(displayTitle, group);
    }

    if (episodeResourceCount === 0 && uniqueMagnets.length > 0) {
      summary.items_without_episode_resources += 1;
    }
    if (itemCrossSeasonCount > 0) {
      summary.items_with_cross_season_resources += 1;
    }

    const sourceOrderBroken = originalIdentityKeys.some((key, index) => {
      if (index === 0) return false;
      const previous = originalIdentityKeys[index - 1];
      return previous[0] > key[0]
        || (previous[0] === key[0] && previous[1] > key[1])
        || (previous[0] === key[0] && previous[1] === key[1] && previous[2] > key[2]);
    });
    if (sourceOrderBroken) {
      summary.items_out_of_source_order += 1;
      if (examples.out_of_order.length < 20) {
        examples.out_of_order.push({
          title: item.title,
          before: originalIdentityKeys.slice(0, 12),
          after: sorted
            .map((resource) => resourceEpisodeIdentity(resource, fallbackSeason))
            .filter(Boolean)
            .slice(0, 12)
            .map((identity) => [identity.season, identity.episodeStart, identity.episodeEnd]),
        });
      }
    }

    for (const [displayTitle, hashes] of displayGroups.entries()) {
      if (hashes.length <= 1) continue;
      summary.repeated_display_title_groups += 1;
      if (examples.repeated_display_title.length < 20) {
        examples.repeated_display_title.push({
          title: item.title,
          display_title: displayTitle,
          resource_count: hashes.length,
        });
      }
    }
  }

  summary.duplicate_magnet_count = summary.magnet_count - summary.unique_magnet_count;
  summary.unrecovered_generic_title_count = summary.generic_title_count - summary.recovered_generic_title_count;

  console.log('=== Series resource audit ===');
  console.log(JSON.stringify(summary, null, 2));
  console.log('=== Examples ===');
  console.log(JSON.stringify(examples, null, 2));
}
