
from typing import List, Dict, Any

from django.core.cache import cache
from .movie_service import MovieService
from ..repositories.ratings_repository import RatingsRepository
from ..repositories.watchlist_repository import WatchlistRepository
from ..repositories.viewed_movies_repository import ViewedMoviesRepository


class RecommendationEngine:
    """Lightweight engine using user genre preferences for cold-start personalization."""
    
    def __init__(self) -> None:
        self.movie_service = MovieService()
        self.ratings_repo = RatingsRepository()
        self.watchlist_repo = WatchlistRepository()
        self.viewed_repo = ViewedMoviesRepository()

    def get_trending_movies(self, time_window: str = 'week', page: int = 1) -> List[Dict[str, Any]]:
        try:
            return self.movie_service.get_trending_movies(time_window=time_window, page=page)
        except Exception:
            return []

    def get_featured_movies(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            return self.movie_service.get_popular_movies(limit=limit)
        except Exception:
            return []

    def is_new_user(self, user_id: int) -> bool:
        """A user is new only if: no prefs AND no ratings AND no watchlist AND no views.
        On repository errors, treat as NOT new to avoid over-redirecting.
        """
        try:
            if cache.get(f"user_selected_genres_{user_id}"):
                return False
            has_ratings = False
            has_watchlist = False
            has_views = False
            try:
                has_ratings = bool(self.ratings_repo.find_by_user(user_id))
            except Exception:
                return False
            try:
                has_watchlist = bool(self.watchlist_repo.find_by_user(user_id))
            except Exception:
                return False
            try:
                has_views = bool(self.viewed_repo.find_recent_by_user(user_id, limit=1))
            except Exception:
                return False
            return not (has_ratings or has_watchlist or has_views)
        except Exception:
            return False

    def _derive_genres_from_history(self, user_id: int, max_genres: int = 5) -> list[str]:
        """Infer a simple genre preference list from watchlist, views, and ratings."""
        try:
            genre_counts: dict[str, int] = {}
            movie_ids: set[int] = set()
            try:
                for r in self.ratings_repo.find_by_user(user_id):
                    mid = int(r.get('movie_id', 0))
                    if mid:
                        movie_ids.add(mid)
            except Exception:
                pass
            try:
                for w in self.watchlist_repo.find_by_user(user_id):
                    mid = int(w.get('movie_id', 0))
                    if mid:
                        movie_ids.add(mid)
            except Exception:
                pass
            try:
                for v in self.viewed_repo.find_recent_by_user(user_id, limit=100):
                    mid = int(v.get('movie_id', 0))
                    if mid:
                        movie_ids.add(mid)
            except Exception:
                pass

            for mid in list(movie_ids)[:100]:
                m = self.movie_service.get_movie(mid)
                if not m:
                    continue
                for g in m.get('genres', []) or []:
                    gname = str(g)
                    genre_counts[gname] = genre_counts.get(gname, 0) + 1
            top = sorted(genre_counts.items(), key=lambda t: t[1], reverse=True)
            return [g for g, _cnt in top[:max_genres]]
        except Exception:
            return []
    
    def _cosine_similarity(self, user_genres: list[str], movie_genres: list[str]) -> float:
        try:
            if not user_genres or not movie_genres:
                return 0.0
            user_set = set(g.lower() for g in user_genres)
            movie_set = set(g.lower() for g in movie_genres)
            overlap = len(user_set & movie_set)
            if overlap == 0:
                return 0.0
            import math
            return overlap / (math.sqrt(len(user_set)) * math.sqrt(len(movie_set)))
        except Exception:
            return 0.0

    def get_featured_for_you(self, user_id: int, limit: int = 12) -> List[Dict[str, Any]]:
        """Use saved preferences (from /preferences/) to rank popular movies by genre similarity.

        Falls back to popular movies if no preferences.
        """
        try:
            selected = cache.get(f"user_selected_genres_{user_id}") or []
            if not selected:
                # Derive from history for existing users without explicit prefs
                derived = self._derive_genres_from_history(user_id)
                if derived:
                    selected = derived
            candidates = self.movie_service.get_popular_movies(limit=200)
            if not selected:
                return candidates[:limit]

            scored: list[tuple[float, Dict[str, Any]]] = []
            for m in candidates:
                try:
                    movie_genres = m.get('genres', []) or []
                    sim = self._cosine_similarity(selected, movie_genres)
                    pop = float(m.get('vote_average', 0.0))
                    score = 0.8 * sim + 0.2 * (pop / 10.0)
                    m = dict(m)
                    m['similarity_score'] = round(sim, 3)
                    scored.append((score, m))
                except Exception:
                    continue

            scored.sort(key=lambda t: t[0], reverse=True)
            ranked = [m for _s, m in scored[:limit]]
            if len(ranked) < limit:
                seen = {m.get('id') for m in ranked}
                for p in candidates:
                    if p.get('id') not in seen:
                        ranked.append(p)
                    if len(ranked) >= limit:
                        break
            return ranked[:limit]
        except Exception:
            return self.get_featured_movies(limit=limit)

    def get_watchlist_based_recommendations(self, user_id: int, limit: int = 12) -> List[Dict[str, Any]]:
        """Recommend movies using genre-based cosine similarity derived from the user's watchlist.

        - Build a simple genre preference vector from movies in the user's watchlist
        - Rank popular candidates by cosine similarity to the user's inferred genres
        - Blend in popularity as a light tie-breaker
        - Exclude movies already present in the watchlist
        """
        try:
            # Attempt cache keyed by current watchlist ids
            try:
                watchlist_entries = self.watchlist_repo.find_by_user(user_id)
            except Exception:
                watchlist_entries = []

            watchlist_ids: list[int] = []
            for w in watchlist_entries:
                try:
                    mid = int(w.get('movie_id', 0))
                except Exception:
                    mid = 0
                if mid:
                    watchlist_ids.append(mid)

            if not watchlist_ids:
                # No watchlist yet; fall back to featured
                return self.get_featured_movies(limit=limit)

            cache_key = f"watchlist_recs_{user_id}_" + "-".join(str(i) for i in sorted(set(watchlist_ids))[:200])
            cached = cache.get(cache_key)
            if cached is not None:
                return cached[:limit]

            # Derive top genres from the user's watchlist
            genre_counts: dict[str, int] = {}
            for mid in watchlist_ids[:200]:
                m = self.movie_service.get_movie(mid)
                if not m:
                    continue
                for g in m.get('genres', []) or []:
                    gname = str(g)
                    genre_counts[gname] = genre_counts.get(gname, 0) + 1
            top_genres = [g for g, _cnt in sorted(genre_counts.items(), key=lambda t: t[1], reverse=True)[:5]]

            # Candidate pool: popular movies
            candidates = self.get_featured_movies(limit=300)
            watchlist_set = set(watchlist_ids)

            # Score candidates by cosine similarity to inferred genres + light popularity
            scored: list[tuple[float, Dict[str, Any]]] = []
            for m in candidates:
                try:
                    mid = int(m.get('id', 0))
                except Exception:
                    mid = 0
                if not mid or mid in watchlist_set:
                    continue
                movie_genres = m.get('genres', []) or []
                sim = self._cosine_similarity(top_genres, movie_genres)
                pop = float(m.get('vote_average', 0.0))
                score = 0.8 * sim + 0.2 * (pop / 10.0)
                m_with_score = dict(m)
                try:
                    m_with_score['similarity_score'] = round(float(sim), 3)
                except Exception:
                    m_with_score['similarity_score'] = 0.0
                scored.append((score, m_with_score))

            scored.sort(key=lambda t: t[0], reverse=True)
            ranked = [m for _s, m in scored[:limit]]

            # If not enough, backfill with popular not in watchlist and not already chosen
            if len(ranked) < limit:
                seen_ids = {m.get('id') for m in ranked}
                for p in candidates:
                    pid = p.get('id')
                    if pid in seen_ids or pid in watchlist_set:
                        continue
                    p2 = dict(p)
                    p2['similarity_score'] = 0.0
                    ranked.append(p2)
                    if len(ranked) >= limit:
                        break

            cache.set(cache_key, ranked, timeout=60 * 30)  # cache for 30 minutes
            return ranked[:limit]
        except Exception:
            return self.get_featured_movies(limit=limit)

   
    def get_item_based_recommendations(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Item-based CF using cosine similarity on item vectors (users as features).

        Steps:
        - Build inverted index item->(user->rating) and item norms
        - For the user's highly-rated seed items (>=5), compute cosine similarity to other items
        - Score each candidate by sum(sim(i,candidate) * rating(user,i)) and normalize by total sim
        - Exclude items already rated by the user
        """
        try:
            try:
                user_ratings = self.ratings_repo.find_by_user(user_id)
            except Exception:
                user_ratings = []
            seed_movie_ids = [int(r.get('movie_id', 0)) for r in user_ratings if int(r.get('rating', 0)) >= 5]
            seed_movie_ids = [m for m in seed_movie_ids if m]
            if not seed_movie_ids:
                return []

            # Build item->user ratings map and norms for items seen in neighborhood of seeds
            from collections import defaultdict
            item_to_users: dict[int, dict[int, float]] = defaultdict(dict)

            # Gather raters for seed items and their other rated items
            neighbor_user_ids: set[int] = set()
            for mid in seed_movie_ids[:100]:  # Increased from 50 to 100
                try:
                    for rr in self.ratings_repo.iter_by_movie(mid):
                        try:
                            nid = int(rr.get('user_id'))
                            neighbor_user_ids.add(nid)
                        except Exception:
                            continue
                except Exception:
                    continue

            # Build item vectors from neighbor users' full ratings
            for nid in list(neighbor_user_ids)[:2000]:  # Increased from 1000 to 2000
                try:
                    nr = self.ratings_repo.find_by_user(nid)
                except Exception:
                    continue
                for r in nr:
                    try:
                        mid = int(r.get('movie_id', 0))
                        val = float(r.get('rating', 0))
                    except Exception:
                        continue
                    if mid:
                        item_to_users[mid][nid] = val

            # Compute norms
            import math
            item_norm: dict[int, float] = {}
            for mid, vec in item_to_users.items():
                item_norm[mid] = math.sqrt(sum(v*v for v in vec.values())) or 1.0

            # Score candidates by summed cosine similarity to seed items weighted by user's rating on seed
            seen = {int(r.get('movie_id', 0)) for r in user_ratings if r.get('movie_id') is not None}
            scores: dict[int, float] = {}
            weights: dict[int, float] = {}

            # Build a quick map for the user's ratings on seeds
            user_seed_rating: dict[int, float] = {}
            for r in user_ratings:
                try:
                    mid = int(r.get('movie_id', 0))
                    if mid in seed_movie_ids:
                        user_seed_rating[mid] = float(r.get('rating', 0))
                except Exception:
                    continue

            for i in seed_movie_ids:
                vec_i = item_to_users.get(i, {})
                if not vec_i:
                    continue
                for j, vec_j in item_to_users.items():
                    if j == i or j in seen:
                        continue
                    # compute cosine on overlapping users
                    common = set(vec_i.keys()) & set(vec_j.keys())
                    if not common:
                        continue
                    dot = sum(vec_i[u] * vec_j[u] for u in common)
                    sim = dot / (item_norm.get(i, 1.0) * item_norm.get(j, 1.0))
                    if sim <= 0.1:  # Lowered threshold from 0 to 0.1
                        continue
                    r_ui = user_seed_rating.get(i, 0.0)
                    scores[j] = scores.get(j, 0.0) + sim * r_ui
                    weights[j] = weights.get(j, 0.0) + sim

            if not scores:
                # Fallback: return popular movies if no collaborative filtering results
                return self.get_featured_movies(limit=limit)

            ranked = []
            for mid, sc in scores.items():
                w = weights.get(mid, 0.0)
                if w > 0:
                    ranked.append((sc / w, mid))
            ranked.sort(reverse=True)

            recs: List[Dict[str, Any]] = []
            for _score, mid in ranked:
                m = self.movie_service.get_movie(mid)
                if m:
                    recs.append(m)
                if len(recs) >= limit:
                    break
            
            # If we don't have enough recommendations, supplement with popular movies
            if len(recs) < limit:
                seen_ids = {m.get('id') for m in recs}
                popular = self.get_featured_movies(limit=limit * 2)
                for movie in popular:
                    if movie.get('id') not in seen_ids and len(recs) < limit:
                        recs.append(movie)
            
            return recs
        except Exception:
            return []

    def get_user_based_recommendations(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """User-based CF: find similar users by rating overlap and recommend their favorites."""
        try:
            try:
                target_ratings = self.ratings_repo.find_by_user(user_id)
            except Exception:
                target_ratings = []
            if not target_ratings:
                return []

            target_map: dict[int, float] = {}
            for r in target_ratings:
                try:
                    target_map[int(r.get('movie_id'))] = float(r.get('rating', 0))
                except Exception:
                    continue

            # Build neighbor set from raters of the target's movies
            neighbor_ids: set[int] = set()
            for mid in list(target_map.keys())[:100]:  # Increased from 50 to 100
                try:
                    for rr in self.ratings_repo.iter_by_movie(mid):
                        nid = rr.get('user_id')
                        try:
                            nid = int(nid)
                            if nid != int(user_id):
                                neighbor_ids.add(nid)
                        except Exception:
                            continue
                except Exception:
                    continue

            # Compute similarity = cosine on co-rated items
            import math
            sim_by_user: dict[int, float] = {}
            for nid in list(neighbor_ids)[:1000]:  # Increased from 500 to 1000
                try:
                    nr = self.ratings_repo.find_by_user(nid)
                except Exception:
                    continue
                neigh_map: dict[int, float] = {}
                for r in nr:
                    try:
                        neigh_map[int(r.get('movie_id'))] = float(r.get('rating', 0))
                    except Exception:
                        continue
                common = [mid for mid in neigh_map.keys() if mid in target_map]
                if not common:
                    continue
                dot = sum(target_map[mid] * neigh_map[mid] for mid in common)
                na = math.sqrt(sum(target_map[mid] ** 2 for mid in common))
                nb = math.sqrt(sum(neigh_map[mid] ** 2 for mid in common))
                if na <= 0 or nb <= 0:
                    continue
                sim = dot / (na * nb)
                if sim > 0:
                    sim_by_user[nid] = sim

            if not sim_by_user:
                # Fallback: return popular movies if no similar users found
                return self.get_featured_movies(limit=limit)

            # Aggregate neighbor favorites not rated by target
            target_seen = set(target_map.keys())
            score_by_movie: dict[int, float] = {}
            for nid, sim in sorted(sim_by_user.items(), key=lambda t: t[1], reverse=True)[:50]:
                try:
                    nr = self.ratings_repo.find_by_user(nid)
                except Exception:
                    continue
                for r in nr:
                    try:
                        mid = int(r.get('movie_id', 0))
                        if not mid or mid in target_seen:
                            continue
                        val = float(r.get('rating', 0))
                        # weighted by similarity
                        score_by_movie[mid] = score_by_movie.get(mid, 0.0) + sim * val
                    except Exception:
                        continue

            if not score_by_movie:
                # Fallback: return popular movies if no recommendations found
                return self.get_featured_movies(limit=limit)

            ranked_ids = sorted(score_by_movie.keys(), key=lambda m: score_by_movie[m], reverse=True)
            recs: List[Dict[str, Any]] = []
            for mid in ranked_ids:
                m = self.movie_service.get_movie(mid)
                if m:
                    recs.append(m)
                if len(recs) >= limit:
                    break
            
            # If we don't have enough recommendations, supplement with popular movies
            if len(recs) < limit:
                seen_ids = {m.get('id') for m in recs}
                popular = self.get_featured_movies(limit=limit * 2)
                for movie in popular:
                    if movie.get('id') not in seen_ids and len(recs) < limit:
                        recs.append(movie)
            
            return recs
        except Exception:
            return []
