INSERT OR REPLACE INTO RootFolders (Id, Path) VALUES (1, '/tmp/media');

INSERT OR REPLACE INTO Tags (Id, Label) VALUES (1, 'test-tag');

INSERT OR REPLACE INTO Series (Id, TvdbId, TvRageId, Title, CleanTitle, Status, Images, Path, Monitored, SeasonFolder, Runtime, SeriesType, UseSceneNumbering, TvMazeId, OriginalLanguage, QualityProfileId)
VALUES (1, 10000001, 0, 'Test Series', 'testseries', 1, '[]', '/tmp/media/test-series', 1, 1, 60, 0, 0, 0, 1, 1);

INSERT OR REPLACE INTO Episodes (Id, SeriesId, SeasonNumber, EpisodeNumber, EpisodeFileId, UnverifiedSceneNumbering, Runtime, Monitored, AirDateUtc, Title)
VALUES
(1, 1, 1, 1, 0, 0, 60, 1, '2026-01-01T00:00:00Z', 'Test Episode 01'),
(2, 1, 1, 2, 0, 0, 60, 1, '2026-01-08T00:00:00Z', 'Test Episode 02'),
(3, 1, 1, 3, 0, 0, 60, 1, '2026-01-15T00:00:00Z', 'Test Episode 03'),
(4, 1, 1, 4, 0, 0, 60, 1, '2026-01-22T00:00:00Z', 'Test Episode 04'),
(5, 1, 1, 5, 0, 0, 60, 1, '2026-01-29T00:00:00Z', 'Test Episode 05');
