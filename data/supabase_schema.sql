-- Series Archive → Supabase 이전용 스키마 (2026-08-11 rev2)
-- rev1 오류 수정: ad_social_matches 의 실제 컬럼명은 social_video_id 가 아니라 social_id 였음
--                (SQLite 원본: UNIQUE(ad_id, social_id)) → 인덱스/PK를 social_id 로 정정.
-- 이 스크립트는 몇 번을 실행해도 안전합니다(전부 IF NOT EXISTS / DO 가드).
--  · 기존 테이블이 이미 있으면 지우지 않고 '없는 컬럼만' 추가합니다.
--  · 기존 ad_scripts 등 운영 테이블은 이 스크립트가 전혀 건드리지 않습니다.
-- Supabase Dashboard → SQL Editor 에 붙여넣고 Run.


-- ── ad_library_ads ──
CREATE TABLE IF NOT EXISTS public.ad_library_ads (
  "id" text,
  "brand_name" text,
  "ad_title" text,
  "ad_copy" text,
  "platform" text,
  "media_type" text,
  "thumbnail_url" text,
  "video_url" text,
  "landing_url" text,
  "original_ad_url" text,
  "status" text,
  "started_at" text,
  "collected_at" text,
  "score" bigint,
  "category" text,
  "tags" text,
  "is_bookmarked" smallint,
  "memo" text,
  "created_at" text,
  "updated_at" text,
  "ad_format" text,
  "transparency_url" text,
  "media_url" text,
  "preview_url" text,
  "brand_id" bigint,
  "scrape_status" text,
  "error_message" text,
  "platforms" text,
  "local_thumbnail_path" text,
  "script_text" text,
  "script_source" text,
  "script_status" text,
  "script_error_message" text,
  "script_created_at" text,
  "script_updated_at" text,
  "cta" text,
  "ad_variant_count" bigint,
  "yt_views" bigint,
  "yt_likes" bigint,
  "yt_comments" bigint,
  "detail_status" text,
  "yt_embeddable" smallint,
  "fatigue_status" text,
  "is_excluded" smallint,
  "video_url_updated_at" text,
  "last_crawled_at" text,
  "video_status" text,
  "page_id" text,
  "last_seen_at" text,
  "advertiser_name" text,
  "brand_status" text,
  "match_method" text,
  "match_confidence" text,
  "manual_override" smallint,
  "match_reason" text,
  "content_hash" text,
  "dedupe_key" text,
  "first_seen_at" text,
  "is_preserved" smallint,
  "storage_path" text,
  "orig_thumbnail_url" text,
  "migrated_at" timestamptz DEFAULT now(),
  CONSTRAINT ad_library_ads_pkey PRIMARY KEY ("id")
);
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "id" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "brand_name" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "ad_title" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "ad_copy" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "platform" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "media_type" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "thumbnail_url" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "video_url" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "landing_url" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "original_ad_url" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "status" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "started_at" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "collected_at" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "score" bigint;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "category" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "tags" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "is_bookmarked" smallint;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "memo" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "created_at" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "updated_at" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "ad_format" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "transparency_url" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "media_url" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "preview_url" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "brand_id" bigint;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "scrape_status" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "error_message" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "platforms" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "local_thumbnail_path" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "script_text" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "script_source" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "script_status" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "script_error_message" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "script_created_at" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "script_updated_at" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "cta" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "ad_variant_count" bigint;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "yt_views" bigint;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "yt_likes" bigint;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "yt_comments" bigint;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "detail_status" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "yt_embeddable" smallint;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "fatigue_status" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "is_excluded" smallint;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "video_url_updated_at" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "last_crawled_at" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "video_status" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "page_id" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "last_seen_at" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "advertiser_name" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "brand_status" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "match_method" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "match_confidence" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "manual_override" smallint;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "match_reason" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "content_hash" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "dedupe_key" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "first_seen_at" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "is_preserved" smallint;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "storage_path" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "orig_thumbnail_url" text;
ALTER TABLE public.ad_library_ads ADD COLUMN IF NOT EXISTS "migrated_at" timestamptz DEFAULT now();
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ad_library_ads_pkey') THEN
    ALTER TABLE public.ad_library_ads ADD CONSTRAINT ad_library_ads_pkey PRIMARY KEY ("id");
  END IF;
END $$;

-- ── ad_view_snapshots ──
CREATE TABLE IF NOT EXISTS public.ad_view_snapshots (
  "ad_id" text,
  "snapshot_date" text,
  "views" bigint,
  "likes" bigint,
  "comments" bigint,
  "created_at" text,
  "view_snapshot_source" text DEFAULT 'live',
  "migrated_at" timestamptz DEFAULT now(),
  CONSTRAINT ad_view_snapshots_pkey PRIMARY KEY ("ad_id", "snapshot_date")
);
ALTER TABLE public.ad_view_snapshots ADD COLUMN IF NOT EXISTS "ad_id" text;
ALTER TABLE public.ad_view_snapshots ADD COLUMN IF NOT EXISTS "snapshot_date" text;
ALTER TABLE public.ad_view_snapshots ADD COLUMN IF NOT EXISTS "views" bigint;
ALTER TABLE public.ad_view_snapshots ADD COLUMN IF NOT EXISTS "likes" bigint;
ALTER TABLE public.ad_view_snapshots ADD COLUMN IF NOT EXISTS "comments" bigint;
ALTER TABLE public.ad_view_snapshots ADD COLUMN IF NOT EXISTS "created_at" text;
ALTER TABLE public.ad_view_snapshots ADD COLUMN IF NOT EXISTS "view_snapshot_source" text DEFAULT 'live';
ALTER TABLE public.ad_view_snapshots ADD COLUMN IF NOT EXISTS "migrated_at" timestamptz DEFAULT now();
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ad_view_snapshots_pkey') THEN
    ALTER TABLE public.ad_view_snapshots ADD CONSTRAINT ad_view_snapshots_pkey PRIMARY KEY ("ad_id", "snapshot_date");
  END IF;
END $$;

-- ── ad_social_matches ──
CREATE TABLE IF NOT EXISTS public.ad_social_matches (
  "id" bigint,
  "ad_id" text,
  "social_id" text,
  "match_score" double precision,
  "brand_match" smallint,
  "copy_sim" double precision,
  "url_sim" double precision,
  "media_sim" double precision,
  "created_at" text,
  CONSTRAINT ad_social_matches_pkey PRIMARY KEY ("ad_id", "social_id")
);
ALTER TABLE public.ad_social_matches ADD COLUMN IF NOT EXISTS "id" bigint;
ALTER TABLE public.ad_social_matches ADD COLUMN IF NOT EXISTS "ad_id" text;
ALTER TABLE public.ad_social_matches ADD COLUMN IF NOT EXISTS "social_id" text;
ALTER TABLE public.ad_social_matches ADD COLUMN IF NOT EXISTS "match_score" double precision;
ALTER TABLE public.ad_social_matches ADD COLUMN IF NOT EXISTS "brand_match" smallint;
ALTER TABLE public.ad_social_matches ADD COLUMN IF NOT EXISTS "copy_sim" double precision;
ALTER TABLE public.ad_social_matches ADD COLUMN IF NOT EXISTS "url_sim" double precision;
ALTER TABLE public.ad_social_matches ADD COLUMN IF NOT EXISTS "media_sim" double precision;
ALTER TABLE public.ad_social_matches ADD COLUMN IF NOT EXISTS "created_at" text;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ad_social_matches_pkey') THEN
    ALTER TABLE public.ad_social_matches ADD CONSTRAINT ad_social_matches_pkey PRIMARY KEY ("ad_id", "social_id");
  END IF;
END $$;

-- ── social_videos ──
CREATE TABLE IF NOT EXISTS public.social_videos (
  "id" text,
  "brand_name" text,
  "platform" text,
  "video_url" text,
  "thumbnail_url" text,
  "caption" text,
  "views" bigint,
  "likes" bigint,
  "comments" bigint,
  "shares" bigint,
  "posted_at" text,
  "source_url" text,
  "collected_at" text,
  "created_at" text,
  "updated_at" text,
  "absolute_grade" text,
  "internal_grade" text,
  "final_grade" text,
  "engagement_rate" double precision,
  "engagement_level" text,
  "engagement_score" double precision,
  "internal_percentile" double precision,
  "grading_basis" text,
  "graded_at" text,
  "video_id" text,
  "embed_url" text,
  "title" text,
  "channel_title" text,
  "script_text" text,
  "script_status" text,
  "brand_match_score" double precision,
  "brand_match_reason" text,
  "review_status" text,
  CONSTRAINT social_videos_pkey PRIMARY KEY ("id")
);
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "id" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "brand_name" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "platform" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "video_url" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "thumbnail_url" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "caption" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "views" bigint;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "likes" bigint;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "comments" bigint;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "shares" bigint;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "posted_at" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "source_url" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "collected_at" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "created_at" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "updated_at" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "absolute_grade" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "internal_grade" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "final_grade" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "engagement_rate" double precision;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "engagement_level" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "engagement_score" double precision;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "internal_percentile" double precision;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "grading_basis" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "graded_at" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "video_id" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "embed_url" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "title" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "channel_title" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "script_text" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "script_status" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "brand_match_score" double precision;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "brand_match_reason" text;
ALTER TABLE public.social_videos ADD COLUMN IF NOT EXISTS "review_status" text;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'social_videos_pkey') THEN
    ALTER TABLE public.social_videos ADD CONSTRAINT social_videos_pkey PRIMARY KEY ("id");
  END IF;
END $$;

-- ── social_video_snapshots ──
CREATE TABLE IF NOT EXISTS public.social_video_snapshots (
  "id" bigint,
  "social_video_id" text,
  "snapshot_date" text,
  "views" bigint,
  "likes" bigint,
  "comments" bigint,
  "shares" bigint,
  "created_at" text,
  CONSTRAINT social_video_snapshots_pkey PRIMARY KEY ("social_video_id", "snapshot_date")
);
ALTER TABLE public.social_video_snapshots ADD COLUMN IF NOT EXISTS "id" bigint;
ALTER TABLE public.social_video_snapshots ADD COLUMN IF NOT EXISTS "social_video_id" text;
ALTER TABLE public.social_video_snapshots ADD COLUMN IF NOT EXISTS "snapshot_date" text;
ALTER TABLE public.social_video_snapshots ADD COLUMN IF NOT EXISTS "views" bigint;
ALTER TABLE public.social_video_snapshots ADD COLUMN IF NOT EXISTS "likes" bigint;
ALTER TABLE public.social_video_snapshots ADD COLUMN IF NOT EXISTS "comments" bigint;
ALTER TABLE public.social_video_snapshots ADD COLUMN IF NOT EXISTS "shares" bigint;
ALTER TABLE public.social_video_snapshots ADD COLUMN IF NOT EXISTS "created_at" text;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'social_video_snapshots_pkey') THEN
    ALTER TABLE public.social_video_snapshots ADD CONSTRAINT social_video_snapshots_pkey PRIMARY KEY ("social_video_id", "snapshot_date");
  END IF;
END $$;

-- ── brands ──
CREATE TABLE IF NOT EXISTS public.brands (
  "id" bigint,
  "display_name" text,
  "search_keywords" text,
  "official_domain" text,
  "meta_page_name" text,
  "google_advertiser_name" text,
  "youtube_channel_name" text,
  "tiktok_handle" text,
  "instagram_handle" text,
  "category" text,
  "is_active" smallint,
  "created_at" text,
  "updated_at" text,
  "meta_page_id" text,
  "page_id_status" text,
  "meta_reported_count" bigint,
  "sort_order" bigint,
  "brand_aliases" text,
  "product_keywords" text,
  "brand_domains" text,
  CONSTRAINT brands_pkey PRIMARY KEY ("id")
);
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "id" bigint;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "display_name" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "search_keywords" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "official_domain" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "meta_page_name" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "google_advertiser_name" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "youtube_channel_name" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "tiktok_handle" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "instagram_handle" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "category" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "is_active" smallint;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "created_at" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "updated_at" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "meta_page_id" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "page_id_status" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "meta_reported_count" bigint;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "sort_order" bigint;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "brand_aliases" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "product_keywords" text;
ALTER TABLE public.brands ADD COLUMN IF NOT EXISTS "brand_domains" text;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'brands_pkey') THEN
    ALTER TABLE public.brands ADD CONSTRAINT brands_pkey PRIMARY KEY ("id");
  END IF;
END $$;

-- ── 조회 성능 인덱스 ──
CREATE INDEX IF NOT EXISTS ad_library_ads_brand_idx    ON public.ad_library_ads (brand_name);
CREATE INDEX IF NOT EXISTS ad_library_ads_platform_idx ON public.ad_library_ads (platform);
CREATE INDEX IF NOT EXISTS ad_library_ads_seen_idx     ON public.ad_library_ads (last_seen_at);
CREATE INDEX IF NOT EXISTS ad_view_snapshots_date_idx  ON public.ad_view_snapshots (snapshot_date);
CREATE INDEX IF NOT EXISTS ad_social_matches_ad_idx    ON public.ad_social_matches (ad_id);
CREATE INDEX IF NOT EXISTS social_videos_brand_idx     ON public.social_videos (brand_name);

-- ── RLS: 앱(anon)은 읽기만 / 수집 잡(service_role)은 RLS 우회 ──
ALTER TABLE public.ad_library_ads         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ad_view_snapshots      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ad_social_matches      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.social_videos          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.social_video_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.brands                 ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['ad_library_ads','ad_view_snapshots','ad_social_matches',
                           'social_videos','social_video_snapshots','brands'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_read', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO anon, authenticated USING (true)',
                   t || '_read', t);
  END LOOP;
END $$;

-- ── 확인용: 생성 결과 ──
SELECT table_name, count(*) AS columns
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('ad_library_ads','ad_view_snapshots','ad_social_matches',
                     'social_videos','social_video_snapshots','brands')
GROUP BY table_name ORDER BY table_name;