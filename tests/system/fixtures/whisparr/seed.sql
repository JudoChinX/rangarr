INSERT OR REPLACE INTO RootFolders (Id, Path) VALUES (1, '/tmp/media');

INSERT OR REPLACE INTO Tags (Id, Label) VALUES (1, 'test-tag');

INSERT OR REPLACE INTO Series (Id, TvdbId, Title, CleanTitle, Status, Images, Path, Monitored, QualityProfileId, Runtime, UseSceneNumbering, OriginalLanguage, FirstAired, LastAired, Added, Seasons, Ratings)
VALUES (1, 10000001, 'Test Performer', 'testperformer', 1, '[]', '/tmp/media/test-performer', 1, 1, 30, 0, 1, '2024-01-01T00:00:00Z', '2024-01-15T00:00:00Z', '2024-01-01T00:00:00Z', '[]', '{}');

INSERT OR REPLACE INTO Episodes (Id, SeriesId, SeasonNumber, Runtime, Monitored, EpisodeFileId, AirDate, AirDateUtc, Title)
VALUES
(1, 1, 1, 30, 1, 0, '2024-01-01', '2024-01-01T00:00:00Z', 'Test Scene 01'),
(2, 1, 1, 30, 1, 0, '2024-01-08', '2024-01-08T00:00:00Z', 'Test Scene 02'),
(3, 1, 1, 30, 1, 0, '2024-01-15', '2024-01-15T00:00:00Z', 'Test Scene 03');
