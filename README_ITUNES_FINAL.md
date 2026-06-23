# jmusic-config — iTunes Final Smart Feed

גרסה סופית ליצירת `home_feed.json` עבור JMusic/Metrolist.

## עיקרון עבודה

- **iTunes Search API** הוא מקור המטא־דאטה: תאריך יציאה, עטיפה, שם אלבום/שיר וקישור iTunes.
- **YouTube Music** משמש רק כדי לקרוא מדפי האמנים המותרים את האלבומים/הסינגלים וכדי לשמור `youtubeBrowseId` / `youtubeVideoId` לניגון באפליקציה.
- אין Spotify.
- אין Apple Music Developer Token.
- אין deep-translator בריצה הלילית.
- יש תעתיק עברית־אנגלית פנימי + RapidFuzz לניקוד התאמות חכם.

## קבצים חשובים

```text
allowed_artists.txt
artist_sources.json
requirements.txt
requirements-aliases.txt
scripts/generate_home_feed.py
scripts/enrich_artist_aliases.py
.github/workflows/generate-home-feed.yml
cache/.gitkeep
```

## מה חכם במנגנון ההתאמה

הסקריפט לא מאשר תוצאה רק כי שם האמן דומה.

פריט נכנס ל־`home_feed.json` רק אם יש:

```text
שם אמן/alias מתאים
+
שם אלבום/שיר מתאים
+
סוג פריט מתאים, אלבום או סינגל
+
תאריך יציאה מ־iTunes
+
matchScore >= MIN_MATCH_SCORE
```

תוצאות חלשות לא נכנסות לפיד. הן נרשמות ב־`home_feed_report.json` תחת `weakMatches`.

יש גם שער בטיחות נוסף: גם אם שם השיר מתאים מאוד, התוצאה לא תאושר אם ציון שם האמן נמוך מדי. זה מונע מצב שבו `קובי ברומר` יאושר בטעות מול `Kobi Peretz` רק בגלל ששם השיר דומה.

## תעתיק עברית־אנגלית

הסקריפט יוצר aliases אוטומטיים, למשל:

```text
קובי ברומר -> kobi brumer / koby brumer / cobi brumer
משה קליין -> moshe klein / moshe kleyn
שמוליק סוכות -> shmueli sukkot / shmulik sukkot
חיים ישראל -> chaim yisrael / haim israel
```

בנוסף יש השוואה פונטית כדי להבין וריאציות כמו:

```text
Brumer / Bromer / Brumr / Bromr
```

## RapidFuzz

RapidFuzz נוסף כשכבת ניקוד נוספת. הוא לא מחליט לבד, אלא רק משפר את ניקוד הדמיון בתוך המנגנון הכולל.

## שמירה על מגבלות iTunes

ברירת המחדל:

```text
itunes_request_delay_seconds = 4.0
```

כלומר בערך 15 קריאות בדקה, עם מרווח בטיחות.

בנוסף:

```text
itunes_429_sleep_seconds = 90
itunes_max_retries = 2
max_itunes_lookups_total = 150
```

ה־cache נשמר כאן:

```text
cache/itunes_lookup_cache.json
cache/youtube_album_details_cache.json
```

## הרצה ראשונה מומלצת

ב־GitHub:

```text
Actions -> Generate Home Feed -> Run workflow
```

ערכים מומלצים:

```text
itunes_country = IL
max_items_per_artist_category = 4
artist_albums_limit = 50
max_release_age_days = 180
min_release_date =
youtube_request_delay_seconds = 0.8
itunes_request_delay_seconds = 4.0
itunes_429_sleep_seconds = 90
itunes_max_retries = 2
max_itunes_lookups_total = 150
min_match_score = 78
min_artist_match_score = 28
min_title_match_score = 30
enable_rapidfuzz = true
enable_hebrew_transliteration = true
max_auto_aliases_per_artist = 8
max_search_aliases_per_item = 6
refresh_itunes_cache = false
refresh_youtube_cache = false
```

## אחרי שהכול עובד

אפשר להגדיל בהדרגה:

```text
max_items_per_artist_category = 8
artist_albums_limit = 80
max_itunes_lookups_total = 0
```

אבל לא מומלץ להוריד:

```text
itunes_request_delay_seconds
```

מתחת ל־`3.5`.

## דוח בדיקה

אחרי כל ריצה פתח:

```text
home_feed_report.json
```

בדוק במיוחד:

```text
itemsGeneratedAfterDedupe
albumsGeneratedAfterDedupe
singlesGeneratedAfterDedupe
itunesNetworkReads
itunesCacheHits
itunes429Count
itemsSkippedWeakItunesCandidate
weakMatches
artistsWithAutoAliases
autoAliasExamples
minArtistMatchScore
minTitleMatchScore
enableRapidFuzz
rapidFuzzAvailable
```

## סקריפט עזר להעשרת aliases

יש סקריפט אופציונלי:

```text
scripts/enrich_artist_aliases.py
```

הוא לא רץ בלילה. הוא נועד לשימוש ידני בלבד.

להרצה בלי Google Translate, רק יצירת מבנה `artist_sources.json`:

```bash
python scripts/enrich_artist_aliases.py
```

להרצה עם deep-translator/GoogleTranslator:

```bash
pip install -r requirements-aliases.txt
python scripts/enrich_artist_aliases.py --use-google
```

לאחר מכן מומלץ לעבור ידנית על `artist_sources.json` לפני Commit.
