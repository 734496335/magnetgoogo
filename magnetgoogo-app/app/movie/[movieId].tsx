import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Linking,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  Vibration,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import * as Clipboard from 'expo-clipboard';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLang } from '../../src/core/LangContext';
import { useTheme, type Colors } from '../../src/core/ThemeContext';
import { getResourceCopy } from '../../src/core/resourceCopy';
import { addHistory } from '../../src/core/searchHistory';
import { trackCopy, trackOpen } from '../../src/core/analytics';
import { loadMovieById, movieCoverUri } from '../../src/core/resourceFeed';
import type { MovieFeedItem, MovieResource } from '../../src/core/resourceFeedProtocol';

interface MagnetResourceCardProps {
  resource: MovieResource;
  colors: Colors;
  copied: boolean;
  copyLabel: string;
  copiedLabel: string;
  openLabel: string;
  magnetLabel: string;
  onCopy: (resource: MovieResource) => void;
  onOpen: (resource: MovieResource) => void;
}

const MagnetResourceCard = memo(function MagnetResourceCard({
  resource,
  colors,
  copied,
  copyLabel,
  copiedLabel,
  openLabel,
  magnetLabel,
  onCopy,
  onOpen,
}: MagnetResourceCardProps) {
  const copyResource = useCallback(() => onCopy(resource), [onCopy, resource]);
  const openResource = useCallback(() => onOpen(resource), [onOpen, resource]);
  const visibleTags = resource.quality_tags.slice(0, 5);

  return (
    <View
      style={[
        styles.resourceCard,
        {
          backgroundColor: colors.card,
          borderColor: colors.accent,
          shadowColor: colors.shadow,
        },
      ]}
    >
      <View style={styles.resourceHeader}>
        <LinearGradient colors={['#4e8aff', '#2c63f4']} style={styles.resourceIcon}>
          <Ionicons name="magnet" size={22} color="#fff" />
        </LinearGradient>
        <View style={styles.resourceHeaderText}>
          <Text style={[styles.resourceType, { color: colors.accent }]}>{magnetLabel}</Text>
          <Text style={[styles.resourceTitle, { color: colors.text }]} numberOfLines={3}>
            {resource.display_title}
          </Text>
        </View>
      </View>

      {visibleTags.length > 0 && (
        <View style={styles.resourceTags}>
          {visibleTags.map((tag) => (
            <View key={tag} style={[styles.resourceTag, { backgroundColor: colors.tagBg }]}>
              <Text style={[styles.resourceTagText, { color: colors.tagText }]}>{tag}</Text>
            </View>
          ))}
        </View>
      )}

      <View style={[styles.resourceActions, { borderTopColor: colors.border }]}>
        <TouchableOpacity
          style={styles.actionTouch}
          activeOpacity={0.8}
          onPress={copyResource}
          accessibilityRole="button"
          accessibilityLabel={copyLabel}
        >
          <LinearGradient colors={['#4e8aff', '#2c63f4']} style={styles.actionButton}>
            <Ionicons name={copied ? 'checkmark' : 'copy-outline'} size={15} color="#fff" />
            <Text style={styles.actionButtonText}>{copied ? copiedLabel : copyLabel}</Text>
          </LinearGradient>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.actionTouch}
          activeOpacity={0.8}
          onPress={openResource}
          accessibilityRole="button"
          accessibilityLabel={openLabel}
        >
          <LinearGradient colors={['#ff8a4c', '#f06529']} style={styles.actionButton}>
            <Ionicons name="open-outline" size={15} color="#fff" />
            <Text style={styles.actionButtonText}>{openLabel}</Text>
          </LinearGradient>
        </TouchableOpacity>
      </View>
    </View>
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
  const { lang, t } = useLang();
  const { colors } = useTheme();
  const copy = getResourceCopy(lang);
  const movieId = Array.isArray(params.movieId) ? params.movieId[0] : params.movieId;
  const [movie, setMovie] = useState<MovieFeedItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [posterFailed, setPosterFailed] = useState(false);
  const [copiedResourceUrl, setCopiedResourceUrl] = useState<string | null>(null);

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
    if (!copiedResourceUrl) return undefined;
    const timer = setTimeout(() => setCopiedResourceUrl(null), 2000);
    return () => clearTimeout(timer);
  }, [copiedResourceUrl]);

  const metadata = useMemo(() => {
    if (!movie) return '';
    return [
      movie.year,
      movie.genres.slice(0, 2).join(' · '),
      movie.duration_minutes ? copy.minutes(movie.duration_minutes) : null,
    ].filter(Boolean).join(' · ');
  }, [copy, movie]);

  const magnetResources = useMemo(
    () => movie?.resources.filter((resource) => resource.resource_type === 'magnet') ?? [],
    [movie],
  );

  const copyResource = useCallback(async (resource: MovieResource) => {
    try {
      await Clipboard.setStringAsync(resource.url);
      trackCopy();
      Vibration.vibrate(Platform.OS === 'android' ? 30 : 10);
      setCopiedResourceUrl(resource.url);
    } catch (error) {
      console.warn('[MovieDetail]', {
        stage: 'copy_magnet',
        error_code: 'MOVIE_MAGNET_COPY_FAILED',
        movie_id: movie?.movie_id,
        info_hash: resource.info_hash,
        error: error instanceof Error ? error.message : String(error),
      });
      Alert.alert(t.copyFailed);
    }
  }, [movie?.movie_id, t.copyFailed]);

  const openResource = useCallback((resource: MovieResource) => {
    trackOpen();
    Linking.openURL(resource.url).catch((error) => {
      console.warn('[MovieDetail]', {
        stage: 'open_magnet',
        error_code: 'MOVIE_MAGNET_OPEN_FAILED',
        movie_id: movie?.movie_id,
        info_hash: resource.info_hash,
        error: error instanceof Error ? error.message : String(error),
      });
      Alert.alert(t.cannotOpen, t.cannotOpenMsg);
    });
  }, [movie?.movie_id, t.cannotOpen, t.cannotOpenMsg]);

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
              {copy.resourceCount(magnetResources.length)}
            </Text>
          </View>
          {magnetResources.length === 0 ? (
            <Text style={[styles.noResources, { color: colors.textTertiary }]}>
              {copy.noMagnetResources}
            </Text>
          ) : magnetResources.map((resource) => (
            <MagnetResourceCard
              key={resource.url}
              resource={resource}
              colors={colors}
              copied={copiedResourceUrl === resource.url}
              copyLabel={t.copyMagnet}
              copiedLabel={t.copied}
              openLabel={t.openMagnet}
              magnetLabel={copy.providerMagnet}
              onCopy={copyResource}
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
  resourceCard: {
    marginTop: 14,
    borderWidth: 1.25,
    borderRadius: 20,
    padding: 15,
    shadowOpacity: 0.16,
    shadowOffset: { width: 0, height: 8 },
    shadowRadius: 18,
    elevation: 5,
  },
  resourceHeader: { flexDirection: 'row', alignItems: 'flex-start' },
  resourceIcon: {
    width: 46,
    height: 46,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  resourceHeaderText: { flex: 1, marginLeft: 12 },
  resourceType: { fontSize: 11, fontWeight: '800', marginBottom: 4 },
  resourceTitle: { fontSize: 13, lineHeight: 19, fontWeight: '700' },
  resourceTags: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 12 },
  resourceTag: {
    borderRadius: 10,
    paddingHorizontal: 9,
    paddingVertical: 5,
    marginRight: 6,
    marginBottom: 6,
  },
  resourceTagText: { fontSize: 10, fontWeight: '700' },
  resourceActions: {
    flexDirection: 'row',
    marginTop: 10,
    paddingTop: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    gap: 9,
  },
  actionTouch: { flex: 1 },
  actionButton: {
    height: 40,
    borderRadius: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  actionButtonText: { color: '#fff', fontSize: 12, fontWeight: '800' },
  noResources: { marginTop: 14, fontSize: 13, lineHeight: 20 },
  searchButton: {
    height: 50,
    borderRadius: 15,
    marginTop: 30,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchButtonText: { marginLeft: 8, color: '#fff', fontSize: 15, fontWeight: '800' },
});
