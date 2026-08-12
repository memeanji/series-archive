-- Series Archive — 조회수 저장 방식 변경(2026-08-11)
-- 최신 조회수는 '영상 단위'로 이 표에 UPDATE 하고, 과거 추이는 기존 ad_view_snapshots 를 그대로 쓴다.
-- 기존 표는 어느 것도 건드리지 않는다(ad_scripts 포함). 여러 번 실행해도 안전.

CREATE TABLE IF NOT EXISTS public.video_view_state (
  "social_id"             text,          -- 영상 식별자(YouTube video_id 또는 social_videos.id)
  "platform"              text DEFAULT '',
  "current_view_count"    bigint DEFAULT 0,
  "current_like_count"    bigint DEFAULT 0,
  "current_comment_count" bigint DEFAULT 0,
  "last_checked_at"       text,          -- 마지막으로 조회수를 확인한 시각
  "last_snapshot_date"    text,          -- 마지막으로 추이 스냅샷을 남긴 날짜(YYYY-MM-DD)
  "source_url"            text DEFAULT '',
  CONSTRAINT video_view_state_pkey PRIMARY KEY ("social_id")
);

-- 이미 있던 표라면 빠진 컬럼만 채운다(삭제 없음)
ALTER TABLE public.video_view_state ADD COLUMN IF NOT EXISTS "platform" text DEFAULT '';
ALTER TABLE public.video_view_state ADD COLUMN IF NOT EXISTS "current_view_count" bigint DEFAULT 0;
ALTER TABLE public.video_view_state ADD COLUMN IF NOT EXISTS "current_like_count" bigint DEFAULT 0;
ALTER TABLE public.video_view_state ADD COLUMN IF NOT EXISTS "current_comment_count" bigint DEFAULT 0;
ALTER TABLE public.video_view_state ADD COLUMN IF NOT EXISTS "last_checked_at" text;
ALTER TABLE public.video_view_state ADD COLUMN IF NOT EXISTS "last_snapshot_date" text;
ALTER TABLE public.video_view_state ADD COLUMN IF NOT EXISTS "source_url" text DEFAULT '';

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'video_view_state_pkey') THEN
    ALTER TABLE public.video_view_state ADD CONSTRAINT video_view_state_pkey PRIMARY KEY ("social_id");
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS video_view_state_checked_idx
  ON public.video_view_state (last_checked_at);

ALTER TABLE public.video_view_state ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS video_view_state_read ON public.video_view_state;
CREATE POLICY video_view_state_read ON public.video_view_state
  FOR SELECT TO anon, authenticated USING (true);

SELECT count(*) AS columns FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'video_view_state';
