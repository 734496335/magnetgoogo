import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Linking,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLang } from '../../src/core/LangContext';
import { useTheme, type Colors } from '../../src/core/ThemeContext';
import { getResourceCopy, type ResourceCopy } from '../../src/core/resourceCopy';
import { addHistory } from '../../src/core/searchHistory';
import { loadMovieById, movieCoverUri } from '../../src/core/resourceFeed';
import type { MovieFeedItem, MovieResource } from '../../src/core/resourceFeedProtocol';

interface ResourceButtonProps {
  resource: MovieResource;
  colors: Colors;
  copy: ResourceCopy;
  onOpen: (resource: MovieResource) => void;
}

function providerPresentation(provider: string, copy: ResourceCopy) {
  switch (provider) {
    case 'xunlei':
      return { label: copy.providerXunlei, icon: 'flash-outline' as const };
    case 'quark':
      return { label: copy.providerQuark, icon: 'planet-outline' as const };
    case 'baidu':
      return { label: copy.providerBaidu, icon: 'cloud-outline' as const };
    default:
      return { label: copy.providerMagnet, icon: 'magnet-outline' as const };
  }
}

const ResourceButton = memo(function ResourceButton({
  resource,
  colors,
  copy,
  onOpen,
}: ResourceButtonProps) {
  const presentation = providerPresentation(resource.provider, copy);
  const open = useCallback(() => onOpen(resource), [onOpen, resource]);
  return (
    <TouchableOpacity
      style={[styles.resourceButton, { backgroundColor: colors.card, borderColor: colors.border }]}
      activeOpacity={0.72}
      onPress={open}
      accessibilityRole="button"
      accessibilityLabel={`${presentation.label} ${copy.openResource}`}
    >
      <View style={[styles.providerIcon, { backgroundColor: colors.tagBg }]}>
        <Ionicons name={presentation.icon} size={21} color={colors.tagText} />
      </View>
      <View style={styles.resourceInfo}>
        <Text style={[styles.providerName, { color: colors.text }]}>{presentation.label}</Text>
        <Text style={[styles.resourceTitle, { color: colors.textTertiary }]} numberOfLines={1}>
          {resource.resource_type === 'magnet' ? resource.display_title : copy.cloudResourceHint}
        </Text>
        {!!resource.extraction_code && (
          <Text style={[styles.extractionCode, { color: colors.textSecondary }]}>
            {copy.extractionCode} {resource.extraction_code}
          </Text>
        )}
      </View>
      <Ionicons name="open-outline" size={18} color={colors.textTertiary} />
    </TouchableOpacity>
  );
});

function InfoRow({ label, value, colors }: { label: string; value: string; colors: Colors }) {
  if (!value) return null;
  return (
    <View style={styles.infoRow}>
      <Text style={[styles.infoLabel, { color: colors.textTertiary }]}>{label}</Text>
      <Text style={[styles.infoValue, { color: colors.text }]}>{value}</Text>
    </View>
  );
}

export default function MovieDetailScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ movieId?: string | string[] }>();
  const { lang } = useLang();
  const { colors } = useTheme();
  const copy = getResourceCopy(lang);
  const movieId = Array.isArray(params.movieId) ? params.movieId[0] : params.movieId;
  const [movie, setMovie] = useState<MovieFeedItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [posterFailed, setPosterFailed] = useState(false);
  const [toast, setToast] = useState('');

  useEffect(() => {
    let active = true;
    if (!movieId) {
      setFailed(true);
      setLoading(false);
      return () => {
        active = false;
      };
    }
    loadMovieById(movieId)
      .then((loaded) => {
        if (!active) return;
        if (loaded) setMovie(loaded);
        else setFailed(true);
      })
      .catch((error) => {
        if (!active) return;
        console.warn('[MovieDetail]', {
          stage: 'load_movie',
          error_code: 'MOVIE_DETAIL_LOAD_FAILED',
          movie_id: movieId,
          error: error instanceof Error ? error.message : String(error),
        });
        setFailed(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [movieId]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(''), 1800);
    return () => clearTimeout(timer);
  }, [toast]);

  const metadata = useMemo(() => {
    if (!movie) return '';
    return [
      movie.year,
      movie.genres.slice(0, 2).join(' · '),
      movie.duration_minutes ? copy.minutes(movie.duration_minutes) : null,
    ].filter(Boolean).join(' · ');
  }, [copy, movie]);

  const openResource = useCallback(async (resource: MovieResource) => {
    try {
      if (resource.extraction_code) {
        await Clipboard.setStringAsync(resource.extraction_code);
        setToast(copy.extractionCodeCopied);
      }
      const supported = await Linking.canOpenURL(resource.url);
      if (supported) {
        await Linking.openURL(resource.url);
        return;
      }
      await Clipboard.setStringAsync(resource.url);
      setToast(resource.resource_type === 'magnet' ? copy.magnetCopied : copy.openFailed);
    } catch (error) {
      console.warn('[MovieDetail]', {
        stage: 'open_resource',
        error_code: 'MOVIE_RESOURCE_OPEN_FAILED',
        provider: resource.provider,
        movie_id: movie?.movie_id,
        error: error instanceof Error ? error.message : String(error),
      });
      setToast(copy.openFailed);
    }
  }, [copy.extractionCodeCopied, copy.magnetCopied, copy.openFailed, movie?.movie_id]);

  const searchMore = useCallback(async () => {
    if (!movie) return;
    try {
      await addHistory(movie.title);
    } catch (error) {
      console.warn('[MovieDetail]', {
        stage: 'save_search_history',
        error_code: 'MOVIE_SEARCH_HISTORY_FAILED',
        movie_id: movie.movie_id,
        error: error instanceof Error ? error.message : String(error),
      });
    }
    router.push({ pathname: '/search', params: { q: movie.title } });
  }, [movie, router]);

  if (loading) {
    return (
      <View style={[styles.center, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
        <ActivityIndicator size="large" color={colors.accent} />
      </View>
    );
  }

  if (failed || !movie) {
    return (
      <View style={[styles.center, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
        <Ionicons name="film-outline" size={42} color={colors.textTertiary} />
        <Text style={[styles.notFound, { color: colors.text }]}>{copy.movieNotFound}</Text>
        <TouchableOpacity style={styles.backTextButton} onPress={() => router.back()}>
          <Text style={{ color: colors.accent }}>{copy.back}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.bg }]}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <View style={{ height: insets.top + 54 }} />
        <View style={[styles.poster, { backgroundColor: colors.chipBg, shadowColor: colors.shadow }]}>
          {posterFailed ? (
            <View style={styles.posterFallback}>
              <Ionicons name="film-outline" size={42} color={colors.textTertiary} />
            </View>
          ) : (
            <Image
              source={{ uri: movieCoverUri(movie) }}
              style={styles.posterImage}
              resizeMode="cover"
              onError={() => setPosterFailed(true)}
            />
          )}
        </View>

        <Text style={[styles.title, { color: colors.text }]}>{movie.title}</Text>
        {!!movie.original_title && movie.original_title !== movie.title && (
          <Text style={[styles.originalTitle, { color: colors.textTertiary }]}>{movie.original_title}</Text>
        )}
        <Text style={[styles.metadata, { color: colors.textSecondary }]}>{metadata}</Text>

        <View style={styles.highlightRow}>
          {movie.douban_rating !== null && (
            <View style={[styles.scorePill, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Ionicons name="star" size={14} color="#f59e0b" />
              <Text style={[styles.score, { color: colors.text }]}>{movie.douban_rating.toFixed(1)}</Text>
              <Text style={[styles.scoreSource, { color: colors.textTertiary }]}>豆瓣</Text>
            </View>
          )}
          {movie.quality_tags.slice(0, 5).map((tag) => (
            <View key={tag} style={[styles.tag, { backgroundColor: colors.tagBg }]}>
              <Text style={[styles.tagText, { color: colors.tagText }]}>{tag}</Text>
            </View>
          ))}
        </View>

        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>{copy.detailSynopsis}</Text>
          <Text style={[styles.synopsis, { color: colors.textSecondary }]}>
            {movie.synopsis || copy.noSynopsis}
          </Text>
        </View>

        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>{copy.detailInfo}</Text>
          <InfoRow label={copy.detailRelease} value={movie.release_date || movie.update_date || ''} colors={colors} />
          <InfoRow label={copy.detailCountry} value={movie.countries.join('、')} colors={colors} />
          <InfoRow label={copy.detailLanguage} value={movie.languages.join('、')} colors={colors} />
          <InfoRow label="IMDb" value={movie.imdb_id || ''} colors={colors} />
        </View>

        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>{copy.detailCast}</Text>
          <InfoRow label={copy.detailDirector} value={movie.directors.join('、')} colors={colors} />
          <InfoRow label={copy.detailActors} value={movie.actors.slice(0, 12).join('、')} colors={colors} />
        </View>

        <View style={styles.section}>
          <View style={styles.sectionTitleRow}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>{copy.detailResources}</Text>
            <Text style={[styles.sectionCount, { color: colors.textTertiary }]}>
              {copy.resourceCount(movie.resources.length)}
            </Text>
          </View>
          {movie.resources.map((resource) => (
            <ResourceButton
              key={`${resource.provider}:${resource.url}`}
              resource={resource}
              colors={colors}
              copy={copy}
              onOpen={openResource}
            />
          ))}
        </View>

        <TouchableOpacity
          style={[styles.searchButton, { backgroundColor: colors.accent }]}
          activeOpacity={0.8}
          onPress={() => void searchMore()}
        >
          <Ionicons name="search" size={18} color="#fff" />
          <Text style={styles.searchButtonText}>{copy.searchMore}</Text>
        </TouchableOpacity>
      </ScrollView>

      <TouchableOpacity
        style={[styles.backButton, { top: insets.top + 8, backgroundColor: colors.card, borderColor: colors.border }]}
        onPress={() => router.back()}
        accessibilityRole="button"
        accessibilityLabel={copy.back}
      >
        <Ionicons name="chevron-back" size={23} color={colors.text} />
      </TouchableOpacity>

      {!!toast && (
        <View style={[styles.toast, { bottom: insets.bottom + 22 }]} pointerEvents="none">
          <Text style={styles.toastText}>{toast}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { paddingHorizontal: 20, paddingBottom: 44 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  notFound: { marginTop: 14, fontSize: 18, fontWeight: '800' },
  backTextButton: { marginTop: 18, padding: 10 },
  backButton: {
    position: 'absolute',
    left: 16,
    width: 42,
    height: 42,
    borderRadius: 21,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
    shadowOpacity: 0.08,
    shadowOffset: { width: 0, height: 3 },
    shadowRadius: 8,
    elevation: 2,
  },
  poster: {
    width: 190,
    height: 270,
    borderRadius: 17,
    overflow: 'hidden',
    alignSelf: 'center',
    shadowOpacity: 0.16,
    shadowOffset: { width: 0, height: 8 },
    shadowRadius: 18,
    elevation: 5,
  },
  posterImage: { width: '100%', height: '100%' },
  posterFallback: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  title: { marginTop: 22, fontSize: 25, lineHeight: 32, fontWeight: '800', textAlign: 'center', letterSpacing: -0.5 },
  originalTitle: { marginTop: 7, fontSize: 13, lineHeight: 18, textAlign: 'center' },
  metadata: { marginTop: 10, fontSize: 13, textAlign: 'center' },
  highlightRow: { marginTop: 16, flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center' },
  scorePill: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 9,
    paddingHorizontal: 8,
    paddingVertical: 5,
    marginRight: 6,
    marginBottom: 6,
  },
  score: { marginLeft: 4, fontSize: 12, fontWeight: '800' },
  scoreSource: { marginLeft: 4, fontSize: 9 },
  tag: { borderRadius: 7, paddingHorizontal: 8, paddingVertical: 6, marginRight: 6, marginBottom: 6 },
  tagText: { fontSize: 10, fontWeight: '700' },
  section: { marginTop: 30 },
  sectionTitleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sectionTitle: { fontSize: 18, fontWeight: '800', letterSpacing: -0.2 },
  sectionCount: { fontSize: 11 },
  synopsis: { marginTop: 12, fontSize: 14, lineHeight: 23 },
  infoRow: { flexDirection: 'row', alignItems: 'flex-start', paddingTop: 13 },
  infoLabel: { width: 72, fontSize: 12, lineHeight: 20 },
  infoValue: { flex: 1, fontSize: 13, lineHeight: 20 },
  resourceButton: {
    minHeight: 72,
    marginTop: 10,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
  },
  providerIcon: { width: 42, height: 42, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  resourceInfo: { flex: 1, marginHorizontal: 11 },
  providerName: { fontSize: 14, fontWeight: '700' },
  resourceTitle: { marginTop: 3, fontSize: 10 },
  extractionCode: { marginTop: 4, fontSize: 10, fontWeight: '600' },
  searchButton: {
    height: 50,
    borderRadius: 15,
    marginTop: 30,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchButtonText: { marginLeft: 8, color: '#fff', fontSize: 15, fontWeight: '800' },
  toast: {
    position: 'absolute',
    left: 50,
    right: 50,
    alignItems: 'center',
  },
  toastText: {
    overflow: 'hidden',
    borderRadius: 12,
    paddingHorizontal: 15,
    paddingVertical: 10,
    backgroundColor: 'rgba(15,23,42,0.9)',
    color: '#fff',
    fontSize: 12,
    fontWeight: '700',
  },
});
